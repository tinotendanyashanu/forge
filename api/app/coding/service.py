"""Coding lab API-side logic. Never executes code: it only queues jobs."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.enums import JobKind, JobStatus, TestVisibility
from app.db.models import (
    CodingChallenge,
    CodingChallengeVersion,
    CodingDraft,
    CodingJob,
    CodingSubmission,
    Learner,
    WorkerHeartbeat,
)
from app.services.errors import Conflict, DomainError, NotFound, Unprocessable

HEARTBEAT_FRESH = timedelta(seconds=30)


class RateLimited(DomainError):
    status_code = 429


class ExecutionDisabled(DomainError):
    status_code = 503


def _now() -> datetime:
    return datetime.now(UTC)


async def execution_status(db: AsyncSession, settings: Settings) -> dict:
    beat = await db.scalar(
        select(WorkerHeartbeat)
        .where(WorkerHeartbeat.backend == settings.sandbox_backend)
        .order_by(WorkerHeartbeat.last_seen_at.desc())
        .limit(1)
    )
    online = beat is not None and beat.last_seen_at > _now() - HEARTBEAT_FRESH
    report = beat.report if beat else {}
    return {
        "backend": settings.sandbox_backend,
        "accepts_jobs": settings.sandbox_backend != "disabled",
        "executes_code": settings.sandbox_backend == "docker",
        "worker_online": online,
        "verified": bool(online and beat.verified),
        "languages": report.get("languages", {}) if online else {},
        "problems": report.get("problems", []) if beat else ["No execution worker has reported in"],
        "isolation": (
            "container (single-user acknowledged)" if settings.sandbox_backend == "docker"
            else "none: code is never executed" if settings.sandbox_backend == "mock" else "disabled"
        ),
    }


async def get_challenge(db: AsyncSession, slug: str) -> CodingChallenge:
    challenge = await db.scalar(
        select(CodingChallenge)
        .where(CodingChallenge.slug == slug, CodingChallenge.is_active)
        .options(
            selectinload(CodingChallenge.skill),
            selectinload(CodingChallenge.current_version).selectinload(CodingChallengeVersion.files),
            selectinload(CodingChallenge.current_version).selectinload(CodingChallengeVersion.tests),
        )
    )
    if challenge is None or challenge.current_version is None:
        raise NotFound(f"Challenge '{slug}' not found")
    return challenge


def languages_of(version: CodingChallengeVersion) -> list[str]:
    return sorted({f.language for f in version.files if f.role == "starter"})


# ---------------------------------------------------------------- drafts & hints


async def save_draft(
    db: AsyncSession, settings: Settings, learner: Learner, slug: str, language: str, code: str,
    base_revision: int | None,
) -> CodingDraft:
    if len(code.encode()) > settings.coding_max_code_bytes:
        raise Unprocessable(f"Code exceeds {settings.coding_max_code_bytes} bytes")
    challenge = await get_challenge(db, slug)
    if language not in languages_of(challenge.current_version):
        raise Unprocessable(f"{language} is not available for this challenge")
    draft = await db.get(CodingDraft, (learner.id, challenge.id, language), with_for_update=True)
    if draft is None:
        draft = CodingDraft(learner_id=learner.id, challenge_id=challenge.id, language=language, code=code, revision=1)
        db.add(draft)
    else:
        # Optimistic concurrency: a stale tab can't overwrite newer work.
        if base_revision is not None and base_revision != draft.revision:
            raise Conflict("This draft was changed elsewhere. Reload to get the latest version.")
        draft.code, draft.revision, draft.updated_at = code, draft.revision + 1, _now()
    await db.commit()
    return draft


async def reveal_hint(db: AsyncSession, learner: Learner, slug: str, language: str) -> tuple[list[str], int]:
    challenge = await get_challenge(db, slug)
    version = challenge.current_version
    draft = await db.get(CodingDraft, (learner.id, challenge.id, language), with_for_update=True)
    if draft is None:
        starter = next((f.content for f in version.files if f.language == language and f.role == "starter"), None)
        if starter is None:
            raise Unprocessable(f"{language} is not available for this challenge")
        draft = CodingDraft(learner_id=learner.id, challenge_id=challenge.id, language=language, code=starter, hints_used=0)
        db.add(draft)
        await db.flush()
    if draft.hints_used >= len(version.hints):
        raise Conflict("No more hints for this challenge")
    draft.hints_used += 1
    await db.commit()
    return list(version.hints[: draft.hints_used]), len(version.hints)


# ---------------------------------------------------------------- jobs


async def enqueue(
    db: AsyncSession, settings: Settings, learner: Learner, *, slug: str, language: str, code: str,
    kind: JobKind, idempotency_key: uuid.UUID,
) -> tuple[CodingJob, bool]:
    """Returns (job, created). Identical retries return the original job."""
    if settings.sandbox_backend == "disabled":
        raise ExecutionDisabled("Code execution is disabled on this server")
    size = len(code.encode())
    if size == 0 or not code.strip():
        raise Unprocessable("Code is empty")
    if size > settings.coding_max_code_bytes:
        raise Unprocessable(f"Code exceeds {settings.coding_max_code_bytes} bytes")

    # Serialise this learner's enqueues so limits can't be raced.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 1))"), {"k": str(learner.id)})
    existing = await db.scalar(
        select(CodingJob).where(CodingJob.learner_id == learner.id, CodingJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        await db.commit()
        return existing, False

    challenge = await get_challenge(db, slug)
    version = challenge.current_version
    if language not in languages_of(version):
        raise Unprocessable(f"{language} is not available for this challenge")
    digest = hashlib.sha256(code.encode()).hexdigest()

    if kind is JobKind.SUBMIT:
        # Resubmitting identical code returns the earlier result: no new evidence.
        same = await db.scalar(
            select(CodingJob).where(
                CodingJob.learner_id == learner.id, CodingJob.version_id == version.id,
                CodingJob.kind == JobKind.SUBMIT, CodingJob.language == language,
                CodingJob.code_sha256 == digest,
                CodingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]),
            ).order_by(CodingJob.created_at.desc()).limit(1)
        )
        if same is not None:
            await db.commit()
            return same, False

    now = _now()
    active = await db.scalar(
        select(func.count()).select_from(CodingJob).where(
            CodingJob.learner_id == learner.id, CodingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
        )
    ) or 0
    if active >= settings.coding_max_active_jobs:
        raise RateLimited("Too many jobs in progress. Wait for one to finish.")
    window, limit = (
        (timedelta(minutes=1), settings.coding_runs_per_minute) if kind is JobKind.RUN
        else (timedelta(hours=1), settings.coding_submits_per_hour)
    )
    recent = await db.scalar(
        select(func.count()).select_from(CodingJob).where(
            CodingJob.learner_id == learner.id, CodingJob.kind == kind, CodingJob.created_at > now - window
        )
    ) or 0
    if recent >= limit:
        raise RateLimited(f"Rate limit reached ({limit} {kind.value}s per {'minute' if kind is JobKind.RUN else 'hour'}).")

    draft = await db.get(CodingDraft, (learner.id, challenge.id, language))
    job = CodingJob(
        learner_id=learner.id, version_id=version.id, kind=kind, language=language, code=code,
        code_sha256=digest, idempotency_key=idempotency_key, hints_used=draft.hints_used if draft else 0,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        job = await db.scalar(
            select(CodingJob).where(CodingJob.learner_id == learner.id, CodingJob.idempotency_key == idempotency_key)
        )
        if job is None:
            raise
        return job, False
    return job, True


async def load_job(db: AsyncSession, learner: Learner, job_id: uuid.UUID) -> CodingJob:
    job = await db.scalar(
        select(CodingJob)
        .where(CodingJob.id == job_id, CodingJob.learner_id == learner.id)
        .options(
            selectinload(CodingJob.results),
            selectinload(CodingJob.version).selectinload(CodingChallengeVersion.tests),
            selectinload(CodingJob.version).selectinload(CodingChallengeVersion.challenge),
        )
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise NotFound("Job not found")
    return job


async def solved_challenge_ids(db: AsyncSession, learner_id: uuid.UUID) -> set[int]:
    rows = await db.scalars(
        select(CodingSubmission.challenge_id).where(
            CodingSubmission.learner_id == learner_id, CodingSubmission.all_passed, CodingSubmission.executed
        )
    )
    return set(rows.all())


def public_tests(version: CodingChallengeVersion):
    return [t for t in version.tests if t.visibility is TestVisibility.PUBLIC]
