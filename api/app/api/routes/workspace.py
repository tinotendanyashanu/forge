"""FORGE Workspace endpoints: projects, workspaces, files, snapshots, jobs,
submissions, AI reviews, simulated pull requests, exercises and progress.

The API never executes code: it snapshots workspaces and queues jobs for the
worker. Hidden tests' inputs and expected values, hidden checks and reference
solutions never leave the server (references only after a verified all-pass).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentLearner, Db, get_llm
from app.coding.service import execution_status
from app.core.config import Settings
from app.db.enums import JobKind, JobStatus, ReviewStatus, TestOutcome, TestVisibility
from app.db.models import (
    EngAuditEvent,
    EngJob,
    EngProject,
    EngProjectVersion,
    EngPrComment,
    EngPullRequest,
    EngReview,
    EngSubmission,
    EngWorkspace,
)
from app.services.errors import NotFound
from app.workspace import pr as pr_service
from app.workspace import progress as progress_mod
from app.workspace import service
from app.workspace.review import MODES
from app.workspace.service import files_of

public = APIRouter(prefix="/workspace", tags=["workspace"])
router = APIRouter(prefix="/workspace", tags=["workspace"])
LLM = Annotated[object, Depends(get_llm)]


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


Cfg = Annotated[Settings, Depends(_get_settings)]
ReviewMode = Literal["guided", "strict", "senior", "tech_lead"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- schemas


class ProjectSummary(BaseModel):
    slug: str
    title: str
    summary: str
    level: str
    task_type: str
    difficulty: str
    skill: dict
    stack: list[str]
    competencies: list[str]
    estimated_minutes: int
    version: int
    public_tests: int
    hidden_tests: int
    suites: list[str]


class PublicTestOut(BaseModel):
    name: str
    suite: str
    competency: str
    args: list[Any]
    expected: dict


class ExerciseOut(BaseModel):
    slug: str
    kind: str
    title: str
    prompt: str
    rubric: list[str]


class ProjectDetail(ProjectSummary):
    description: str
    architecture: str
    setup: str
    ticket: dict
    rubric: list[str]
    rubric_version: str
    prerequisites: list[str]
    hint_count: int
    time_limit_ms: int
    memory_limit_mb: int
    starter_files: list[str]
    public_tests_detail: list[PublicTestOut]
    hidden_test_names: list[str]
    public_check_sources: dict[str, str]
    exercises: list[ExerciseOut]


class FileMeta(BaseModel):
    path: str
    revision: int
    sha256: str
    size: int
    status: Literal["unchanged", "modified", "added"]


class FileOut(BaseModel):
    path: str
    content: str
    revision: int
    sha256: str
    workspace_revision: int


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    project_slug: str
    project_title: str
    level: str
    status: str
    version: int
    revision: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class WorkspaceDetail(WorkspaceSummary):
    files: list[FileMeta]
    deleted_files: list[str]
    hints: list[str]
    hint_count: int
    resets: int
    open_pull_request: uuid.UUID | None
    latest_job: "JobOut | None"
    project: ProjectDetail
    outdated: bool


class TestResultOut(BaseModel):
    name: str
    suite: str
    competency: str
    visibility: TestVisibility
    outcome: TestOutcome
    duration_ms: int | None
    message: str | None
    args: list[Any] | None = None
    expected: dict | None = None
    actual: str | None = None


class JobOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: JobKind
    status: JobStatus
    attempts: int
    snapshot_number: int
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


class ReviewOut(BaseModel):
    id: uuid.UUID
    mode: str
    status: ReviewStatus
    error_code: str | None
    review: dict | None
    provider: str
    model: str
    prompt_version: str
    rubric_version: str
    leak_blocked: bool
    updated_at: datetime


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    number: int
    snapshot_number: int
    passed: int
    total: int
    hidden_passed: int
    hidden_total: int
    all_passed: bool
    executed: bool
    verified: bool
    hints_used: int
    created_at: datetime


class SubmissionDetail(SubmissionSummary):
    project_slug: str
    results: list[TestResultOut]
    diff: list[dict]
    reviews: list[ReviewOut]
    reference_diff: list[dict] | None
    misconceptions: list[str] | None


class SnapshotOut(BaseModel):
    number: int
    kind: str
    label: str | None
    digest: str
    workspace_revision: int
    created_at: datetime
    files_changed: int


class SnapshotDetail(SnapshotOut):
    files: dict[str, str]
    diff: list[dict]


class CommentOut(BaseModel):
    id: uuid.UUID
    revision_number: int
    parent_id: uuid.UUID | None
    author: str
    kind: str
    path: str | None
    line: int | None
    body: str
    category: str | None
    severity: str | None
    resolved: bool
    answered: bool
    created_at: datetime


class RevisionOut(BaseModel):
    number: int
    note: str | None
    snapshot_number: int
    created_at: datetime
    job: JobOut
    submission: SubmissionSummary | None
    diff_from_previous: list[dict]


class PullRequestSummary(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_slug: str
    project_title: str
    title: str
    status: str
    revisions: int
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None


class PullRequestDetail(PullRequestSummary):
    description: str
    revision_list: list[RevisionOut]
    diff: list[dict]
    comments: list[CommentOut]
    reviews: list[ReviewOut]
    criteria: dict
    decision: dict | None
    ticket: dict


class ExerciseResponseOut(BaseModel):
    id: uuid.UUID
    exercise_slug: str
    body: str
    status: str
    error_code: str | None
    score: float | None
    eligible: bool
    evaluation: dict | None
    created_at: datetime


class StatusOut(BaseModel):
    execution: dict
    llm: dict
    modes: dict[str, str]


# -- inputs


class FileIn(_In):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=65_536)
    base_revision: int | None = Field(default=None, ge=1)


class FileDeleteIn(_In):
    path: str = Field(min_length=1, max_length=200)
    base_revision: int = Field(ge=1)


class SnapshotIn(_In):
    label: str | None = Field(default=None, max_length=120)


class RevisionGuardIn(_In):
    expected_revision: int = Field(ge=1)


class JobIn(_In):
    kind: JobKind
    idempotency_key: uuid.UUID


class ReviewIn(_In):
    mode: ReviewMode = "senior"


class PullIn(_In):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=20, max_length=8000)
    idempotency_key: uuid.UUID


class RevisionIn(_In):
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: uuid.UUID


class CommentIn(_In):
    body: str = Field(min_length=1, max_length=4000)
    path: str | None = Field(default=None, max_length=200)
    line: int | None = Field(default=None, ge=1)
    parent_id: uuid.UUID | None = None
    client_id: uuid.UUID


class ExerciseIn(_In):
    body: str = Field(min_length=40, max_length=12_000)
    client_id: uuid.UUID


# ---------------------------------------------------------------- mapping


def _summary(p: EngProject) -> ProjectSummary:
    v = p.current_version
    return _summary_for(p, v)


def _summary_for(p: EngProject, v: EngProjectVersion) -> ProjectSummary:
    c = v.content
    return ProjectSummary(
        slug=p.slug, title=v.title, summary=v.summary, level=p.level, task_type=p.task_type,
        difficulty=p.difficulty.value, skill={"slug": p.skill.slug, "title": p.skill.title}, stack=c["stack"],
        competencies=c["competencies"], estimated_minutes=c["estimated_minutes"], version=v.number,
        public_tests=sum(t.visibility is TestVisibility.PUBLIC for t in v.tests),
        hidden_tests=sum(t.visibility is TestVisibility.HIDDEN for t in v.tests), suites=v.suites,
    )


def _detail(p: EngProject, v: EngProjectVersion) -> ProjectDetail:
    c = v.content
    return ProjectDetail(
        **_summary_for(p, v).model_dump(),
        description=c["description"], architecture=c["architecture"], setup=c["setup"], ticket=c["ticket"],
        rubric=c["rubric"], rubric_version=v.rubric_version, prerequisites=c["prerequisites"],
        hint_count=len(c["hints"]), time_limit_ms=v.time_limit_ms, memory_limit_mb=v.memory_limit_mb,
        starter_files=sorted(files_of(v, "starter")),
        public_tests_detail=[PublicTestOut(name=t.name, suite=t.suite, competency=t.competency, args=t.args,
                                           expected=t.expected)
                             for t in v.tests if t.visibility is TestVisibility.PUBLIC],
        hidden_test_names=[t.name for t in v.tests if t.visibility is TestVisibility.HIDDEN],
        # Public checks are part of the public contract; hidden checks never leave the server.
        public_check_sources={f.path.split(":")[0]: f.content for f in v.files
                              if f.role == "check" and f.path.endswith(":public")},
        exercises=[ExerciseOut(**{k: e[k] for k in ("slug", "kind", "title", "prompt", "rubric")})
                   for e in c.get("exercises", [])],
    )


def _results(job: EngJob) -> list[TestResultOut]:
    tests = {t.id: t for t in job.version.tests}
    out = []
    for r in job.results:
        t = tests[r.test_id]
        hidden = t.visibility is TestVisibility.HIDDEN
        out.append(TestResultOut(
            name=t.name, suite=t.suite, competency=t.competency, visibility=t.visibility, outcome=r.outcome,
            duration_ms=r.duration_ms, message=r.message,
            args=None if hidden else t.args, expected=None if hidden else t.expected, actual=None if hidden else r.actual,
        ))
    return out


async def _job_out(db, job: EngJob) -> JobOut:
    sub = await service.submission_for_job(db, job.id)
    done = job.status is JobStatus.COMPLETED
    return JobOut(
        id=job.id, workspace_id=job.workspace_id, kind=job.kind, status=job.status, attempts=job.attempts,
        snapshot_number=job.snapshot.number, error_code=job.error_code, error_message=job.error_message,
        backend=job.backend, sandbox_verified=job.sandbox_verified, created_at=job.created_at,
        finished_at=job.finished_at,
        passed=sum(r.outcome is TestOutcome.PASSED for r in job.results) if done else None,
        total=len(job.results) if done else None,
        results=_results(job) if done else [], submission_id=sub.id if sub else None,
    )


def _sub_summary(s: EngSubmission, snapshot_number: int) -> SubmissionSummary:
    return SubmissionSummary(
        id=s.id, job_id=s.job_id, workspace_id=s.workspace_id, number=s.number, snapshot_number=snapshot_number,
        passed=s.passed, total=s.total, hidden_passed=s.hidden_passed, hidden_total=s.hidden_total,
        all_passed=s.all_passed, executed=s.executed, verified=s.verified, hints_used=s.hints_used,
        created_at=s.created_at,
    )


def _review_out(r: EngReview) -> ReviewOut:
    return ReviewOut(id=r.id, mode=r.mode, status=r.status, error_code=r.error_code, review=r.review,
                     provider=r.provider, model=r.model, prompt_version=r.prompt_version,
                     rubric_version=r.rubric_version, leak_blocked=r.leak_blocked, updated_at=r.updated_at)


def _ws_summary(ws: EngWorkspace) -> WorkspaceSummary:
    return WorkspaceSummary(
        id=ws.id, project_slug=ws.project.slug, project_title=ws.version.title, level=ws.project.level,
        status=ws.status, version=ws.version.number, revision=ws.revision, created_at=ws.created_at,
        updated_at=ws.updated_at, completed_at=ws.completed_at,
    )


async def _ws_detail(db, ws: EngWorkspace) -> WorkspaceDetail:
    starter = files_of(ws.version, "starter")
    files = [FileMeta(path=f.path, revision=f.revision, sha256=f.sha256, size=len(f.content.encode()),
                      status="added" if f.path not in starter else "unchanged" if starter[f.path] == f.content
                      else "modified") for f in ws.files]
    present = {f.path for f in ws.files}
    open_pr = await db.scalar(select(EngPullRequest.id).where(EngPullRequest.workspace_id == ws.id,
                                                              EngPullRequest.status.in_(pr_service.OPEN)))
    latest = await db.scalar(select(EngJob.id).where(EngJob.workspace_id == ws.id)
                             .order_by(EngJob.created_at.desc()).limit(1))
    project = await db.scalar(select(EngProject).where(EngProject.id == ws.project_id))
    hints = ws.version.content["hints"]
    return WorkspaceDetail(
        **_ws_summary(ws).model_dump(), files=files, deleted_files=sorted(set(starter) - present),
        hints=hints[: ws.hints_used], hint_count=len(hints), resets=ws.resets, open_pull_request=open_pr,
        latest_job=await _job_out(db, await service.load_job(db, _Owner(ws.learner_id), latest)) if latest else None,
        project=_detail(ws.project, ws.version), outdated=project.current_version_id != ws.version_id,
    )


class _Owner:
    """Minimal learner stand-in for loaders called with an already-authorised owner id."""

    def __init__(self, learner_id: uuid.UUID) -> None:
        self.id = learner_id


# ---------------------------------------------------------------- public


@public.get("/status")
async def workspace_status(db: Db, llm: LLM, settings: Cfg) -> StatusOut:
    return StatusOut(
        execution=await execution_status(db, settings),
        llm={"provider": getattr(llm, "name", "disabled"), "model": getattr(llm, "model", ""),
             "configured": getattr(llm, "name", "disabled") != "disabled"},
        modes={k: v["title"] for k, v in MODES.items()},
    )


@public.get("/projects")
async def list_projects(db: Db) -> list[ProjectSummary]:
    return [_summary(p) for p in await service.list_projects(db)]


@public.get("/projects/{slug}")
async def project_detail(db: Db, slug: str) -> ProjectDetail:
    p = await service.get_project(db, slug)
    return _detail(p, p.current_version)


# ---------------------------------------------------------------- workspaces


@router.get("/workspaces")
async def my_workspaces(db: Db, learner: CurrentLearner) -> list[WorkspaceSummary]:
    return [_ws_summary(w) for w in await service.list_workspaces(db, learner)]


@router.post("/projects/{slug}/workspace")
async def open_workspace(db: Db, learner: CurrentLearner, slug: str, response: Response) -> WorkspaceDetail:
    ws, created = await service.open_workspace(db, learner, slug)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return await _ws_detail(db, ws)


@router.get("/workspaces/{workspace_id}")
async def workspace_detail(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> WorkspaceDetail:
    return await _ws_detail(db, await service.load_workspace(db, learner, workspace_id))


@router.get("/workspaces/{workspace_id}/files/{path:path}")
async def read_file(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, path: str) -> FileOut:
    ws = await service.load_workspace(db, learner, workspace_id)
    f = next((f for f in ws.files if f.path == path), None)
    if f is None:
        raise NotFound("File not found")
    return FileOut(path=f.path, content=f.content, revision=f.revision, sha256=f.sha256, workspace_revision=ws.revision)


@router.get("/workspaces/{workspace_id}/original/{path:path}")
async def read_original(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, path: str) -> dict:
    ws = await service.load_workspace(db, learner, workspace_id)
    starter = files_of(ws.version, "starter")
    if path not in starter:
        raise NotFound("Not part of the original project")
    return {"path": path, "content": starter[path]}


@router.put("/workspaces/{workspace_id}/files")
async def write_file(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, body: FileIn) -> FileOut:
    f = await service.write_file(db, learner, workspace_id, body.path, body.content, body.base_revision)
    ws = await db.scalar(select(EngWorkspace).where(EngWorkspace.id == workspace_id))
    return FileOut(path=f.path, content=f.content, revision=f.revision, sha256=f.sha256, workspace_revision=ws.revision)


@router.post("/workspaces/{workspace_id}/files/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, body: FileDeleteIn) -> Response:
    await service.delete_file(db, learner, workspace_id, body.path, body.base_revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workspaces/{workspace_id}/diff")
async def workspace_diff(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID,
                         against: int | None = None) -> list[dict]:
    """Current files vs the original project, or vs snapshot ``against``."""
    ws = await service.load_workspace(db, learner, workspace_id)
    base = (dict((await service.get_snapshot(db, learner, workspace_id, against)).files) if against
            else files_of(ws.version, "starter"))
    return service.diff_trees(base, service.current_files(ws))


@router.post("/workspaces/{workspace_id}/reset")
async def reset(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, body: RevisionGuardIn) -> WorkspaceDetail:
    return await _ws_detail(db, await service.reset_workspace(db, learner, workspace_id, body.expected_revision))


@router.post("/workspaces/{workspace_id}/hints")
async def hint(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> dict:
    hints, total = await service.reveal_hint(db, learner, workspace_id)
    return {"hints": hints, "total": total}


@router.get("/workspaces/{workspace_id}/history")
async def history(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> list[dict]:
    await service.load_workspace(db, learner, workspace_id)
    rows = await db.scalars(select(EngAuditEvent).where(EngAuditEvent.workspace_id == workspace_id,
                                                        EngAuditEvent.learner_id == learner.id)
                            .order_by(EngAuditEvent.created_at.desc()).limit(200))
    return [{"action": r.action, "detail": r.detail, "at": r.created_at} for r in rows]


# ---------------------------------------------------------------- snapshots


def _snap_out(s, original: dict[str, str]) -> SnapshotOut:
    return SnapshotOut(number=s.number, kind=s.kind, label=s.label, digest=s.digest,
                       workspace_revision=s.workspace_revision, created_at=s.created_at,
                       files_changed=len(service.diff_trees(original, dict(s.files))))


@router.get("/workspaces/{workspace_id}/snapshots")
async def snapshots(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> list[SnapshotOut]:
    ws = await service.load_workspace(db, learner, workspace_id)
    original = files_of(ws.version, "starter")
    return [_snap_out(s, original) for s in await service.list_snapshots(db, learner, workspace_id)]


@router.post("/workspaces/{workspace_id}/snapshots", status_code=status.HTTP_201_CREATED)
async def create_snapshot(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, body: SnapshotIn) -> SnapshotOut:
    snap = await service.create_snapshot(db, learner, workspace_id, body.label)
    ws = await service.load_workspace(db, learner, workspace_id)
    return _snap_out(snap, files_of(ws.version, "starter"))


@router.get("/workspaces/{workspace_id}/snapshots/{number}")
async def snapshot_detail(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, number: int) -> SnapshotDetail:
    ws = await service.load_workspace(db, learner, workspace_id)
    snap = await service.get_snapshot(db, learner, workspace_id, number)
    original = files_of(ws.version, "starter")
    return SnapshotDetail(**_snap_out(snap, original).model_dump(), files=dict(snap.files),
                          diff=service.diff_trees(original, dict(snap.files)))


@router.post("/workspaces/{workspace_id}/snapshots/{number}/restore")
async def restore(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID, number: int,
                  body: RevisionGuardIn) -> WorkspaceDetail:
    return await _ws_detail(db, await service.restore_snapshot(db, learner, workspace_id, number, body.expected_revision))


# ---------------------------------------------------------------- jobs & submissions


@router.post("/workspaces/{workspace_id}/jobs")
async def create_job(db: Db, settings: Cfg, learner: CurrentLearner, workspace_id: uuid.UUID, body: JobIn,
                     response: Response) -> JobOut:
    job, created = await service.enqueue(db, settings, learner, workspace_id, kind=body.kind,
                                         idempotency_key=body.idempotency_key)
    response.status_code = status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    return await _job_out(db, await service.load_job(db, learner, job.id))


@router.get("/jobs/{job_id}")
async def get_job(db: Db, learner: CurrentLearner, job_id: uuid.UUID) -> JobOut:
    return await _job_out(db, await service.load_job(db, learner, job_id))


@router.get("/workspaces/{workspace_id}/submissions")
async def submissions(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> list[SubmissionSummary]:
    await service.load_workspace(db, learner, workspace_id)
    rows = await db.scalars(select(EngSubmission).where(EngSubmission.workspace_id == workspace_id,
                                                        EngSubmission.learner_id == learner.id)
                            .order_by(EngSubmission.number.desc()))
    out = []
    for s in rows.all():
        snap = await pr_service.snapshot_by_id(db, s.snapshot_id)
        out.append(_sub_summary(s, snap.number))
    return out


async def _load_submission(db, learner, submission_id: uuid.UUID) -> EngSubmission:
    s = await db.scalar(select(EngSubmission).where(EngSubmission.id == submission_id,
                                                    EngSubmission.learner_id == learner.id))
    if s is None:
        raise NotFound("Submission not found")
    return s


@router.get("/submissions/{submission_id}")
async def submission_detail(db: Db, learner: CurrentLearner, submission_id: uuid.UUID) -> SubmissionDetail:
    s = await _load_submission(db, learner, submission_id)
    job = await service.load_job(db, learner, s.job_id)
    ws = await service.load_workspace(db, learner, s.workspace_id)
    original = files_of(ws.version, "starter")
    reviews = (await db.scalars(select(EngReview).where(EngReview.submission_id == s.id)
                                .order_by(EngReview.created_at))).all()
    solved = s.all_passed and s.verified
    return SubmissionDetail(
        **_sub_summary(s, job.snapshot.number).model_dump(), project_slug=ws.project.slug, results=_results(job),
        diff=service.diff_trees(original, dict(job.snapshot.files)), reviews=[_review_out(r) for r in reviews],
        # The reference is revealed only after a verified all-pass: the attempt is finished.
        reference_diff=service.diff_trees(original, {**original, **files_of(job.version, "reference")})
        if solved else None,
        misconceptions=ws.version.content["misconceptions"] if solved else None,
    )


@router.post("/submissions/{submission_id}/reviews")
async def review_submission(db: Db, settings: Cfg, learner: CurrentLearner, llm: LLM, submission_id: uuid.UUID,
                            body: ReviewIn) -> ReviewOut:
    s = await _load_submission(db, learner, submission_id)
    return _review_out(await pr_service.review_submission(db, settings, llm, learner, s, mode=body.mode))


# ---------------------------------------------------------------- pull requests


async def _pr_summary(pr: EngPullRequest) -> PullRequestSummary:
    return PullRequestSummary(
        id=pr.id, workspace_id=pr.workspace_id, project_slug=pr.workspace.project.slug,
        project_title=pr.workspace.version.title if "version" in pr.workspace.__dict__ else pr.workspace.project.slug,
        title=pr.title, status=pr.status, revisions=len(pr.revisions), created_at=pr.created_at,
        updated_at=pr.updated_at, decided_at=pr.decided_at,
    )


async def _pr_detail(db, learner, pr: EngPullRequest, settings: Settings) -> PullRequestDetail:
    original = files_of(pr.workspace.version, "starter")
    revisions, previous = [], original
    sub_ids = []
    for r in pr.revisions:
        job = await service.load_job(db, learner, r.job_id)
        sub = await service.submission_for_job(db, job.id)
        if sub:
            sub_ids.append(sub.id)
        files = dict(r.snapshot.files)
        revisions.append(RevisionOut(
            number=r.number, note=r.note, snapshot_number=r.snapshot.number, created_at=r.created_at,
            job=await _job_out(db, job), submission=_sub_summary(sub, r.snapshot.number) if sub else None,
            diff_from_previous=service.diff_trees(previous, files),
        ))
        previous = files
    comments = await pr_service.comments_for(db, pr.id)
    answered = {c.parent_id for c in comments if c.kind == "response"}
    reviews = (await db.scalars(select(EngReview).where(EngReview.submission_id.in_(sub_ids or [uuid.uuid4()]))
                                .order_by(EngReview.created_at))).all()
    return PullRequestDetail(
        **(await _pr_summary(pr)).model_dump(), description=pr.description, revision_list=revisions,
        diff=service.diff_trees(original, dict(pr.revisions[-1].snapshot.files)),
        comments=[_comment_out(c, answered) for c in comments], reviews=[_review_out(r) for r in reviews],
        criteria=await pr_service.evaluate_criteria(db, settings, pr), decision=pr.decision,
        ticket=pr.workspace.version.content["ticket"],
    )


def _comment_out(c: EngPrComment, answered: set) -> CommentOut:
    return CommentOut(id=c.id, revision_number=c.revision_number, parent_id=c.parent_id, author=c.author, kind=c.kind,
                      path=c.path, line=c.line, body=c.body, category=c.category, severity=c.severity,
                      resolved=c.resolved, answered=c.id in answered, created_at=c.created_at)


@router.get("/pulls")
async def list_pulls(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID | None = None) -> list[PullRequestSummary]:
    return [await _pr_summary(p) for p in await pr_service.list_prs(db, learner, workspace_id)]


@router.post("/workspaces/{workspace_id}/pulls")
async def open_pull(db: Db, settings: Cfg, learner: CurrentLearner, workspace_id: uuid.UUID, body: PullIn,
                    response: Response) -> PullRequestDetail:
    pr, created = await pr_service.open_pr(db, settings, learner, workspace_id, title=body.title,
                                           description=body.description, idempotency_key=body.idempotency_key)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return await _pr_detail(db, learner, pr, settings)


@router.get("/pulls/{pr_id}")
async def pull_detail(db: Db, settings: Cfg, learner: CurrentLearner, pr_id: uuid.UUID) -> PullRequestDetail:
    return await _pr_detail(db, learner, await pr_service.load_pr(db, learner, pr_id), settings)


@router.post("/pulls/{pr_id}/revisions")
async def push_revision(db: Db, settings: Cfg, learner: CurrentLearner, pr_id: uuid.UUID, body: RevisionIn) -> PullRequestDetail:
    pr = await pr_service.push_revision(db, settings, learner, pr_id, note=body.note,
                                        idempotency_key=body.idempotency_key)
    return await _pr_detail(db, learner, pr, settings)


@router.post("/pulls/{pr_id}/comments", status_code=status.HTTP_201_CREATED)
async def comment(db: Db, learner: CurrentLearner, pr_id: uuid.UUID, body: CommentIn) -> CommentOut:
    c = await pr_service.add_comment(db, learner, pr_id, body=body.body, path=body.path, line=body.line,
                                     parent_id=body.parent_id, client_id=body.client_id)
    return _comment_out(c, set())


@router.post("/pulls/{pr_id}/reviews")
async def review_pull(db: Db, settings: Cfg, learner: CurrentLearner, llm: LLM, pr_id: uuid.UUID, body: ReviewIn) -> ReviewOut:
    return _review_out(await pr_service.review_pr(db, settings, llm, learner, pr_id, body.mode))


@router.post("/pulls/{pr_id}/decision")
async def decide(db: Db, settings: Cfg, learner: CurrentLearner, pr_id: uuid.UUID) -> PullRequestDetail:
    return await _pr_detail(db, learner, await pr_service.decide(db, settings, learner, pr_id), settings)


@router.post("/pulls/{pr_id}/close")
async def close(db: Db, settings: Cfg, learner: CurrentLearner, pr_id: uuid.UUID) -> PullRequestDetail:
    return await _pr_detail(db, learner, await pr_service.close_pr(db, learner, pr_id), settings)


# ---------------------------------------------------------------- exercises & progress


def _exercise_out(r) -> ExerciseResponseOut:
    return ExerciseResponseOut(id=r.id, exercise_slug=r.exercise_slug, body=r.body, status=r.status,
                               error_code=r.error_code, score=float(r.score) if r.score is not None else None,
                               eligible=r.eligible, evaluation=r.evaluation, created_at=r.created_at)


@router.get("/workspaces/{workspace_id}/exercises")
async def exercise_responses(db: Db, learner: CurrentLearner, workspace_id: uuid.UUID) -> list[ExerciseResponseOut]:
    return [_exercise_out(r) for r in await pr_service.list_exercise_responses(db, learner, workspace_id)]


@router.post("/workspaces/{workspace_id}/exercises/{slug}", status_code=status.HTTP_201_CREATED)
async def submit_exercise(db: Db, settings: Cfg, learner: CurrentLearner, llm: LLM, workspace_id: uuid.UUID, slug: str,
                          body: ExerciseIn) -> ExerciseResponseOut:
    r = await pr_service.submit_exercise(db, settings, llm, learner, workspace_id, slug=slug, body=body.body,
                                         client_id=body.client_id)
    return _exercise_out(r)


@router.get("/progress")
async def progress(db: Db, learner: CurrentLearner) -> dict:
    return await progress_mod.progress(db, learner.id)


@router.get("/portfolio")
async def portfolio(db: Db, learner: CurrentLearner) -> dict:
    return await progress_mod.engineering_portfolio(db, learner.id)


__all__ = ["public", "router"]
