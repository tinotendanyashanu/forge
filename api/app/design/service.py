"""System design lab: projects, versions, ADRs, reviews, evaluations, failure drills.

Every project is owned by one learner; every lookup filters on the owner, so
another learner's ids behave exactly like unknown ids (404).
LLM calls never run inside a database transaction: inputs are committed first,
the call runs, then results are applied under a row lock.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.enums import DesignReviewMode
from app.db.models import (
    AdrRevision,
    ArchitectureDecision,
    ArchitectureProject,
    ArchitectureVersion,
    DesignChallenge,
    DesignChallengeVersion,
    DesignEvaluation,
    DesignReview,
    DesignReviewMessage,
    FailureAttempt,
    Learner,
)
from app.design import interviewer as ai
from app.design.catalog import FAILURE_SCENARIOS, RUBRIC_VERSION
from app.design.challenges import HIDDEN_FIELDS, PUBLIC_FIELDS
from app.design.graph import GraphDocument, clean_text, diff
from app.services.errors import Conflict, DomainError, NotFound, Unprocessable

MAX_EXPLANATION = 20_000
MAX_PROJECTS_PER_LEARNER = 200
MAX_VERSIONS_PER_PROJECT = 200
MAX_ADRS_PER_PROJECT = 50
PENDING_STALE_AFTER = timedelta(minutes=10)


class RateLimited(DomainError):
    status_code = 429


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- ADR content


def _clean(v: str) -> str:
    return clean_text(v)


class AdrContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=160)
    context: str = Field(min_length=1, max_length=4000)
    decision: str = Field(min_length=1, max_length=4000)
    alternatives: list[str] = Field(default_factory=list, max_length=8)
    reasons: str = Field(default="", max_length=4000)
    tradeoffs: str = Field(default="", max_length=4000)
    consequences: str = Field(default="", max_length=4000)
    risks: str = Field(default="", max_length=4000)
    revisit_when: str = Field(default="", max_length=2000)

    def cleaned(self) -> dict:
        d = self.model_dump()
        out = {k: clean_text(v) if isinstance(v, str) else [clean_text(x)[:600] for x in v if x.strip()] for k, v in d.items()}
        if len(out["title"]) < 3:
            raise Unprocessable("ADR title is required")
        return out


AdrStatus = Literal["proposed", "accepted", "superseded", "rejected"]


# ---------------------------------------------------------------- challenges


async def list_challenges(db: AsyncSession) -> list[DesignChallenge]:
    return list((await db.scalars(
        select(DesignChallenge).where(DesignChallenge.is_active).order_by(DesignChallenge.position)
    )).all())


async def versions_by_id(db: AsyncSession, ids: set[int]) -> dict[int, DesignChallengeVersion]:
    if not ids:
        return {}
    rows = await db.scalars(select(DesignChallengeVersion).where(DesignChallengeVersion.id.in_(ids)))
    return {v.id: v for v in rows.all()}


async def get_challenge(db: AsyncSession, slug: str) -> tuple[DesignChallenge, DesignChallengeVersion]:
    ch = await db.scalar(select(DesignChallenge).where(DesignChallenge.slug == slug, DesignChallenge.is_active))
    if ch is None or ch.current_version_id is None:
        raise NotFound("Design challenge not found")
    version = await db.get(DesignChallengeVersion, ch.current_version_id)
    return ch, version


async def completed_challenge_ids(db: AsyncSession, learner_id: uuid.UUID) -> set[int]:
    """Challenges with at least one completed (evaluated) review: hidden notes unlock."""
    rows = await db.scalars(
        select(ArchitectureProject.challenge_id)
        .join(DesignEvaluation, DesignEvaluation.project_id == ArchitectureProject.id)
        .where(ArchitectureProject.learner_id == learner_id, DesignEvaluation.status == "evaluated")
    )
    return set(rows.all())


def challenge_view(ch: DesignChallenge, version: DesignChallengeVersion, *, reveal: bool) -> dict:
    c = version.content
    out = {
        "slug": ch.slug, "title": version.title, "level": ch.level, "version": version.number,
        "rubric_version": version.rubric_version,
        **{k: c[k] for k in PUBLIC_FIELDS},
        "hint_count": len(c["hints"]),
        "failure_scenarios": [
            {"slug": s, "title": FAILURE_SCENARIOS[s]["title"], "prompt": FAILURE_SCENARIOS[s]["prompt"]}
            for s in c["failure_scenarios"]
        ],
        "revealed": reveal,
    }
    if reveal:
        out["reviewer_notes"] = {k: c[k] for k in HIDDEN_FIELDS}
    return out


# ---------------------------------------------------------------- projects


EMPTY_GRAPH = {"version": 1, "nodes": [], "edges": []}


async def create_project(db: AsyncSession, learner: Learner, slug: str, title: str | None) -> ArchitectureProject:
    ch, version = await get_challenge(db, slug)
    count = await db.scalar(select(func.count()).select_from(ArchitectureProject).where(
        ArchitectureProject.learner_id == learner.id))
    if count >= MAX_PROJECTS_PER_LEARNER:
        raise Unprocessable("Project limit reached")
    name = clean_text(title or "")[:160] or version.title
    p = ArchitectureProject(learner_id=learner.id, challenge_id=ch.id, challenge_version_id=version.id,
                            title=name, graph=EMPTY_GRAPH, explanation="", revision=1)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def load_project(db: AsyncSession, learner: Learner, project_id: uuid.UUID, *, lock: bool = False) -> ArchitectureProject:
    q = select(ArchitectureProject).where(ArchitectureProject.id == project_id, ArchitectureProject.learner_id == learner.id)
    if lock:
        q = q.with_for_update()
    p = await db.scalar(q)
    if p is None:
        raise NotFound("Project not found")
    return p


async def list_projects(db: AsyncSession, learner: Learner, limit: int = 50) -> list[ArchitectureProject]:
    return list((await db.scalars(
        select(ArchitectureProject).where(ArchitectureProject.learner_id == learner.id)
        .order_by(ArchitectureProject.updated_at.desc()).limit(limit)
    )).all())


def validate_graph(raw: dict) -> GraphDocument:
    try:
        return GraphDocument.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first["loc"])
        raise Unprocessable(f"Invalid diagram: {first['msg']}" + (f" at {loc}" if loc else "")) from None


async def save_project(
    db: AsyncSession, learner: Learner, project_id: uuid.UUID, *, graph: dict | None,
    explanation: str | None, title: str | None, base_revision: int,
) -> ArchitectureProject:
    p = await load_project(db, learner, project_id, lock=True)
    # Optimistic concurrency: a stale tab can't overwrite newer work.
    if base_revision != p.revision:
        raise Conflict(f"This design was changed elsewhere (revision {p.revision}). Reload to continue.")
    if graph is not None:
        p.graph = validate_graph(graph).model_dump()
    if explanation is not None:
        e = clean_text_keep_lines(explanation)
        if len(e) > MAX_EXPLANATION:
            raise Unprocessable(f"Explanation must be at most {MAX_EXPLANATION} characters")
        p.explanation = e
    if title is not None:
        t = clean_text(title)[:160]
        if not t:
            raise Unprocessable("Title is required")
        p.title = t
    p.revision += 1
    p.updated_at = _now()
    await db.commit()
    return p


def clean_text_keep_lines(value: str) -> str:
    return "\n".join(clean_text(line) for line in value.replace("\r\n", "\n").split("\n")).strip()


# ---------------------------------------------------------------- versions


def _fingerprint(graph: dict, explanation: str) -> str:
    return hashlib.sha256(json.dumps([graph, explanation], sort_keys=True).encode()).hexdigest()


async def _next_version_number(db: AsyncSession, project_id: uuid.UUID) -> int:
    return (await db.scalar(select(func.max(ArchitectureVersion.number)).where(
        ArchitectureVersion.project_id == project_id)) or 0) + 1


async def snapshot(db: AsyncSession, p: ArchitectureProject, name: str, *, reuse_identical: bool) -> ArchitectureVersion:
    """Caller holds the project row lock. Doesn't commit."""
    if reuse_identical:
        latest = await db.scalar(select(ArchitectureVersion).where(ArchitectureVersion.project_id == p.id)
                                 .order_by(ArchitectureVersion.number.desc()).limit(1))
        if latest and _fingerprint(latest.graph, latest.explanation) == _fingerprint(p.graph, p.explanation):
            return latest
    number = await _next_version_number(db, p.id)
    if number > MAX_VERSIONS_PER_PROJECT:
        raise Unprocessable("Version limit reached for this project")
    v = ArchitectureVersion(project_id=p.id, number=number, name=name, graph=p.graph,
                            explanation=p.explanation, source_revision=p.revision)
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


