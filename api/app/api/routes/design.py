"""System Design & Architecture Lab endpoints (Milestone 6)."""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentLearner, Db, get_llm, sync_mastery_best_effort
from app.db.enums import DesignReviewMode
from app.db.models import (
    ArchitectureDecision,
    ArchitectureProject,
    ArchitectureVersion,
    DesignChallenge,
    DesignEvaluation,
    DesignReview,
    DesignReviewMessage,
    FailureAttempt,
    LearnerGoal,
    Skill,
    SkillMastery,
)
from app.design import service
from app.design.catalog import COMPETENCIES, CRITERIA, FAILURE_SCENARIOS, RUBRIC_VERSION
from app.design.graph import COMPONENT_TYPES, MAX_EDGES, MAX_GRAPH_BYTES, MAX_NODES, PROTOCOLS
from app.design.interviewer import EVALUATION_VERSION, PROMPT_VERSION
from app.services.errors import Forbidden, Unprocessable

public = APIRouter(prefix="/design", tags=["design"])
router = APIRouter(prefix="/design", tags=["design"])
LLM = Annotated[object, Depends(get_llm)]


# ---------------------------------------------------------------- schemas


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_slug: str = Field(max_length=96)
    title: str | None = Field(default=None, max_length=160)


class ProjectSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    graph: dict[str, Any] | None = None
    explanation: str | None = Field(default=None, max_length=service.MAX_EXPLANATION + 2000)
    title: str | None = Field(default=None, max_length=200)


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class RestoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)


class AdrIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: service.AdrContent
    status: service.AdrStatus = "proposed"
    base_revision: int | None = Field(default=None, ge=1)


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: DesignReviewMode


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)
    client_message_id: uuid.UUID


class FailureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(max_length=64)


class FailureAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impact: str = Field(min_length=1, max_length=6000)
    mitigation: str = Field(min_length=1, max_length=6000)


