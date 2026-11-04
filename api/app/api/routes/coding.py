"""Coding lab endpoints. The API only queues jobs; the worker executes them."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentLearner, Db, get_llm
from app.coding import review as review_mod
from app.coding import service
from app.db.enums import Difficulty, JobKind, JobStatus, ReviewStatus, TestOutcome, TestVisibility
from app.db.models import (
    CodingChallenge,
    CodingChallengeVersion,
    CodingDraft,
    CodingJob,
    CodingReview,
    CodingSubmission,
    CodingTestResult,
    Skill,
    SkillMastery,
)
from app.services.errors import Conflict, NotFound

public = APIRouter(prefix="/coding", tags=["coding"])
router = APIRouter(prefix="/coding", tags=["coding"])
LLM = Annotated[object, Depends(get_llm)]
Language = Literal["python", "javascript", "typescript"]


# ---------------------------------------------------------------- schemas


class ChallengeSummary(BaseModel):
    slug: str
    title: str
    area: str
    skill: dict
    difficulty: Difficulty
    languages: list[str]
    version: int
    public_tests: int
    hidden_tests: int


class PublicTest(BaseModel):
    name: str
    call: str
    args: list[Any]
    expected: dict


class ChallengeDetail(ChallengeSummary):
    description: str
    constraints: list[str]
    prerequisites: list[str]
    rubric: list[str]
    hint_count: int
    time_limit_ms: int
    memory_limit_mb: int
    starters: dict[str, str]
    examples: list[PublicTest]
    hidden_test_names: list[str]


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Language
    code: str = Field(max_length=262_144)
    base_revision: int | None = Field(default=None, ge=1)


class DraftOut(BaseModel):
    language: str
    code: str
    revision: int
    hints_used: int
    updated_at: datetime


class HintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Language


class JobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=96)
    language: Language
    code: str = Field(max_length=262_144)
    kind: JobKind
    idempotency_key: uuid.UUID


class TestResultOut(BaseModel):
    name: str
    visibility: TestVisibility
    outcome: TestOutcome
    duration_ms: int | None
    message: str | None
    # Public tests only:
    args: list[Any] | None = None
    expected: dict | None = None
    actual: str | None = None


class JobOut(BaseModel):
    id: uuid.UUID
    challenge_slug: str
    kind: JobKind
    language: str
    status: JobStatus
    attempts: int
    error_code: str | None
    error_message: str | None
    backend: str | None
    sandbox_verified: bool
    created_at: datetime
    finished_at: datetime | None
    passed: int | None
    total: int | None
    results: list[TestResultOut]
    submission_id: uuid.UUID | None


class SubmissionOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    challenge_slug: str
    challenge_title: str
    language: str
    passed: int
    total: int
    all_passed: bool
    executed: bool
    verified: bool
    hints_used: int
    created_at: datetime
    review_status: ReviewStatus | None


class ReviewOut(BaseModel):
    status: ReviewStatus
    error_code: str | None
    review: dict | None
    provider: str
    model: str
    leak_blocked: bool
    updated_at: datetime


class SubmissionDetail(SubmissionOut):
    code: str
    results: list[TestResultOut]
    review: ReviewOut | None
    reference_solution: str | None  # only after a verified all-pass
    misconceptions: list[str] | None


class ChallengeState(BaseModel):
    draft: DraftOut | None
    drafts: dict[str, DraftOut]
    hints: list[str]
    solved: bool
    attempts: int
    best: SubmissionOut | None
    reference_solutions: dict[str, str] | None
    misconceptions: list[str] | None


# ---------------------------------------------------------------- helpers


def _summary(ch: CodingChallenge) -> ChallengeSummary:
    v = ch.current_version
    return ChallengeSummary(
        slug=ch.slug, title=v.title, area=ch.area, skill={"slug": ch.skill.slug, "title": ch.skill.title},
        difficulty=ch.difficulty, languages=service.languages_of(v), version=v.number,
        public_tests=sum(t.visibility is TestVisibility.PUBLIC for t in v.tests),
        hidden_tests=sum(t.visibility is TestVisibility.HIDDEN for t in v.tests),
    )


def _results(job: CodingJob) -> list[TestResultOut]:
    tests = {t.id: t for t in job.version.tests}
    out = []
    for r in job.results:
        t = tests[r.test_case_id]
        hidden = t.visibility is TestVisibility.HIDDEN
        out.append(TestResultOut(
            name=t.name, visibility=t.visibility, outcome=r.outcome, duration_ms=r.duration_ms,
            message=r.message,
            args=None if hidden else t.args, expected=None if hidden else t.expected,
            actual=None if hidden else r.actual,
        ))
    return out


async def _job_out(db, job: CodingJob) -> JobOut:
    sub_id = await db.scalar(select(CodingSubmission.id).where(CodingSubmission.job_id == job.id))
    done = job.status is JobStatus.COMPLETED
    return JobOut(
        id=job.id, challenge_slug=job.version.challenge.slug, kind=job.kind, language=job.language,
        status=job.status, attempts=job.attempts, error_code=job.error_code, error_message=job.error_message,
        backend=job.backend, sandbox_verified=job.sandbox_verified, created_at=job.created_at,
        finished_at=job.finished_at,
        passed=sum(r.outcome is TestOutcome.PASSED for r in job.results) if done else None,
        total=len(job.results) if done else None,
        results=_results(job) if done else [], submission_id=sub_id,
    )


def _sub_out(s: CodingSubmission, slug: str, title: str, review: CodingReview | None) -> SubmissionOut:
    return SubmissionOut(
        id=s.id, job_id=s.job_id, challenge_slug=slug, challenge_title=title, language=s.language,
        passed=s.passed, total=s.total, all_passed=s.all_passed, executed=s.executed, verified=s.verified,
        hints_used=s.hints_used, created_at=s.created_at, review_status=review.status if review else None,
    )


# ---------------------------------------------------------------- catalogue (public)


@public.get("/challenges", response_model=list[ChallengeSummary])
async def list_challenges(
    db: Db,
    skill: str | None = None,
    area: str | None = None,
    difficulty: Difficulty | None = None,
    language: Language | None = None,
) -> list[ChallengeSummary]:
    stmt = (
        select(CodingChallenge).join(Skill, Skill.id == CodingChallenge.skill_id)
        .where(CodingChallenge.is_active)
        .options(selectinload(CodingChallenge.skill),
                 selectinload(CodingChallenge.current_version).selectinload(CodingChallengeVersion.tests),
                 selectinload(CodingChallenge.current_version).selectinload(CodingChallengeVersion.files))
        .order_by(CodingChallenge.position)
    )
    if skill:
        stmt = stmt.where(Skill.slug == skill)
    if area:
        stmt = stmt.where(CodingChallenge.area == area)
    if difficulty:
        stmt = stmt.where(CodingChallenge.difficulty == difficulty)
    out = [_summary(c) for c in (await db.scalars(stmt)).all() if c.current_version]
    return [c for c in out if language is None or language in c.languages]


@public.get("/challenges/{slug}", response_model=ChallengeDetail)
async def challenge_detail(slug: str, db: Db) -> ChallengeDetail:
    ch = await service.get_challenge(db, slug)
    v = ch.current_version
    return ChallengeDetail(
        **_summary(ch).model_dump(), description=v.description, constraints=list(v.constraints),
        prerequisites=list(v.prerequisites), rubric=list(v.rubric), hint_count=len(v.hints),
        time_limit_ms=v.time_limit_ms, memory_limit_mb=v.memory_limit_mb,
        starters={f.language: f.content for f in v.files if f.role == "starter"},
        examples=[PublicTest(name=t.name, call=t.call, args=t.args, expected=t.expected)
                  for t in v.tests if t.visibility is TestVisibility.PUBLIC],
        hidden_test_names=[t.name for t in v.tests if t.visibility is TestVisibility.HIDDEN],
    )


@public.get("/status")
async def execution_status(db: Db, request: Request) -> dict:
    return await service.execution_status(db, request.app.state.settings)


# ---------------------------------------------------------------- learner (local-only)


@router.get("/challenges/{slug}/state", response_model=ChallengeState)
async def challenge_state(slug: str, learner: CurrentLearner, db: Db) -> ChallengeState:
    ch = await service.get_challenge(db, slug)
    v = ch.current_version
    drafts = (await db.scalars(select(CodingDraft).where(
        CodingDraft.learner_id == learner.id, CodingDraft.challenge_id == ch.id))).all()
    subs = (await db.scalars(select(CodingSubmission).where(
        CodingSubmission.learner_id == learner.id, CodingSubmission.challenge_id == ch.id,
    ).order_by(CodingSubmission.passed.desc(), CodingSubmission.created_at.desc()))).all()
    solved = any(s.all_passed and s.verified for s in subs)
    hints_used = max((d.hints_used for d in drafts), default=0)
    latest = max(drafts, key=lambda d: d.updated_at, default=None)
    as_out = lambda d: DraftOut(language=d.language, code=d.code, revision=d.revision,  # noqa: E731
                                hints_used=d.hints_used, updated_at=d.updated_at)
    return ChallengeState(
        draft=as_out(latest) if latest else None,
        drafts={d.language: as_out(d) for d in drafts},
        hints=list(v.hints[:hints_used]),
        solved=solved,
        attempts=len(subs),
        best=_sub_out(subs[0], ch.slug, v.title, None) if subs else None,
        # Reference material only after a verified pass.
        reference_solutions={f.language: f.content for f in v.files if f.role == "reference"} if solved else None,
        misconceptions=list(v.misconceptions) if solved else None,
    )


@router.put("/challenges/{slug}/draft", response_model=DraftOut)
async def save_draft(slug: str, payload: DraftIn, learner: CurrentLearner, db: Db, request: Request) -> DraftOut:
    d = await service.save_draft(db, request.app.state.settings, learner, slug, payload.language,
                                 payload.code, payload.base_revision)
    return DraftOut(language=d.language, code=d.code, revision=d.revision, hints_used=d.hints_used,
                    updated_at=d.updated_at)


@router.post("/challenges/{slug}/hints")
async def hint(slug: str, payload: HintIn, learner: CurrentLearner, db: Db) -> dict:
    hints, total = await service.reveal_hint(db, learner, slug, payload.language)
    return {"hints": hints, "total": total}


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: JobIn, learner: CurrentLearner, db: Db, request: Request, response: Response) -> JobOut:
    job, created = await service.enqueue(
        db, request.app.state.settings, learner, slug=payload.challenge_slug, language=payload.language,
        code=payload.code, kind=payload.kind, idempotency_key=payload.idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return await _job_out(db, await service.load_job(db, learner, job.id))


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, learner: CurrentLearner, db: Db) -> JobOut:
    return await _job_out(db, await service.load_job(db, learner, job_id))


@router.get("/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    learner: CurrentLearner, db: Db, challenge: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SubmissionOut]:
    stmt = (
        select(CodingSubmission, CodingChallenge.slug, CodingChallengeVersion.title, CodingReview)
        .join(CodingChallenge, CodingChallenge.id == CodingSubmission.challenge_id)
        .join(CodingChallengeVersion, CodingChallengeVersion.id == CodingSubmission.version_id)
        .outerjoin(CodingReview, CodingReview.submission_id == CodingSubmission.id)
        .where(CodingSubmission.learner_id == learner.id)
        .order_by(CodingSubmission.created_at.desc()).limit(limit)
    )
    if challenge:
        stmt = stmt.where(CodingChallenge.slug == challenge)
    return [_sub_out(s, slug, title, r) for s, slug, title, r in (await db.execute(stmt)).all()]


async def _load_submission(db, learner, submission_id) -> tuple[CodingSubmission, CodingJob, CodingReview | None]:
    sub = await db.scalar(select(CodingSubmission).where(
        CodingSubmission.id == submission_id, CodingSubmission.learner_id == learner.id))
    if sub is None:
        raise NotFound("Submission not found")
    job = await service.load_job(db, learner, sub.job_id)
    review = await db.scalar(select(CodingReview).where(CodingReview.submission_id == sub.id)
                             .execution_options(populate_existing=True))
    return sub, job, review


def _review_out(r: CodingReview | None) -> ReviewOut | None:
    if r is None:
        return None
    return ReviewOut(status=r.status, error_code=r.error_code, review=r.review, provider=r.provider,
                     model=r.model, leak_blocked=r.leak_blocked, updated_at=r.updated_at)


async def _detail(db, learner, submission_id) -> SubmissionDetail:
    sub, job, review = await _load_submission(db, learner, submission_id)
    v = job.version
    solved = bool(await db.scalar(select(func.count()).select_from(CodingSubmission).where(
        CodingSubmission.learner_id == learner.id, CodingSubmission.challenge_id == sub.challenge_id,
        CodingSubmission.all_passed, CodingSubmission.verified)))
    reference = None
    if solved:
        await db.refresh(v, ["files"])
        reference = next((f.content for f in v.files if f.language == sub.language and f.role == "reference"), None)
    return SubmissionDetail(
        **_sub_out(sub, v.challenge.slug, v.title, review).model_dump(), code=job.code, results=_results(job),
        review=_review_out(review), reference_solution=reference,
        misconceptions=list(v.misconceptions) if solved else None,
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
async def get_submission(submission_id: uuid.UUID, learner: CurrentLearner, db: Db) -> SubmissionDetail:
    return await _detail(db, learner, submission_id)


@router.post("/submissions/{submission_id}/review", response_model=SubmissionDetail)
async def request_review(submission_id: uuid.UUID, learner: CurrentLearner, db: Db, llm: LLM,
                         request: Request) -> SubmissionDetail:
    """Idempotent: a completed review is returned as-is; an ungraded one is retried."""
    sub, job, review = await _load_submission(db, learner, submission_id)
    if review is not None and review.status is ReviewStatus.COMPLETED:
        return await _detail(db, learner, submission_id)
    if review is not None and review.status is ReviewStatus.PENDING:
        raise Conflict("A review is already in progress")
    # Every request reaches the model; cap them like submissions (ungraded reviews can otherwise be retried forever).
    recent = await db.scalar(
        select(func.count()).select_from(CodingReview)
        .join(CodingSubmission, CodingSubmission.id == CodingReview.submission_id)
        .where(CodingSubmission.learner_id == learner.id,
               CodingReview.updated_at > datetime.now(UTC) - timedelta(hours=1))
    ) or 0
    if recent >= request.app.state.settings.coding_submits_per_hour:
        raise service.RateLimited("AI review limit reached for this hour. Try again later.")
    if review is None:
        review = CodingReview(submission_id=sub.id, status=ReviewStatus.PENDING,
                              provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"),
                              prompt_version=review_mod.PROMPT_VERSION)
        db.add(review)
    else:
        review.status, review.error_code = ReviewStatus.PENDING, None
    await db.commit()

    v = job.version
    await db.refresh(v, ["files"])
    reference = next((f.content for f in v.files if f.language == sub.language and f.role == "reference"), None)
    status_, payload, error, attempts, leak = await review_mod.review_submission(
        llm, version=v, language=sub.language, code=job.code, results=job.results, tests=v.tests,
        reference=reference, reveal_reference=sub.all_passed and sub.verified, passed=sub.passed,
        total=sub.total, executed=sub.executed,
        max_repair_attempts=request.app.state.settings.llm_max_repair_attempts,
    )
    row = await db.scalar(select(CodingReview).where(CodingReview.id == review.id).with_for_update())
    row.status = ReviewStatus.COMPLETED if status_ == "completed" else ReviewStatus.UNGRADED
    row.review, row.error_code, row.llm_attempts, row.leak_blocked = payload, error, attempts, leak
    row.updated_at = datetime.now(UTC)
    await db.commit()
    return await _detail(db, learner, submission_id)


@router.get("/progress")
async def practical_progress(learner: CurrentLearner, db: Db, request: Request) -> dict:
    from app.mastery.service import sync_learner

    await sync_learner(db, learner.id, request.app.state.clock())
    rows = (await db.execute(
        select(Skill.slug, Skill.title, CodingChallenge.slug, CodingChallenge.difficulty)
        .join(CodingChallenge, CodingChallenge.skill_id == Skill.id)
        .where(CodingChallenge.is_active).order_by(Skill.position, CodingChallenge.position)
    )).all()
    subs = (await db.execute(
        select(CodingChallenge.slug, CodingSubmission.all_passed, CodingSubmission.verified, CodingSubmission.executed)
        .join(CodingChallenge, CodingChallenge.id == CodingSubmission.challenge_id)
        .where(CodingSubmission.learner_id == learner.id)
    )).all()
    solved = {s for s, ok, ver, _ in subs if ok and ver}
    attempted = {s for s, _, _, ex in subs if ex}
    practical = {
        slug: float(score) for slug, score in (await db.execute(
            select(Skill.slug, SkillMastery.practical_score).join(SkillMastery, SkillMastery.skill_id == Skill.id)
            .where(SkillMastery.learner_id == learner.id, SkillMastery.practical_score.is_not(None))
        )).all()
    }
    skills: dict[str, dict] = {}
    for skill_slug, title, ch_slug, difficulty in rows:
        entry = skills.setdefault(skill_slug, {"skill": {"slug": skill_slug, "title": title}, "total": 0,
                                               "solved": 0, "attempted": 0, "by_difficulty": {},
                                               "practical_score": practical.get(skill_slug)})
        entry["total"] += 1
        entry["solved"] += ch_slug in solved
        entry["attempted"] += ch_slug in attempted
        d = entry["by_difficulty"].setdefault(difficulty.value, {"total": 0, "solved": 0})
        d["total"] += 1
        d["solved"] += ch_slug in solved
    return {"skills": list(skills.values()), "submissions": len(subs),
            "verified_submissions": sum(1 for _, _, ver, _ in subs if ver)}