async def create_version(db: AsyncSession, learner: Learner, project_id: uuid.UUID, name: str) -> ArchitectureVersion:
    p = await load_project(db, learner, project_id, lock=True)
    label = clean_text(name)[:120]
    if not label:
        raise Unprocessable("Version name is required")
    v = await snapshot(db, p, label, reuse_identical=False)
    await db.commit()
    await db.refresh(v)
    return v


async def list_versions(db: AsyncSession, learner: Learner, project_id: uuid.UUID) -> list[ArchitectureVersion]:
    await load_project(db, learner, project_id)
    return list((await db.scalars(select(ArchitectureVersion).where(ArchitectureVersion.project_id == project_id)
                                  .order_by(ArchitectureVersion.number.desc()))).all())


async def get_version(db: AsyncSession, learner: Learner, project_id: uuid.UUID, number: int) -> ArchitectureVersion:
    await load_project(db, learner, project_id)
    v = await db.scalar(select(ArchitectureVersion).where(
        ArchitectureVersion.project_id == project_id, ArchitectureVersion.number == number))
    if v is None:
        raise NotFound("Version not found")
    return v


async def compare(db: AsyncSession, learner: Learner, project_id: uuid.UUID, a: int, b: int | None) -> dict:
    """Diff from version a to version b (or to the current saved design when b is None)."""
    p = await load_project(db, learner, project_id)
    va = await get_version(db, learner, project_id, a)
    if b is None:
        g_b, ex_b, label_b = p.graph, p.explanation, "current"
    else:
        vb = await get_version(db, learner, project_id, b)
        g_b, ex_b, label_b = vb.graph, vb.explanation, f"v{vb.number}"
    return {"from": f"v{va.number}", "to": label_b,
            **diff(GraphDocument.model_validate(va.graph), GraphDocument.model_validate(g_b)),
            "explanation_changed": va.explanation != ex_b}