def _f(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


def project_out(p: ArchitectureProject, challenge: DesignChallenge | None = None, title: str | None = None) -> dict:
    out = {
        "id": str(p.id), "title": p.title, "graph": p.graph, "explanation": p.explanation,
        "revision": p.revision, "created_at": p.created_at, "updated_at": p.updated_at,
    }
    if challenge is not None:
        out["challenge"] = {"slug": challenge.slug, "level": challenge.level, "title": title}
    return out


def version_out(v: ArchitectureVersion, *, full: bool = False) -> dict:
    out = {"number": v.number, "name": v.name, "source_revision": v.source_revision, "created_at": v.created_at,
           "components": len(v.graph.get("nodes", [])), "connections": len(v.graph.get("edges", []))}
    if full:
        out |= {"graph": v.graph, "explanation": v.explanation}
    return out


def adr_out(d: ArchitectureDecision) -> dict:
    return {"number": d.number, "revision": d.revision, "status": d.status, "content": d.content,
            "created_at": d.created_at, "updated_at": d.updated_at}


def message_out(m: DesignReviewMessage) -> dict:
    return {"id": str(m.id), "seq": m.seq, "role": m.role, "kind": m.kind, "content": m.content,
            "provider": m.provider, "model": m.model, "created_at": m.created_at,
            "client_message_id": str(m.client_message_id) if m.client_message_id else None}


def evaluation_out(ev: DesignEvaluation, version: ArchitectureVersion | None = None) -> dict:
    return {
        "id": str(ev.id), "review_id": str(ev.review_id), "project_id": str(ev.project_id),
        "status": ev.status, "error_code": ev.error_code,
        "total_score": _f(ev.total_score), "model_total_score": _f(ev.model_total_score),
        "confidence": _f(ev.confidence), "injection_suspected": ev.injection_suspected,
        "mastery_eligible": ev.mastery_eligible, "result": ev.result,
        "architecture_version": version.number if version else None,
        "versions": {"evaluation": ev.evaluation_version, "rubric": ev.rubric_version,
                     "challenge_version_id": ev.challenge_version_id, "model": ev.model, "provider": ev.provider},
        "usage": {"prompt_tokens": ev.prompt_tokens, "completion_tokens": ev.completion_tokens,
                  "llm_attempts": ev.llm_attempts, "approximate_cost": None},
        "created_at": ev.created_at, "completed_at": ev.completed_at,
    }


def failure_out(fa: FailureAttempt, version_number: int | None = None) -> dict:
    sc = FAILURE_SCENARIOS[fa.scenario_slug]
    return {
        "id": str(fa.id), "project_id": str(fa.project_id), "architecture_version": version_number,
        "scenario": {"slug": fa.scenario_slug, "title": sc["title"], "prompt": sc["prompt"]},
        "status": "evaluating" if fa.error_code == "in_progress" else fa.status,
        "error_code": None if fa.error_code == "in_progress" else fa.error_code,
        "impact": fa.impact, "mitigation": fa.mitigation, "score": _f(fa.score), "result": fa.result,
        "mastery_eligible": fa.mastery_eligible, "provider": fa.provider, "model": fa.model,
        "usage": {"prompt_tokens": fa.prompt_tokens, "completion_tokens": fa.completion_tokens, "approximate_cost": None},
        "created_at": fa.created_at, "completed_at": fa.completed_at,
    }


def review_out(r: DesignReview) -> dict:
    return {"id": str(r.id), "project_id": str(r.project_id), "mode": r.mode, "hints_used": r.hints_used,
            "depth": r.depth, "created_at": r.created_at, "updated_at": r.updated_at}


# ---------------------------------------------------------------- public catalogue


@public.get("/catalog")
async def catalog() -> dict:
    """Component library, protocols, rubric criteria and scenario titles. No hidden content."""
    return {
        "components": [{"type": k, **v} for k, v in COMPONENT_TYPES.items()],
        "protocols": list(PROTOCOLS),
        "criteria": [{"key": k, "description": v} for k, v in CRITERIA.items()],
        "competencies": sorted(COMPETENCIES),
        "failure_scenarios": [{"slug": k, "title": v["title"], "prompt": v["prompt"]} for k, v in FAILURE_SCENARIOS.items()],
        "limits": {"nodes": MAX_NODES, "edges": MAX_EDGES, "graph_bytes": MAX_GRAPH_BYTES},
        "rubric_version": RUBRIC_VERSION,
    }


@public.get("/challenges")
async def challenges(db: Db) -> list[dict]:
    chs = await service.list_challenges(db)
    versions = await service.versions_by_id(db, {c.current_version_id for c in chs if c.current_version_id})
    out = []
    for c in chs:
        v = versions[c.current_version_id]
        out.append({"slug": c.slug, "title": v.title, "level": c.level, "version": v.number,
                    "summary": v.content["business_context"][:240], "skills": v.content["skills"],
                    "competencies": v.content["competencies"], "prerequisites": v.content["prerequisites"]})
    return out


@public.get("/challenges/{slug}")
async def challenge(db: Db, slug: str) -> dict:
    ch, v = await service.get_challenge(db, slug)
    return service.challenge_view(ch, v, reveal=False)


# ---------------------------------------------------------------- learner routes


@router.get("/status")
async def lab_status(request: Request, llm: LLM) -> dict:
    s = request.app.state.settings
    return {
        "llm": {"provider": getattr(llm, "name", "disabled"), "model": getattr(llm, "model", None),
                "configured": getattr(llm, "name", "disabled") != "disabled"},
        "prompt_version": PROMPT_VERSION, "evaluation_version": EVALUATION_VERSION,
        "rubric_version": RUBRIC_VERSION, "ai_calls_per_hour": s.design_llm_calls_per_hour,
    }


@router.get("/challenges/{slug}/learner")
async def challenge_for_learner(db: Db, learner: CurrentLearner, slug: str) -> dict:
    """Challenge with reviewer notes revealed once the learner has a completed evaluation for it."""
    ch, v = await service.get_challenge(db, slug)
    done = ch.id in await service.completed_challenge_ids(db, learner.id)
    projects = await db.scalars(select(ArchitectureProject).where(
        ArchitectureProject.learner_id == learner.id, ArchitectureProject.challenge_id == ch.id)
        .order_by(ArchitectureProject.updated_at.desc()))
    return service.challenge_view(ch, v, reveal=done) | {
        "projects": [{"id": str(p.id), "title": p.title, "updated_at": p.updated_at} for p in projects.all()]}


@router.get("/challenges/{slug}/notes")
async def challenge_notes(db: Db, learner: CurrentLearner, slug: str) -> dict:
    ch, v = await service.get_challenge(db, slug)
    if ch.id not in await service.completed_challenge_ids(db, learner.id):
        raise Forbidden("Reviewer notes unlock after your first completed evaluation of this challenge")
    return service.challenge_view(ch, v, reveal=True)["reviewer_notes"]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(db: Db, learner: CurrentLearner, body: ProjectIn) -> dict:
    p = await service.create_project(db, learner, body.challenge_slug, body.title)
    return project_out(p)


@router.get("/projects")
async def projects(db: Db, learner: CurrentLearner) -> list[dict]:
    ps = await service.list_projects(db, learner)
    chs = {c.id: c for c in (await db.scalars(select(DesignChallenge))).all()}
    versions = await service.versions_by_id(db, {p.challenge_version_id for p in ps})
    return [project_out(p, chs[p.challenge_id], versions[p.challenge_version_id].title) | {"graph": None, "explanation": None,
            "components": len(p.graph.get("nodes", []))} for p in ps]


@router.get("/projects/{project_id}")
async def project(db: Db, learner: CurrentLearner, project_id: uuid.UUID) -> dict:
    p = await service.load_project(db, learner, project_id)
    ch = await db.get(DesignChallenge, p.challenge_id)
    versions = await service.versions_by_id(db, {p.challenge_version_id})
    v = versions[p.challenge_version_id]
    done = ch.id in await service.completed_challenge_ids(db, learner.id)
    current = ch.current_version_id == v.id
    return project_out(p, ch, v.title) | {
        "challenge_detail": service.challenge_view(ch, v, reveal=done),
        "challenge_outdated": not current,
    }


@router.put("/projects/{project_id}")
async def save_project(db: Db, learner: CurrentLearner, project_id: uuid.UUID, body: ProjectSave) -> dict:
    p = await service.save_project(db, learner, project_id, graph=body.graph, explanation=body.explanation,
                                   title=body.title, base_revision=body.base_revision)
    return {"revision": p.revision, "updated_at": p.updated_at}


@router.get("/projects/{project_id}/versions")
async def versions(db: Db, learner: CurrentLearner, project_id: uuid.UUID) -> list[dict]:
    return [version_out(v) for v in await service.list_versions(db, learner, project_id)]


@router.post("/projects/{project_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(db: Db, learner: CurrentLearner, project_id: uuid.UUID, body: VersionIn) -> dict:
    return version_out(await service.create_version(db, learner, project_id, body.name), full=True)


@router.get("/projects/{project_id}/versions/{number}")
async def version(db: Db, learner: CurrentLearner, project_id: uuid.UUID, number: int) -> dict:
    return version_out(await service.get_version(db, learner, project_id, number), full=True)


@router.post("/projects/{project_id}/versions/{number}/restore")
async def restore(db: Db, learner: CurrentLearner, project_id: uuid.UUID, number: int, body: RestoreIn) -> dict:
    p = await service.restore_version(db, learner, project_id, number, body.base_revision)
    return project_out(p)


@router.get("/projects/{project_id}/compare")
async def compare(db: Db, learner: CurrentLearner, project_id: uuid.UUID,
                  from_: Annotated[int, Query(alias="from", ge=1)], to: Annotated[int | None, Query(ge=1)] = None) -> dict:
    return await service.compare(db, learner, project_id, from_, to)


# ---- ADRs


@router.get("/projects/{project_id}/adrs")
async def adrs(db: Db, learner: CurrentLearner, project_id: uuid.UUID) -> list[dict]:
    return [adr_out(d) for d in await service.list_adrs(db, learner, project_id)]


@router.post("/projects/{project_id}/adrs", status_code=status.HTTP_201_CREATED)
async def create_adr(db: Db, learner: CurrentLearner, project_id: uuid.UUID, body: AdrIn) -> dict:
    return adr_out(await service.create_adr(db, learner, project_id, body.content, body.status))


@router.put("/projects/{project_id}/adrs/{number}")
async def update_adr(db: Db, learner: CurrentLearner, project_id: uuid.UUID, number: int, body: AdrIn) -> dict:
    if body.base_revision is None:
        raise Unprocessable("base_revision is required to edit a decision record")
    return adr_out(await service.update_adr(db, learner, project_id, number, body.content, body.status, body.base_revision))


@router.get("/projects/{project_id}/adrs/{number}/revisions")
async def adr_revisions(db: Db, learner: CurrentLearner, project_id: uuid.UUID, number: int) -> list[dict]:
    return [{"revision": r.revision, "status": r.status, "content": r.content, "created_at": r.created_at}
            for r in await service.adr_history(db, learner, project_id, number)]


# ---- reviews


@router.post("/projects/{project_id}/reviews", status_code=status.HTTP_201_CREATED)
async def start_review(db: Db, learner: CurrentLearner, project_id: uuid.UUID, body: ReviewIn) -> dict:
    r = await service.start_review(db, learner, project_id, body.mode)
    return review_out(r) | {"messages": [message_out(m) for m in await service.messages_of(db, r.id)]}


@router.get("/projects/{project_id}/reviews")
async def reviews(db: Db, learner: CurrentLearner, project_id: uuid.UUID) -> list[dict]:
    return [review_out(r) for r in await service.list_reviews(db, learner, project_id)]


@router.get("/reviews/{review_id}")
async def review(db: Db, learner: CurrentLearner, review_id: uuid.UUID) -> dict:
    r, _ = await service.load_review(db, learner, review_id)
    evals = (await db.execute(
        select(DesignEvaluation, ArchitectureVersion)
        .join(ArchitectureVersion, ArchitectureVersion.id == DesignEvaluation.architecture_version_id)
        .where(DesignEvaluation.review_id == r.id).order_by(DesignEvaluation.created_at.desc())
    )).all()
    return review_out(r) | {
        "messages": [message_out(m) for m in await service.messages_of(db, r.id)],
        "evaluations": [evaluation_out(e, v) for e, v in evals],
    }


@router.post("/reviews/{review_id}/messages")
async def send_message(request: Request, db: Db, learner: CurrentLearner, llm: LLM, review_id: uuid.UUID, body: MessageIn) -> dict:
    msgs = await service.send_message(db, request.app.state.settings, llm, learner, review_id,
                                      body.content, body.client_message_id)
    return {"messages": [message_out(m) for m in msgs]}


@router.post("/reviews/{review_id}/hint")
async def hint(db: Db, learner: CurrentLearner, review_id: uuid.UUID) -> dict:
    return message_out(await service.reveal_hint(db, learner, review_id))


@router.post("/reviews/{review_id}/evaluate")
async def evaluate(request: Request, db: Db, learner: CurrentLearner, llm: LLM, review_id: uuid.UUID) -> dict:
    ev = await service.evaluate(db, request.app.state.settings, llm, learner, review_id)
    version = await db.get(ArchitectureVersion, ev.architecture_version_id)
    out = evaluation_out(ev, version)
    if ev.status == "evaluated":
        await sync_mastery_best_effort(request, db, learner)
    return out


# ---- evaluations


@router.get("/evaluations")
async def evaluation_history(db: Db, learner: CurrentLearner, project_id: uuid.UUID | None = None) -> list[dict]:
    rows = await service.evaluations_for(db, learner, project_id)
    return [evaluation_out(ev, v) | {"project_title": p.title} for ev, p, v in rows]


@router.get("/evaluations/{evaluation_id}")
async def evaluation(db: Db, learner: CurrentLearner, evaluation_id: uuid.UUID) -> dict:
    ev, p, v = await service.get_evaluation(db, learner, evaluation_id)
    return evaluation_out(ev, v) | {"project_title": p.title}


# ---- failure scenarios


@router.get("/projects/{project_id}/failures")
async def failures(db: Db, learner: CurrentLearner, project_id: uuid.UUID) -> list[dict]:
    items = await service.list_failures(db, learner, project_id)
    nums = {v.id: v.number for v in await service.list_versions(db, learner, project_id)}
    return [failure_out(f, nums.get(f.architecture_version_id)) for f in items]


@router.post("/projects/{project_id}/failures", status_code=status.HTTP_201_CREATED)
async def start_failure(db: Db, learner: CurrentLearner, project_id: uuid.UUID, body: FailureIn) -> dict:
    fa = await service.start_failure(db, learner, project_id, body.scenario)
    v = await db.get(ArchitectureVersion, fa.architecture_version_id)
    return failure_out(fa, v.number)


@router.get("/failures/{attempt_id}")
async def failure(db: Db, learner: CurrentLearner, attempt_id: uuid.UUID) -> dict:
    fa, _ = await service.load_failure(db, learner, attempt_id)
    v = await db.get(ArchitectureVersion, fa.architecture_version_id)
    return failure_out(fa, v.number)


@router.post("/failures/{attempt_id}/respond")
async def respond_failure(request: Request, db: Db, learner: CurrentLearner, llm: LLM, attempt_id: uuid.UUID, body: FailureAnswer) -> dict:
    fa = await service.respond_failure(db, request.app.state.settings, llm, learner, attempt_id, body.impact, body.mitigation)
    v = await db.get(ArchitectureVersion, fa.architecture_version_id)
    out = failure_out(fa, v.number)
    if fa.status == "evaluated":
        await sync_mastery_best_effort(request, db, learner)
    return out


# ---- dashboard


@router.get("/dashboard")
async def dashboard(db: Db, learner: CurrentLearner) -> dict:
    ps = await service.list_projects(db, learner, limit=200)
    chs = await service.list_challenges(db)
    versions = await service.versions_by_id(db, {c.current_version_id for c in chs if c.current_version_id}
                                            | {p.challenge_version_id for p in ps})
    by_id = {c.id: c for c in chs}
    evals = await service.evaluations_for(db, learner, limit=200)

    best: dict[int, float | None] = {p.challenge_id: None for p in ps}
    weak: dict[str, list[int]] = {}
    for ev, p, _ in evals:
        if ev.status == "evaluated":
            s = float(ev.total_score)
            best[p.challenge_id] = max(best.get(p.challenge_id) or 0.0, s)
            for c in ev.result["criteria"]:
                weak.setdefault(c["criterion"], []).append(c["score"] if c["evidence_status"] == "observed" else 0)
    weak_criteria = sorted((k for k, v in weak.items() if sum(v) / (2 * len(v)) < 0.5),
                           key=lambda k: sum(weak[k]) / len(weak[k]))
    passed_levels = {by_id[cid].level.value for cid, b in best.items() if b is not None and b >= 0.5 and cid in by_id}

    mastery_rows = (await db.execute(
        select(Skill.slug, Skill.title, SkillMastery).join(SkillMastery, SkillMastery.skill_id == Skill.id)
        .where(SkillMastery.learner_id == learner.id))).all()
    mastered = {slug for slug, _, m in mastery_rows if m.demonstrated_level is not None}
    design_skills = {s for c in chs for s in versions[c.current_version_id].content["skills"]}
    goal = await db.scalar(select(LearnerGoal).join(Skill, Skill.id == LearnerGoal.skill_id).where(
        LearnerGoal.learner_id == learner.id, Skill.slug == "system-design"))
    target = {"beginner": "beginner", "intermediate": "intermediate", "advanced": "senior"}.get(
        goal.target_level.value if goal else "", None)

    rec = service.recommend_challenge(
        [(c, versions[c.current_version_id]) for c in chs], attempted=best, weak_criteria=weak_criteria,
        mastered_skills=mastered, target_level=target, passed_levels=passed_levels)

    competency_input = [(ev, p.challenge_id) for ev, p, _ in evals]
    return {
        "continue": [project_out(p, by_id.get(p.challenge_id), versions[p.challenge_version_id].title)
                     | {"graph": None, "explanation": None, "components": len(p.graph.get("nodes", []))} for p in ps[:6]],
        "challenges": [{"slug": c.slug, "title": versions[c.current_version_id].title, "level": c.level,
                        "attempted": c.id in best, "best_score": best.get(c.id)} for c in chs],
        "reviews": [evaluation_out(ev, v) | {"project_title": p.title, "result": None} for ev, p, v in evals[:10]],
        "weak_criteria": [{"criterion": k, "description": CRITERIA[k],
                           "average": round(sum(weak[k]) / (2 * len(weak[k])), 3), "evaluations": len(weak[k])}
                          for k in weak_criteria[:5]],
        "skills": [{"slug": slug, "title": title, "state": m.state, "level": m.demonstrated_level,
                    "reasoning_score": _f(m.reasoning_score), "evidence_count": m.evidence_count}
                   for slug, title, m in mastery_rows if slug in design_skills],
        "competencies": service.competency_profile(competency_input),
        "recommended": rec,
        "evidence_rule": f"Competencies need evaluations from at least {service.MIN_ASSESSMENTS} different challenges.",
    }

