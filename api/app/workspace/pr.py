"""Simulated pull requests, AI reviews and collaboration exercises.

Internal and educational: nothing is pushed to any external repository.

Approval criteria (deterministic, evaluated by ``decide``; documented in
docs/workspace.md and returned with every decision):

1. ``verified_tests``  The latest revision ran in a sandbox that passed its
   security self-check (not the mock runner).
2. ``all_tests_pass``  Every public and hidden test passes on the latest revision.
3. ``review_completed`` An AI review of the latest revision exists. Waived (and
   labelled as waived) when no LLM provider is configured.
4. ``feedback_answered`` Every reviewer request (requested change, blocking
   finding or question) has a learner response.

The AI's own recommendation is shown but is never a criterion: a PR can't be
approved because a model liked it, and can't be blocked by a model alone
beyond requiring the learner to respond.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.career.reviewer import review as review_written
from app.coding.service import RateLimited
from app.core.config import Settings
from app.db.enums import JobKind, JobStatus, ReviewStatus
from app.db.models import (
    EngExerciseResponse,
    EngJob,
    EngProjectVersion,
    EngPrComment,
    EngPrRevision,
    EngPullRequest,
    EngReview,
    EngSnapshot,
    EngSubmission,
    EngWorkspace,
    Learner,
)
from app.services.errors import Conflict, NotFound, Unprocessable
from app.workspace import review as review_mod
from app.workspace import service
from app.workspace.service import audit, current_files, files_of, tree_digest

OPEN = ("open", "changes_requested")
EXERCISE_PROMPT_VERSION = "eng-exercise-v1"


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- loading


async def load_pr(db: AsyncSession, learner: Learner, pr_id: uuid.UUID, *, lock: bool = False) -> EngPullRequest:
    stmt = (select(EngPullRequest)
            .where(EngPullRequest.id == pr_id, EngPullRequest.learner_id == learner.id)
            .options(selectinload(EngPullRequest.revisions).selectinload(EngPrRevision.snapshot),
                     selectinload(EngPullRequest.revisions).selectinload(EngPrRevision.job),
                     selectinload(EngPullRequest.workspace).selectinload(EngWorkspace.version)
                     .selectinload(EngProjectVersion.files),
                     selectinload(EngPullRequest.workspace).selectinload(EngWorkspace.version)
                     .selectinload(EngProjectVersion.tests),
                     selectinload(EngPullRequest.workspace).selectinload(EngWorkspace.project))
            .execution_options(populate_existing=True))
    if lock:
        stmt = stmt.with_for_update(of=EngPullRequest)
    pr = await db.scalar(stmt)
    if pr is None:
        raise NotFound("Pull request not found")
    return pr


async def list_prs(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID | None = None) -> list[EngPullRequest]:
    stmt = (select(EngPullRequest).where(EngPullRequest.learner_id == learner.id)
            .options(selectinload(EngPullRequest.revisions),
                     selectinload(EngPullRequest.workspace).selectinload(EngWorkspace.project))
            .order_by(EngPullRequest.created_at.desc()))
    if workspace_id:
        stmt = stmt.where(EngPullRequest.workspace_id == workspace_id)
    return list((await db.scalars(stmt)).all())


async def comments_for(db: AsyncSession, pr_id: uuid.UUID) -> list[EngPrComment]:
    return list((await db.scalars(select(EngPrComment).where(EngPrComment.pr_id == pr_id)
                                  .order_by(EngPrComment.created_at, EngPrComment.id))).all())


async def submission_for(db: AsyncSession, job_id: uuid.UUID) -> EngSubmission | None:
    return await db.scalar(select(EngSubmission).where(EngSubmission.job_id == job_id))


# ---------------------------------------------------------------- opening & revisions


async def open_pr(db: AsyncSession, settings: Settings, learner: Learner, workspace_id: uuid.UUID, *,
                  title: str, description: str, idempotency_key: uuid.UUID) -> tuple[EngPullRequest, bool]:
    await service.load_workspace(db, learner, workspace_id)  # ownership
    open_one = await db.scalar(select(EngPullRequest.id).where(EngPullRequest.workspace_id == workspace_id,
                                                               EngPullRequest.status.in_(OPEN)))
    if open_one:
        # A retry of the same request (same key) returns the PR it created; anything else conflicts.
        pr = await load_pr(db, learner, open_one)
        keyed = await db.scalar(select(EngJob.id).where(EngJob.learner_id == learner.id,
                                                        EngJob.idempotency_key == idempotency_key))
        if keyed is not None and keyed == pr.revisions[0].job_id:
            return pr, False
        raise Conflict("This workspace already has an open pull request. Push a revision to it instead.")
    job, _ = await service.enqueue(db, settings, learner, workspace_id, kind=JobKind.SUBMIT,
                                   idempotency_key=idempotency_key, snapshot_kind="pull_request")
    pr = EngPullRequest(learner_id=learner.id, workspace_id=workspace_id, title=title.strip(),
                        description=description.strip(), status="open")
    db.add(pr)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("This workspace already has an open pull request.") from None
    db.add(EngPrRevision(pr_id=pr.id, number=1, snapshot_id=job.snapshot_id, job_id=job.id))
    db.add(EngPrComment(pr_id=pr.id, revision_number=1, author="system", kind="comment",
                        body="Pull request opened. Automated checks (public and hidden tests) are running."))
    await audit(db, learner.id, workspace_id, "pr.opened", pr_id=str(pr.id))
    await db.commit()
    return await load_pr(db, learner, pr.id), True


async def push_revision(db: AsyncSession, settings: Settings, learner: Learner, pr_id: uuid.UUID, *,
                        note: str | None, idempotency_key: uuid.UUID) -> EngPullRequest:
    pr = await load_pr(db, learner, pr_id)
    if pr.status not in OPEN:
        raise Conflict(f"This pull request is {pr.status}")
    already = next((r for r in pr.revisions if r.job.idempotency_key == idempotency_key), None)
    if already:
        return pr
    latest = pr.revisions[-1]
    ws = await service.load_workspace(db, learner, pr.workspace_id)
    if tree_digest(current_files(ws)) == latest.snapshot.digest:
        raise Conflict(f"No changes since revision {latest.number}. Edit the code before pushing a revision.")
    job, _ = await service.enqueue(db, settings, learner, pr.workspace_id, kind=JobKind.SUBMIT,
                                   idempotency_key=idempotency_key, snapshot_kind="pull_request")
    pr = await load_pr(db, learner, pr_id, lock=True)
    number = pr.revisions[-1].number + 1
    db.add(EngPrRevision(pr_id=pr.id, number=number, snapshot_id=job.snapshot_id, job_id=job.id,
                         note=(note or "").strip()[:2000] or None))
    db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="system", kind="comment",
                        body=f"Revision {number} pushed. Checks are running."
                             + (f"\n\n{note.strip()[:2000]}" if note and note.strip() else "")))
    pr.status, pr.updated_at = "open", _now()
    await audit(db, learner.id, pr.workspace_id, "pr.revision", pr_id=str(pr.id), number=number)
    await db.commit()
    return await load_pr(db, learner, pr_id)


async def close_pr(db: AsyncSession, learner: Learner, pr_id: uuid.UUID) -> EngPullRequest:
    pr = await load_pr(db, learner, pr_id, lock=True)
    if pr.status not in OPEN:
        raise Conflict(f"This pull request is already {pr.status}")
    pr.status, pr.updated_at, pr.decided_at = "closed", _now(), _now()
    db.add(EngPrComment(pr_id=pr.id, revision_number=pr.revisions[-1].number, author="system", kind="comment",
                        body="Pull request closed without merging."))
    await audit(db, learner.id, pr.workspace_id, "pr.closed", pr_id=str(pr.id))
    await db.commit()
    return await load_pr(db, learner, pr_id)


# ---------------------------------------------------------------- comments


async def add_comment(db: AsyncSession, learner: Learner, pr_id: uuid.UUID, *, body: str, path: str | None,
                      line: int | None, parent_id: uuid.UUID | None, client_id: uuid.UUID) -> EngPrComment:
    pr = await load_pr(db, learner, pr_id, lock=True)
    existing = await db.scalar(select(EngPrComment).where(EngPrComment.pr_id == pr.id,
                                                          EngPrComment.client_id == client_id))
    if existing:
        return existing
    if pr.status not in OPEN:
        raise Conflict(f"This pull request is {pr.status}")
    body = body.strip()
    if not body:
        raise Unprocessable("Comment is empty")
    kind = "comment"
    if parent_id is not None:
        parent = await db.scalar(select(EngPrComment).where(EngPrComment.id == parent_id, EngPrComment.pr_id == pr.id))
        if parent is None:
            raise NotFound("Comment not found")
        if parent.parent_id is not None:
            raise Unprocessable("Reply to the original comment, not to a reply")
        kind = "response"
        path, line = parent.path, parent.line
        if parent.author == "reviewer":
            parent.resolved = True
    elif path is not None:
        latest = pr.revisions[-1].snapshot.files
        path = path if path in latest else None
        if path is None:
            raise Unprocessable("That file is not part of the latest revision")
        if line is not None and not 1 <= line <= max(1, len(latest[path].splitlines())):
            raise Unprocessable("Line is outside the file")
    else:
        line = None
    c = EngPrComment(pr_id=pr.id, revision_number=pr.revisions[-1].number, parent_id=parent_id, author="learner",
                     kind=kind, path=path, line=line, body=body[:4000], client_id=client_id)
    db.add(c)
    pr.updated_at = _now()
    await db.commit()
    return c


# ---------------------------------------------------------------- AI review


async def _llm_budget(db: AsyncSession, settings: Settings, learner: Learner) -> None:
    since = _now() - timedelta(hours=1)
    reviews = await db.scalar(select(func.count()).select_from(EngReview).where(
        EngReview.learner_id == learner.id, EngReview.updated_at > since, EngReview.llm_attempts > 0)) or 0
    exercises = await db.scalar(select(func.count()).select_from(EngExerciseResponse).where(
        EngExerciseResponse.learner_id == learner.id, EngExerciseResponse.created_at > since)) or 0
    if reviews + exercises >= settings.workspace_llm_calls_per_hour:
        raise RateLimited(f"AI review limit reached ({settings.workspace_llm_calls_per_hour} per hour).")


def reference_changes(version: EngProjectVersion) -> str:
    """Lines the reference solution adds or changes: the material a review must not reveal early."""
    starter, ref = files_of(version, "starter"), files_of(version, "reference")
    out = []
    for path, text in ref.items():
        old = set((starter.get(path) or "").splitlines())
        out += [line for line in text.splitlines() if line.strip() and line not in old]
    return "\n".join(out)


async def review_submission(db: AsyncSession, settings: Settings, llm, learner: Learner, submission: EngSubmission,
                            *, mode: str, pr: EngPullRequest | None = None) -> EngReview:
    """Idempotent per (submission, mode); an ungraded review can be retried."""
    rv = await db.scalar(select(EngReview).where(EngReview.submission_id == submission.id, EngReview.mode == mode)
                         .with_for_update())
    if rv is not None and rv.status is not ReviewStatus.UNGRADED:
        return rv
    await _llm_budget(db, settings, learner)
    ws = await service.load_workspace(db, learner, submission.workspace_id)
    job = await service.load_job(db, learner, submission.job_id)
    version = job.version
    version = await db.scalar(select(EngProjectVersion).where(EngProjectVersion.id == version.id)
                              .options(selectinload(EngProjectVersion.files), selectinload(EngProjectVersion.tests)))
    original = files_of(version, "starter")
    files = dict(job.snapshot.files)
    changed = [d["path"] for d in service.diff_trees(original, files) if d["status"] != "deleted"]
    replies: list[str] = []
    if pr is not None:
        replies = [c.body for c in await comments_for(db, pr.id) if c.author == "learner"]
    status, review, error, attempts, leak, provider, model = await review_mod.review_submission(
        llm, mode=mode, content=version.content, files=files, diff_text=service.unified_text(original, files),
        changed=changed, results=job.results, tests=version.tests, reference_changes=reference_changes(version),
        reveal_reference=submission.all_passed and submission.verified, passed=submission.passed,
        total=submission.total, executed=submission.executed, verified=submission.verified,
        pr_description=pr.description if pr else None, replies=replies,
        repairs=settings.llm_max_repair_attempts,
    )
    if rv is None:
        rv = EngReview(submission_id=submission.id, learner_id=learner.id, mode=mode)
        db.add(rv)
    rv.status = ReviewStatus.COMPLETED if status == "completed" else ReviewStatus.UNGRADED
    rv.error_code, rv.review, rv.provider, rv.model = error, review, provider or "?", model or "?"
    rv.prompt_version, rv.rubric_version = review_mod.PROMPT_VERSION, version.rubric_version
    rv.llm_attempts, rv.leak_blocked, rv.updated_at = max(1, attempts), leak, _now()
    await db.flush()
    await audit(db, learner.id, ws.id, "review.requested", mode=mode, status=rv.status.value)
    if pr is not None and rv.status is ReviewStatus.COMPLETED:
        await _post_review_comments(db, pr, rv)
    await db.commit()
    return rv


async def _post_review_comments(db: AsyncSession, pr: EngPullRequest, rv: EngReview) -> None:
    r = rv.review or {}
    number = pr.revisions[-1].number
    db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="reviewer", kind="comment", review_id=rv.id,
                        body=f"**{r.get('mode_title', 'AI review')}** — recommends "
                             f"{r.get('recommendation', 'comment').replace('_', ' ')}.\n\n{r.get('summary', '')}\n\n"
                             f"_{r.get('grounding', '')}_"))
    for f in r.get("findings", []):
        blocking = f["category"] == "proven_failure" or f["severity"] in ("major", "blocker")
        body = f["message"] + (f"\n\nSuggestion: {f['suggestion']}" if f.get("suggestion") else "")
        if f.get("test_name"):
            body += f"\n\nDemonstrated by failing test: {f['test_name']}"
        db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="reviewer",
                            kind="change_request" if blocking else "comment", review_id=rv.id,
                            path=f.get("path"), line=f.get("line"), body=body[:4000], category=f["category"],
                            severity=f["severity"]))
    for change in r.get("requested_changes", []):
        db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="reviewer", kind="change_request",
                            review_id=rv.id, body=change[:4000], severity="major"))
    for q in r.get("questions", []):
        db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="reviewer", kind="change_request",
                            review_id=rv.id, body=q[:4000], severity="question"))
    pr.updated_at = _now()
    if r.get("recommendation") == "request_changes" and pr.status == "open":
        pr.status = "changes_requested"


async def review_pr(db: AsyncSession, settings: Settings, llm, learner: Learner, pr_id: uuid.UUID, mode: str) -> EngReview:
    pr = await load_pr(db, learner, pr_id)
    if pr.status not in OPEN:
        raise Conflict(f"This pull request is {pr.status}")
    latest = pr.revisions[-1]
    if latest.job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise Conflict("Checks are still running for the latest revision. Review it when they finish.")
    submission = await submission_for(db, latest.job_id)
    if submission is None:
        raise Conflict("The latest revision has no test results, so it can't be reviewed. Push a new revision.")
    return await review_submission(db, settings, llm, learner, submission, mode=mode, pr=pr)


# ---------------------------------------------------------------- decision


async def evaluate_criteria(db: AsyncSession, settings: Settings, pr: EngPullRequest) -> dict:
    latest = pr.revisions[-1]
    sub = await submission_for(db, latest.job_id)
    comments = await comments_for(db, pr.id)
    answered = {c.parent_id for c in comments if c.kind == "response" and c.author == "learner"}
    open_requests = [c for c in comments if c.author == "reviewer" and c.kind == "change_request"
                     and c.id not in answered]
    review = None
    if sub is not None:
        review = await db.scalar(select(EngReview).where(EngReview.submission_id == sub.id,
                                                         EngReview.status == ReviewStatus.COMPLETED).limit(1))
    llm_on = settings.llm_provider != "disabled"
    running = latest.job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    crit = [
        {"key": "verified_tests", "label": "Tests ran in the verified sandbox",
         "met": bool(sub and sub.executed and sub.verified),
         "detail": "Checks are still running" if running else
         "No results for the latest revision" if sub is None else
         "Verified sandbox" if sub.verified else "Not executed in a verified sandbox (mock or unverified runner)"},
        {"key": "all_tests_pass", "label": "All public and hidden tests pass",
         "met": bool(sub and sub.all_passed),
         "detail": f"{sub.passed} of {sub.total} passed" if sub else "No results yet"},
        {"key": "review_completed", "label": "AI review completed on the latest revision",
         "met": review is not None or not llm_on, "waived": not llm_on,
         "detail": "Waived: no AI provider is configured on this server" if not llm_on else
         ("Completed" if review else "Request an AI review of the latest revision")},
        {"key": "feedback_answered", "label": "Every reviewer request has a response",
         "met": not open_requests,
         "detail": "All answered" if not open_requests else f"{len(open_requests)} request(s) without a response"},
    ]
    return {"criteria": crit, "approved": all(c["met"] for c in crit), "revision": latest.number,
            "ai_recommendation": (review.review or {}).get("recommendation") if review else None,
            "evaluated_at": _now().isoformat()}


async def decide(db: AsyncSession, settings: Settings, learner: Learner, pr_id: uuid.UUID) -> EngPullRequest:
    pr = await load_pr(db, learner, pr_id, lock=True)
    if pr.status not in OPEN:
        raise Conflict(f"This pull request is already {pr.status}")
    result = await evaluate_criteria(db, settings, pr)
    pr.decision, pr.updated_at = result, _now()
    number = result["revision"]
    if result["approved"]:
        pr.status, pr.decided_at = "approved", _now()
        ws = await db.scalar(select(EngWorkspace).where(EngWorkspace.id == pr.workspace_id).with_for_update())
        ws.status, ws.completed_at = "completed", ws.completed_at or _now()
        db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="system", kind="comment",
                            body=f"Approved on revision {number}: every documented criterion is met."))
    else:
        pr.status = "changes_requested"
        unmet = [c["label"] + f" ({c['detail']})" for c in result["criteria"] if not c["met"]]
        db.add(EngPrComment(pr_id=pr.id, revision_number=number, author="system", kind="comment",
                            body="Not approved yet. Unmet criteria:\n" + "\n".join(f"- {u}" for u in unmet)))
    await audit(db, learner.id, pr.workspace_id, "pr.decided", pr_id=str(pr.id), approved=result["approved"])
    await db.commit()
    return await load_pr(db, learner, pr_id)


# ---------------------------------------------------------------- collaboration exercises


async def submit_exercise(db: AsyncSession, settings: Settings, llm, learner: Learner, workspace_id: uuid.UUID, *,
                          slug: str, body: str, client_id: uuid.UUID) -> EngExerciseResponse:
    existing = await db.scalar(select(EngExerciseResponse).where(EngExerciseResponse.learner_id == learner.id,
                                                                 EngExerciseResponse.client_id == client_id))
    if existing:
        return existing
    ws = await service.load_workspace(db, learner, workspace_id)
    ex = next((e for e in ws.version.content.get("exercises", []) if e["slug"] == slug), None)
    if ex is None:
        raise NotFound("Exercise not found")
    body = body.strip()
    if not 40 <= len(body) <= 12_000:
        raise Unprocessable("Write between 40 and 12,000 characters")
    await _llm_budget(db, settings, learner)
    row = EngExerciseResponse(learner_id=learner.id, workspace_id=ws.id, version_id=ws.version_id, exercise_slug=slug,
                              body=body, client_id=client_id, status="pending", prompt_version=EXERCISE_PROMPT_VERSION)
    db.add(row)
    await db.commit()
    criteria = {f"c{i}": text for i, text in enumerate(ex["rubric"], 1)}
    content = ws.version.content
    out = await review_written(
        llm, title=ex["title"], context=f"{content['ticket']['key']}: {content['ticket']['title']}. "
                                       f"{content['description'][:1500]}",
        prompt=ex["prompt"], criteria=criteria,
        notes="Simulated workplace exercise. Judge reasoning, risk management and communication.",
        response=body, repairs=settings.llm_max_repair_attempts)
    row.provider, row.model, row.completed_at = out.provider or None, out.model or None, _now()
    if out.ok and out.data:
        row.status, row.score = "evaluated", Decimal(str(out.data["score"]))
        row.eligible, row.evaluation = bool(out.data["eligible"]), {
            **out.data["result"], "confidence": float(out.data["confidence"]),
            "injection_suspected": out.data["injection_suspected"]}
    else:
        row.status, row.error_code = "ungraded", out.error_code or "provider_error"
    await audit(db, learner.id, ws.id, "exercise.submitted", slug=slug, status=row.status)
    await db.commit()
    return row


async def list_exercise_responses(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID) -> list[EngExerciseResponse]:
    await service.load_workspace(db, learner, workspace_id)
    return list((await db.scalars(select(EngExerciseResponse).where(
        EngExerciseResponse.workspace_id == workspace_id, EngExerciseResponse.learner_id == learner.id)
        .order_by(EngExerciseResponse.created_at.desc()))).all())


async def snapshot_by_id(db: AsyncSession, snapshot_id: uuid.UUID) -> EngSnapshot | None:
    return await db.get(EngSnapshot, snapshot_id)


async def job_by_id(db: AsyncSession, job_id: uuid.UUID) -> EngJob | None:
    return await db.get(EngJob, job_id)