async def restore_version(db: AsyncSession, learner: Learner, project_id: uuid.UUID, number: int, base_revision: int) -> ArchitectureProject:
    """Copies a snapshot into the working design. History is kept: the current
    design is snapshotted first, so nothing is lost."""
    p = await load_project(db, learner, project_id, lock=True)
    if base_revision != p.revision:
        raise Conflict(f"This design was changed elsewhere (revision {p.revision}). Reload to continue.")
    v = await db.scalar(select(ArchitectureVersion).where(
        ArchitectureVersion.project_id == project_id, ArchitectureVersion.number == number))
    if v is None:
        raise NotFound("Version not found")
    await snapshot(db, p, f"Before restoring v{number}", reuse_identical=True)
    p.graph, p.explanation = v.graph, v.explanation
    p.revision += 1
    p.updated_at = _now()
    await db.commit()
    return p


# ---------------------------------------------------------------- ADRs


async def list_adrs(db: AsyncSession, learner: Learner, project_id: uuid.UUID) -> list[ArchitectureDecision]:
    await load_project(db, learner, project_id)
    return list((await db.scalars(select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id)
                                  .order_by(ArchitectureDecision.number))).all())


async def create_adr(db: AsyncSession, learner: Learner, project_id: uuid.UUID, content: AdrContent, status: str) -> ArchitectureDecision:
    p = await load_project(db, learner, project_id, lock=True)
    number = (await db.scalar(select(func.max(ArchitectureDecision.number)).where(
        ArchitectureDecision.project_id == p.id)) or 0) + 1
    if number > MAX_ADRS_PER_PROJECT:
        raise Unprocessable("Decision record limit reached")
    data = content.cleaned()
    d = ArchitectureDecision(project_id=p.id, number=number, revision=1, status=status, content=data)
    db.add(d)
    await db.flush()
    db.add(AdrRevision(decision_id=d.id, revision=1, status=status, content=data))
    p.updated_at = _now()
    await db.commit()
    await db.refresh(d)
    return d


async def _load_adr(db: AsyncSession, learner: Learner, project_id: uuid.UUID, number: int, *, lock=False) -> ArchitectureDecision:
    await load_project(db, learner, project_id)
    q = select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id, ArchitectureDecision.number == number)
    d = await db.scalar(q.with_for_update() if lock else q)
    if d is None:
        raise NotFound("Decision record not found")
    return d


