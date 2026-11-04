"""Execution worker: the only process that runs learner code.

    python -m app.coding.worker            # poll forever
    python -m app.coding.worker --once     # process at most one job (tests, cron)

Jobs are claimed with ``FOR UPDATE SKIP LOCKED`` and a lease. A crashed worker's
lease expires and the job is retried, up to FORGE_JOB_MAX_ATTEMPTS. Completion is
fenced on (status=running, worker_id), and results are unique per test case, so
a retry can never record results twice or create duplicate submissions.
Learner-code failures (errors, timeouts) are results, not job failures; only
infrastructure problems are retried.
"""

import asyncio
import logging
import os
import socket
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.coding.grading import CaseResult, CaseSpec, grade
from app.coding.sandbox import ExecRequest, SandboxUnavailable, Verification, build_sandbox
from app.core.config import Settings, get_settings
from app.db.enums import JobKind, JobStatus, TestOutcome, TestVisibility
from app.db.models import (
    CodingChallengeVersion,
    CodingJob,
    CodingSubmission,
    CodingTestResult,
    WorkerHeartbeat,
)
from app.db.session import create_engine, create_sessionmaker

log = logging.getLogger("forge.worker")


def _now() -> datetime:
    return datetime.now(UTC)


class Worker:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], sandbox=None) -> None:
        self.s = settings
        self.sessions = sessionmaker
        self.sandbox = sandbox or build_sandbox(settings)
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.verification: Verification | None = None
        from app.workspace.jobs import EngineeringJobs

        # FORGE Workspace project jobs share this process, sandbox and self-check.
        self.projects = EngineeringJobs(self)

    async def verify(self) -> Verification:
        self.verification = await self.sandbox.verify()
        await self.heartbeat()
        return self.verification

    async def heartbeat(self) -> None:
        v = self.verification
        async with self.sessions() as db:
            await db.execute(
                pg_insert(WorkerHeartbeat)
                .values(worker_id=self.id, backend=self.sandbox.name, verified=bool(v and v.verified),
                        report=v.as_json() if v else {}, last_seen_at=_now())
                .on_conflict_do_update(
                    index_elements=[WorkerHeartbeat.worker_id],
                    set_={"verified": bool(v and v.verified), "report": v.as_json() if v else {}, "last_seen_at": _now()},
                )
            )
            await db.commit()

    async def claim(self) -> CodingJob | None:
        async with self.sessions() as db:
            now = _now()
            job = await db.scalar(
                select(CodingJob)
                .where(or_(
                    CodingJob.status == JobStatus.QUEUED,
                    (CodingJob.status == JobStatus.RUNNING) & (CodingJob.lease_expires_at < now),
                ))
                .order_by(CodingJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.attempts >= self.s.job_max_attempts:
                job.status, job.error_code, job.finished_at = JobStatus.FAILED, "max_attempts_exceeded", now
                job.error_message = "The job could not be completed after several attempts"
                await db.commit()
                return None
            job.status, job.worker_id = JobStatus.RUNNING, self.id
            job.attempts += 1
            job.lease_expires_at = now + timedelta(seconds=self.s.job_lease_seconds)
            job.started_at = job.started_at or now
            await db.commit()
            return job

    async def _finish(self, job_id: uuid.UUID, **fields) -> bool:
        async with self.sessions() as db:
            job = await db.scalar(
                select(CodingJob).where(CodingJob.id == job_id).with_for_update()
            )
            if job is None or job.status is not JobStatus.RUNNING or job.worker_id != self.id:
                return False  # lease lost: another worker owns this job now
            for k, v in fields.items():
                setattr(job, k, v)
            job.finished_at = _now()
            await db.commit()
            return True

    async def process(self, job: CodingJob) -> None:
        v = self.verification
        if self.sandbox.name == "disabled":
            await self._finish(job.id, status=JobStatus.BLOCKED, error_code="execution_disabled",
                               error_message="Code execution is disabled on this server")
            return
        if v is None or not v.verified or not v.languages.get(job.language):
            await self._finish(job.id, status=JobStatus.BLOCKED, error_code="sandbox_unverified",
                               error_message="The sandbox failed its security self-check, so nothing was run")
            return

        async with self.sessions() as db:
            version = await db.scalar(
                select(CodingChallengeVersion).where(CodingChallengeVersion.id == job.version_id)
                .options(selectinload(CodingChallengeVersion.tests), selectinload(CodingChallengeVersion.files),
                         selectinload(CodingChallengeVersion.challenge))
            )
        assert version is not None
        tests = [t for t in version.tests if job.kind is JobKind.SUBMIT or t.visibility is TestVisibility.PUBLIC]
        cases = [CaseSpec(t.id, t.position, t.name, t.visibility, t.call, t.args, t.expected) for t in tests]
        driver = next((f.content for f in version.files if f.language == job.language and f.role == "driver"), None)

        if not self.sandbox.executes:  # mock: nothing runs, nothing is graded
            results = [CaseResult(c.id, c.position, TestOutcome.NOT_EXECUTED, None, "Mock runner: not executed", None)
                       for c in cases]
        else:
            try:
                res = await self.sandbox.run(ExecRequest(
                    job.language, job.code, driver, cases, version.time_limit_ms, version.memory_limit_mb))
            except SandboxUnavailable as exc:
                log.warning("sandbox unavailable for job %s: %s", job.id, exc)
                await self._release(job, str(exc))
                return
            results = grade(cases, res.stdout, killed_for_time=res.killed_for_time)
            if res.output_truncated:
                results = [r if r.outcome is TestOutcome.PASSED else
                           CaseResult(r.case_id, r.position, TestOutcome.ERROR, r.duration_ms, "Output limit exceeded", None)
                           for r in results]
        await self._record(job, version, results)

    async def _release(self, job: CodingJob, reason: str) -> None:
        """Infrastructure failure: requeue for retry, or fail after max attempts."""
        final = job.attempts >= self.s.job_max_attempts
        async with self.sessions() as db:
            row = await db.scalar(select(CodingJob).where(CodingJob.id == job.id).with_for_update())
            if row is None or row.worker_id != self.id or row.status is not JobStatus.RUNNING:
                return
            row.status = JobStatus.FAILED if final else JobStatus.QUEUED
            row.lease_expires_at = None
            row.error_code = "sandbox_unavailable" if final else None
            row.error_message = "Execution infrastructure is unavailable" if final else None
            if final:
                row.finished_at = _now()
            await db.commit()

    async def _record(self, job: CodingJob, version: CodingChallengeVersion, results: list[CaseResult]) -> None:
        executed = self.sandbox.executes
        async with self.sessions() as db:
            row = await db.scalar(select(CodingJob).where(CodingJob.id == job.id).with_for_update())
            if row is None or row.status is not JobStatus.RUNNING or row.worker_id != self.id:
                return
            for r in results:
                await db.execute(
                    pg_insert(CodingTestResult)
                    .values(job_id=job.id, test_case_id=r.case_id, position=r.position, outcome=r.outcome,
                            duration_ms=r.duration_ms, message=r.message, actual=r.actual)
                    .on_conflict_do_nothing(index_elements=[CodingTestResult.job_id, CodingTestResult.test_case_id])
                )
            if job.kind is JobKind.SUBMIT:
                passed = sum(r.outcome is TestOutcome.PASSED for r in results)
                await db.execute(
                    pg_insert(CodingSubmission)
                    .values(job_id=job.id, learner_id=job.learner_id, challenge_id=version.challenge_id,
                            version_id=version.id, language=job.language, passed=passed, total=len(results),
                            all_passed=executed and passed == len(results), hints_used=job.hints_used,
                            executed=executed, verified=executed and bool(self.verification and self.verification.verified))
                    .on_conflict_do_nothing(index_elements=[CodingSubmission.job_id])
                )
            row.status, row.backend = JobStatus.COMPLETED, self.sandbox.name
            row.sandbox_verified = bool(self.verification and self.verification.verified and executed)
            row.finished_at, row.lease_expires_at = _now(), None
            await db.commit()
        if job.kind is JobKind.SUBMIT and executed:
            await self._sync_mastery(job.learner_id)

    async def _sync_mastery(self, learner_id: uuid.UUID) -> None:
        from app.mastery.service import sync_learner

        try:
            async with self.sessions() as db:
                await sync_learner(db, learner_id, _now())
        except Exception:  # noqa: BLE001 - mastery reads re-sync; never fail the job
            log.exception("mastery sync failed")

    async def run_once(self) -> bool:
        job = await self.claim()
        if job is None:
            return await self.projects.run_once()
        try:
            await self.process(job)
        except Exception:  # noqa: BLE001
            log.exception("job %s crashed", job.id)
            await self._release(job, "worker error")
        return True

    async def run_forever(self) -> None:
        await self.verify()
        log.info("worker %s backend=%s verified=%s problems=%s", self.id, self.sandbox.name,
                 self.verification.verified, self.verification.problems)
        last_beat = _now()
        while True:
            worked = await self.run_once()
            if _now() - last_beat > timedelta(seconds=10):
                await self.heartbeat()
                last_beat = _now()
            if not worked:
                await asyncio.sleep(self.s.worker_poll_seconds)


async def main(once: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings.require_database_url())
    try:
        worker = Worker(settings, create_sessionmaker(engine))
        if once:
            await worker.verify()
            await worker.run_once()
        else:
            await worker.run_forever()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(main("--once" in sys.argv))