async def update_adr(db: AsyncSession, learner: Learner, project_id: uuid.UUID, number: int,
                     content: AdrContent, status: str, base_revision: int) -> ArchitectureDecision:
    d = await _load_adr(db, learner, project_id, number, lock=True)
    if base_revision != d.revision:
        raise Conflict(f"This decision record was changed elsewhere (revision {d.revision}). Reload to continue.")
    data = content.cleaned()
    d.revision += 1
    d.content, d.status, d.updated_at = data, status, _now()
    db.add(AdrRevision(decision_id=d.id, revision=d.revision, status=status, content=data))
    await db.commit()
    return d


async def adr_history(db: AsyncSession, learner: Learner, project_id: uuid.UUID, number: int) -> list[AdrRevision]:
    d = await _load_adr(db, learner, project_id, number)
    return list((await db.scalars(select(AdrRevision).where(AdrRevision.decision_id == d.id)
                                  .order_by(AdrRevision.revision.desc()))).all())


# ---------------------------------------------------------------- rate limiting


async def check_rate(db: AsyncSession, settings: Settings, learner: Learner) -> None:
    """Counts AI calls in the last hour under a per-learner advisory lock."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 6))"), {"k": str(learner.id)})
    since = _now() - timedelta(hours=1)
    projects = select(ArchitectureProject.id).where(ArchitectureProject.learner_id == learner.id)
    reviews = select(DesignReview.id).where(DesignReview.project_id.in_(projects))
    learner_msgs = await db.scalar(select(func.count()).select_from(DesignReviewMessage).where(
        DesignReviewMessage.review_id.in_(reviews), DesignReviewMessage.role == "learner",
        DesignReviewMessage.created_at >= since))
    evals = await db.scalar(select(func.count()).select_from(DesignEvaluation).where(
        DesignEvaluation.project_id.in_(projects), DesignEvaluation.created_at >= since))
    fails = await db.scalar(select(func.count()).select_from(FailureAttempt).where(
        FailureAttempt.project_id.in_(projects), FailureAttempt.impact.is_not(None),
        FailureAttempt.created_at >= since))
    if learner_msgs + evals + fails >= settings.design_llm_calls_per_hour:
        raise RateLimited("AI review limit reached for this hour. Keep designing and try again later.")


# ---------------------------------------------------------------- reviews


async def _append(db: AsyncSession, review: DesignReview, role: str, kind: str, content: str, **extra) -> DesignReviewMessage:
    seq = (await db.scalar(select(func.max(DesignReviewMessage.seq)).where(DesignReviewMessage.review_id == review.id)) or 0) + 1
    m = DesignReviewMessage(review_id=review.id, seq=seq, role=role, kind=kind, content=content[:20000], **extra)
    db.add(m)
    review.updated_at = _now()
    await db.flush()
    await db.refresh(m)
    return m


def opening_prompt(version: DesignChallengeVersion, mode: str) -> str:
    """Server-written, deterministic opener (role 'system'); not AI output."""
    first = version.content["functional"][0]
    return {
        "guided": f"Start with the core flow. Add the components needed for: \"{first}\". Then explain, in your own words, how a request moves through them.",
        "interview": f"Walk me through your design for \"{version.title}\". Begin with the main request path for: \"{first}\".",
        "senior_review": "Present the architecture as you would to a review board: the key decisions, what you traded off, and what worries you most.",
        "failure_review": "Describe your design, then identify the single component whose failure would hurt users most, and why.",
    }[mode]


async def start_review(db: AsyncSession, learner: Learner, project_id: uuid.UUID, mode: DesignReviewMode) -> DesignReview:
    p = await load_project(db, learner, project_id, lock=True)
    version = await db.get(DesignChallengeVersion, p.challenge_version_id)
    r = DesignReview(project_id=p.id, mode=mode, hints_used=0, depth=1)
    db.add(r)
    await db.flush()
    await _append(db, r, "system", "notice", opening_prompt(version, mode.value))
    await db.commit()
    await db.refresh(r)
    return r


async def load_review(db: AsyncSession, learner: Learner, review_id: uuid.UUID, *, lock=False) -> tuple[DesignReview, ArchitectureProject]:
    q = (select(DesignReview, ArchitectureProject).join(ArchitectureProject, ArchitectureProject.id == DesignReview.project_id)
         .where(DesignReview.id == review_id, ArchitectureProject.learner_id == learner.id))
    if lock:
        q = q.with_for_update(of=DesignReview)
    row = (await db.execute(q)).first()
    if row is None:
        raise NotFound("Review not found")
    return row[0], row[1]


async def messages_of(db: AsyncSession, review_id: uuid.UUID) -> list[DesignReviewMessage]:
    return list((await db.scalars(select(DesignReviewMessage).where(DesignReviewMessage.review_id == review_id)
                                  .order_by(DesignReviewMessage.seq))).all())


async def list_reviews(db: AsyncSession, learner: Learner, project_id: uuid.UUID) -> list[DesignReview]:
    await load_project(db, learner, project_id)
    return list((await db.scalars(select(DesignReview).where(DesignReview.project_id == project_id)
                                  .order_by(DesignReview.created_at.desc()))).all())


async def _context(db: AsyncSession, p: ArchitectureProject, review: DesignReview | None, *, graph: dict | None = None,
                   explanation: str | None = None) -> ai.DesignContext:
    version = await db.get(DesignChallengeVersion, p.challenge_version_id)
    adrs = (await db.scalars(select(ArchitectureDecision).where(ArchitectureDecision.project_id == p.id)
                             .order_by(ArchitectureDecision.number))).all()
    transcript = []
    if review is not None:
        transcript = [(m.role, m.content) for m in await messages_of(db, review.id) if m.kind != "evaluation"]
    return ai.DesignContext(
        challenge=version.content, graph=GraphDocument.model_validate(graph if graph is not None else p.graph),
        explanation=explanation if explanation is not None else p.explanation,
        adrs=[{"status": a.status, **a.content} for a in adrs], transcript=transcript,
        mode=review.mode.value if review else "failure_review", depth=review.depth if review else 2,
    )


async def send_message(db: AsyncSession, settings: Settings, llm, learner: Learner, review_id: uuid.UUID,
                       content: str, client_message_id: uuid.UUID) -> list[DesignReviewMessage]:
    """Commits the learner's message, asks the interviewer, appends its reply.
    Returns the messages created for this client_message_id (idempotent)."""
    text_ = clean_text_keep_lines(content)
    if not text_:
        raise Unprocessable("Message is empty")
    if len(text_) > 8000:
        raise Unprocessable("Message must be at most 8000 characters")
    review, p = await load_review(db, learner, review_id, lock=True)
    existing = await db.scalar(select(DesignReviewMessage).where(
        DesignReviewMessage.review_id == review.id, DesignReviewMessage.client_message_id == client_message_id))
    if existing is not None:
        seq = existing.seq
        await db.commit()
        msgs = await messages_of(db, review_id)
        return [m for m in msgs if m.seq >= seq][:2]
    await check_rate(db, settings, learner)
    mine = await _append(db, review, "learner", "message", text_, client_message_id=client_message_id)
    await db.commit()

    ctx = await _context(db, p, review)
    await db.commit()  # end the read transaction before the network call (no expiry)
    out = await ai.interviewer_turn(llm, ctx, settings.llm_max_repair_attempts)

    review, p = await load_review(db, learner, review_id, lock=True)
    if out.ok:
        if out.data["depth_signal"] == "raise":
            review.depth = min(3, review.depth + 1)
        elif out.data["depth_signal"] == "lower":
            review.depth = max(1, review.depth - 1)
        body = f"{out.data['reply']}\n\n{out.data['question']}"
        reply = await _append(db, review, "interviewer", "question", body, provider=out.provider, model=out.model,
                              prompt_tokens=out.prompt_tokens, completion_tokens=out.completion_tokens)
    else:
        reply = await _append(db, review, "system", "notice",
                              f"The AI interviewer is unavailable ({out.error_code}). Your message is saved; send another message to retry.",
                              provider=out.provider or None, model=out.model or None)
    await db.commit()
    return [mine, reply]


async def reveal_hint(db: AsyncSession, learner: Learner, review_id: uuid.UUID) -> DesignReviewMessage:
    review, p = await load_review(db, learner, review_id, lock=True)
    version = await db.get(DesignChallengeVersion, p.challenge_version_id)
    hints = version.content["hints"]
    if review.hints_used >= len(hints):
        raise Conflict("No more hints for this challenge")
    hint = hints[review.hints_used]
    review.hints_used += 1
    m = await _append(db, review, "system", "hint", f"Hint {review.hints_used} of {len(hints)}: {hint}")
    await db.commit()
    return m


# ---------------------------------------------------------------- evaluation


async def evaluate(db: AsyncSession, settings: Settings, llm, learner: Learner, review_id: uuid.UUID) -> DesignEvaluation:
    review, p = await load_review(db, learner, review_id, lock=True)
    pending = await db.scalar(select(DesignEvaluation).where(
        DesignEvaluation.review_id == review.id, DesignEvaluation.status == "pending"))
    if pending is not None:
        if _now() - pending.created_at < PENDING_STALE_AFTER:
            raise Conflict("An evaluation is already running for this review")
        pending.status, pending.error_code, pending.completed_at = "ungraded", "abandoned", _now()
    await check_rate(db, settings, learner)
    graph = validate_graph(p.graph)
    if not graph.nodes:
        raise Unprocessable("Add components to the diagram before requesting an evaluation")
    version = await snapshot(db, p, "Submitted for evaluation", reuse_identical=True)
    ev = DesignEvaluation(
        review_id=review.id, project_id=p.id, architecture_version_id=version.id,
        challenge_version_id=p.challenge_version_id, rubric_version=RUBRIC_VERSION,
        evaluation_version=ai.EVALUATION_VERSION, status="pending",
        provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"),
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    ev_id = ev.id

    ctx = await _context(db, p, review, graph=version.graph, explanation=version.explanation)
    await db.commit()
    out = await ai.evaluate_design(llm, ctx, settings.llm_max_repair_attempts)

    review, p = await load_review(db, learner, review_id, lock=True)
    ev = await db.get(DesignEvaluation, ev_id, with_for_update=True)
    ev.provider, ev.model = out.provider or ev.provider, out.model or ev.model
    ev.llm_attempts, ev.prompt_tokens, ev.completion_tokens = out.attempts, out.prompt_tokens, out.completion_tokens
    ev.completed_at = _now()
    if out.ok:
        d = out.data
        ev.status, ev.total_score, ev.model_total_score = "evaluated", d["total_score"], d["model_total_score"]
        ev.confidence, ev.result = d["confidence"], d["result"]
        ev.injection_suspected, ev.mastery_eligible = d["injection_suspected"], d["mastery_eligible"]
        await _append(db, review, "system", "evaluation",
                      f"Evaluation complete for version {version.number}. Score {d['total_score'] * 100:.0f}% (AI judgment, not proof of mastery).",
                      architecture_version_id=version.id)
        for q in d["result"]["follow_up_questions"][:1]:
            await _append(db, review, "interviewer", "question", q, architecture_version_id=version.id,
                          provider=out.provider, model=out.model)
    else:
        ev.status, ev.error_code = "ungraded", out.error_code or "provider_error"
        await _append(db, review, "system", "notice",
                      f"Evaluation could not be completed ({ev.error_code}). No score was recorded. You can try again.",
                      architecture_version_id=version.id)
    await db.commit()
    return ev


async def evaluations_for(db: AsyncSession, learner: Learner, project_id: uuid.UUID | None = None, limit: int = 50) -> list[tuple[DesignEvaluation, ArchitectureProject, ArchitectureVersion]]:
    q = (select(DesignEvaluation, ArchitectureProject, ArchitectureVersion)
         .join(ArchitectureProject, ArchitectureProject.id == DesignEvaluation.project_id)
         .join(ArchitectureVersion, ArchitectureVersion.id == DesignEvaluation.architecture_version_id)
         .where(ArchitectureProject.learner_id == learner.id))
    if project_id is not None:
        q = q.where(ArchitectureProject.id == project_id)
    rows = await db.execute(q.order_by(DesignEvaluation.created_at.desc()).limit(limit))
    return [tuple(r) for r in rows.all()]


async def get_evaluation(db: AsyncSession, learner: Learner, evaluation_id: uuid.UUID):
    row = (await db.execute(
        select(DesignEvaluation, ArchitectureProject, ArchitectureVersion)
        .join(ArchitectureProject, ArchitectureProject.id == DesignEvaluation.project_id)
        .join(ArchitectureVersion, ArchitectureVersion.id == DesignEvaluation.architecture_version_id)
        .where(DesignEvaluation.id == evaluation_id, ArchitectureProject.learner_id == learner.id)
    )).first()
    if row is None:
        raise NotFound("Evaluation not found")
    return tuple(row)


# ---------------------------------------------------------------- failure scenarios


async def start_failure(db: AsyncSession, learner: Learner, project_id: uuid.UUID, slug: str) -> FailureAttempt:
    p = await load_project(db, learner, project_id, lock=True)
    if slug not in FAILURE_SCENARIOS:
        raise NotFound("Unknown failure scenario")
    if not validate_graph(p.graph).nodes:
        raise Unprocessable("Add components to the diagram before running a failure scenario")
    version = await snapshot(db, p, f"Failure drill: {FAILURE_SCENARIOS[slug]['title']}", reuse_identical=True)
    fa = FailureAttempt(project_id=p.id, architecture_version_id=version.id, scenario_slug=slug, status="open")
    db.add(fa)
    await db.commit()
    await db.refresh(fa)
    return fa


async def load_failure(db: AsyncSession, learner: Learner, attempt_id: uuid.UUID, *, lock=False) -> tuple[FailureAttempt, ArchitectureProject]:
    q = (select(FailureAttempt, ArchitectureProject).join(ArchitectureProject, ArchitectureProject.id == FailureAttempt.project_id)
         .where(FailureAttempt.id == attempt_id, ArchitectureProject.learner_id == learner.id))
    if lock:
        q = q.with_for_update(of=FailureAttempt)
    row = (await db.execute(q)).first()
    if row is None:
        raise NotFound("Failure scenario attempt not found")
    return row[0], row[1]


async def list_failures(db: AsyncSession, learner: Learner, project_id: uuid.UUID) -> list[FailureAttempt]:
    await load_project(db, learner, project_id)
    return list((await db.scalars(select(FailureAttempt).where(FailureAttempt.project_id == project_id)
                                  .order_by(FailureAttempt.created_at.desc()))).all())


async def respond_failure(db: AsyncSession, settings: Settings, llm, learner: Learner, attempt_id: uuid.UUID,
                          impact: str, mitigation: str) -> FailureAttempt:
    impact, mitigation = clean_text_keep_lines(impact), clean_text_keep_lines(mitigation)
    if len(impact) < 20 or len(mitigation) < 20:
        raise Unprocessable("Describe both the impact and your mitigation (at least 20 characters each)")
    if len(impact) > 6000 or len(mitigation) > 6000:
        raise Unprocessable("Each answer must be at most 6000 characters")
    fa, p = await load_failure(db, learner, attempt_id, lock=True)
    if fa.status == "evaluated":
        raise Conflict("This scenario has already been evaluated. Start a new attempt to try again.")
    if fa.error_code == "in_progress" and _now() - fa.created_at < PENDING_STALE_AFTER:
        raise Conflict("This answer is already being evaluated")
    await check_rate(db, settings, learner)
    fa.impact, fa.mitigation, fa.status, fa.error_code = impact, mitigation, "open", "in_progress"
    await db.commit()

    version = await db.get(ArchitectureVersion, fa.architecture_version_id)
    ctx = await _context(db, p, None, graph=version.graph, explanation=version.explanation)
    await db.commit()
    out = await ai.evaluate_failure(llm, ctx, fa.scenario_slug, impact, mitigation, settings.llm_max_repair_attempts)

    fa, p = await load_failure(db, learner, attempt_id, lock=True)
    fa.provider, fa.model = out.provider or None, out.model or None
    fa.prompt_tokens, fa.completion_tokens, fa.completed_at = out.prompt_tokens, out.completion_tokens, _now()
    if out.ok:
        fa.status, fa.error_code = "evaluated", None
        fa.score, fa.result, fa.mastery_eligible = out.data["score"], out.data["result"], out.data["mastery_eligible"]
    else:
        fa.status, fa.error_code = "ungraded", out.error_code or "provider_error"
    await db.commit()
    return fa


# ---------------------------------------------------------------- dashboard


CRITERION_COMPETENCIES = {
    "requirement_coverage": ["technical_communication"],
    "correctness": ["api_architecture", "data_modeling"],
    "scalability": ["scalability"],
    "reliability": ["failure_recovery", "distributed_systems"],
    "data_consistency": ["consistency", "data_modeling"],
    "security": ["security"],
    "performance": ["scalability"],
    "maintainability": ["api_architecture"],
    "operational_complexity": ["observability"],
    "cost_awareness": ["cost_optimization"],
    "reasoning_quality": ["technical_communication"],
    "tradeoffs": ["technical_communication", "distributed_systems"],
}
MIN_ASSESSMENTS = 2  # evaluations across at least 2 distinct challenges


def competency_profile(evals: list[tuple[DesignEvaluation, int]]) -> dict[str, dict]:
    """Aggregates observed criterion scores of mastery-eligible evaluations.
    ``evals``: (evaluation, challenge_id). A competency is 'insufficient'
    until it has evidence from MIN_ASSESSMENTS evaluations of distinct challenges."""
    acc: dict[str, dict] = {}
    for ev, challenge_id in evals:
        if ev.status != "evaluated" or not ev.mastery_eligible:
            continue
        for c in ev.result["criteria"]:
            for comp in CRITERION_COMPETENCIES.get(c["criterion"], []):
                a = acc.setdefault(comp, {"points": 0, "max": 0, "challenges": set(), "evaluations": 0})
                a["points"] += c["score"] if c["evidence_status"] == "observed" else 0
                a["max"] += 2
                a["challenges"].add(challenge_id)
        for comp in {comp for c in ev.result["criteria"] for comp in CRITERION_COMPETENCIES.get(c["criterion"], [])}:
            acc[comp]["evaluations"] += 1
    out = {}
    for comp, a in acc.items():
        enough = len(a["challenges"]) >= MIN_ASSESSMENTS
        out[comp] = {"score": round(a["points"] / a["max"], 3) if a["max"] else None,
                     "evaluations": a["evaluations"], "distinct_challenges": len(a["challenges"]),
                     "status": "assessed" if enough else "insufficient_evidence"}
    return out


LEVEL_ORDER = ["beginner", "intermediate", "advanced", "senior"]


def recommend_challenge(challenges: list[tuple[DesignChallenge, DesignChallengeVersion]], *, attempted: dict[int, float | None],
                        weak_criteria: list[str], mastered_skills: set[str], target_level: str | None,
                        passed_levels: set[str]) -> dict | None:
    """Picks the next challenge. Rules (in order):
    1. Retry a challenge whose best evaluated score is below 0.5.
    2. Otherwise an unattempted, unlocked challenge at or below the target level.
       Unlocked: beginner level, or its prerequisite skills are mastered, or the
       learner scored at least 0.5 on a challenge one level below. Prefer ones whose
       rubric focuses on the learner's weakest criteria, then the lowest level."""
    for ch, v in challenges:
        best = attempted.get(ch.id)
        if best is not None and best < 0.5:
            return {"slug": ch.slug, "title": v.title, "level": ch.level, "reason": "retry",
                    "detail": f"Your best evaluated score here is {best * 100:.0f}%. Revisit it with what you've learned."}
    cap = LEVEL_ORDER.index(target_level) if target_level in LEVEL_ORDER else len(LEVEL_ORDER) - 1
    best_pick, best_key = None, None
    for ch, v in challenges:
        if ch.id in attempted:
            continue
        lvl = LEVEL_ORDER.index(ch.level.value)
        if lvl > cap:
            continue
        prereqs = set(v.content.get("prerequisites", []))
        if lvl > 0 and not prereqs <= mastered_skills and LEVEL_ORDER[lvl - 1] not in passed_levels:
            continue
        overlap = len(set(v.content["rubric_focus"]) & set(weak_criteria))
        key = (-overlap, lvl, ch.position)
        if best_key is None or key < best_key:
            best_pick, best_key = (ch, v, overlap), key
    if best_pick is None:
        return None
    ch, v, overlap = best_pick
    reason = "weak_area" if overlap else "next_level" if attempted else "start"
    detail = {
        "weak_area": "Its rubric emphasises criteria where your evaluations were weakest.",
        "next_level": "A challenge you have not attempted yet, at a level you have unlocked.",
        "start": "A good first design challenge.",
    }[reason]
    return {"slug": ch.slug, "title": v.title, "level": ch.level, "reason": reason, "detail": detail}


def as_decimal(x) -> Decimal | None:
    return None if x is None else Decimal(str(x))
