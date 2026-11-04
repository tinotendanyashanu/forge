"""FORGE OPS: production engineering simulator endpoints (Milestone 7).

Everything here is simulated. No endpoint executes commands or touches real
infrastructure; the console is a strict allowlist of read-only queries.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentLearner, Db, get_llm, sync_mastery_best_effort
from app.db.models import IncidentEvaluation, IncidentMessage, Postmortem, Skill, SkillMastery
from app.ops import engine as E
from app.ops import service
from app.ops.catalog import MODES, POSTMORTEM_SECTIONS, RCA_CRITERIA, RUBRIC_VERSION
from app.ops.commander import EVALUATION_VERSION, PROMPT_VERSION
from app.ops.scenario import COMMANDS, METRICS

public = APIRouter(prefix="/ops", tags=["ops"])
router = APIRouter(prefix="/ops", tags=["ops"])
LLM = Annotated[object, Depends(get_llm)]
Mode = Literal["guided", "interview", "commander", "postmortem"]
EvidenceId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(max_length=96)
    mode: Mode = "commander"
    fresh: bool = False


class ActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(max_length=64)
    client_action_id: uuid.UUID


class CommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, max_length=300)
    client_action_id: uuid.UUID


class PinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: EvidenceId
    pinned: bool = True
    note: str = Field(default="", max_length=1000)


class HypothesisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=2000)
    status: Literal["open", "supported", "rejected"] = "open"
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=12)


class NotesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = Field(max_length=22000)


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=6000)
    client_message_id: uuid.UUID
    mode: Mode = "commander"


class ResolveIn(service.RcaIn):
    client_action_id: uuid.UUID


def _f(x) -> float | None:
    return None if x is None else float(x)


def message_out(m: IncidentMessage) -> dict:
    return {"id": str(m.id), "seq": m.seq, "role": m.role, "kind": m.kind, "mode": m.mode, "content": m.content,
            "cited_evidence": m.cited_evidence, "provider": m.provider, "model": m.model, "created_at": m.created_at}


def evaluation_out(e: IncidentEvaluation) -> dict:
    return {"id": str(e.id), "kind": e.kind, "status": e.status, "error_code": e.error_code,
            "total_score": _f(e.total_score), "model_total_score": _f(e.model_total_score), "confidence": _f(e.confidence),
            "result": e.result, "injection_suspected": e.injection_suspected, "mastery_eligible": e.mastery_eligible,
            "postmortem_revision": e.postmortem_revision,
            "versions": {"evaluation": e.evaluation_version, "rubric": e.rubric_version,
                         "scenario_version_id": e.scenario_version_id, "provider": e.provider, "model": e.model},
            "usage": {"prompt_tokens": e.prompt_tokens, "completion_tokens": e.completion_tokens,
                      "llm_attempts": e.llm_attempts, "approximate_cost": None},
            "created_at": e.created_at, "completed_at": e.completed_at}


def postmortem_out(pm: Postmortem) -> dict:
    return {"revision": pm.revision, "content": pm.content, "created_at": pm.created_at, "updated_at": pm.updated_at,
            "sections": [{"key": k, "title": v} for k, v in POSTMORTEM_SECTIONS.items()]}


def summary_out(sess, sc, version) -> dict:
    st = service.state_of(sess)
    return {"id": str(sess.id), "scenario": {"slug": sc.slug, "title": version.title, "level": sc.level},
            "status": sess.status, "mode": sess.mode, "minute": st.minute, "outcome_score": _f(sess.outcome_score),
            "success": sess.success, "created_at": sess.created_at, "updated_at": sess.updated_at, "ended_at": sess.ended_at}


# ---------------------------------------------------------------- public catalogue


@public.get("/catalog")
async def catalog() -> dict:
    return {"metrics": METRICS, "commands": list(COMMANDS), "modes": MODES, "rca_criteria": RCA_CRITERIA,
            "postmortem_sections": POSTMORTEM_SECTIONS, "rubric_version": RUBRIC_VERSION}


@public.get("/scenarios")
async def scenarios(db: Db) -> list[dict]:
    out = []
    for sc, v in await service.list_scenarios(db):
        p = service.public_scenario(sc, v)
        out.append({k: p[k] for k in ("slug", "level", "version", "title", "summary", "skills", "competencies")})
    return out


@public.get("/scenarios/{slug}")
async def scenario(db: Db, slug: str) -> dict:
    sc, v = await service.get_scenario(db, slug)
    return service.public_scenario(sc, v)


# ---------------------------------------------------------------- learner routes


@router.get("/status")
async def ops_status(request: Request, llm: LLM) -> dict:
    name = getattr(llm, "name", "disabled")
    return {"llm": {"provider": name, "model": getattr(llm, "model", None), "configured": name != "disabled"},
            "prompt_version": PROMPT_VERSION, "evaluation_version": EVALUATION_VERSION, "rubric_version": RUBRIC_VERSION,
            "ai_calls_per_hour": request.app.state.settings.ops_llm_calls_per_hour}


@router.get("/dashboard")
async def dashboard(db: Db, learner: CurrentLearner) -> dict:
    rows = await service.list_sessions(db, learner, limit=200)
    scs = await service.list_scenarios(db)
    sessions = [s for s, _, _ in rows]
    mistakes = service.recurring_mistakes(sessions)
    best: dict[int, float] = {}
    for s in sessions:
        if s.outcome_score is not None:
            best[s.scenario_id] = max(best.get(s.scenario_id, 0.0), float(s.outcome_score))
    skill_slugs = {sl for _, v in scs for sl in v.content["skills"]}
    mastery = (await db.execute(select(Skill.slug, Skill.title, SkillMastery)
                                .join(SkillMastery, SkillMastery.skill_id == Skill.id)
                                .where(SkillMastery.learner_id == learner.id, Skill.slug.in_(skill_slugs)))).all()
    return {
        "active": [summary_out(*r) for r in rows if r[0].status not in E.CLOSED][:6],
        "history": [summary_out(*r) for r in rows if r[0].status in E.CLOSED][:20],
        "scenarios": [{"slug": sc.slug, "title": v.title, "level": sc.level, "summary": v.content["summary"],
                       "attempted": any(s.scenario_id == sc.id for s in sessions), "best_score": best.get(sc.id)}
                      for sc, v in scs],
        "mistakes": mistakes,
        "recommended": service.recommend(scs, sessions, mistakes),
        "competencies": service.competencies(rows),
        "skills": [{"slug": sl, "title": t, "state": m.state, "level": m.demonstrated_level,
                    "practical_score": _f(m.practical_score), "debugging_score": _f(m.debugging_score),
                    "evidence_count": m.evidence_count} for sl, t, m in mastery],
        "evidence_rule": f"Competencies need verified outcomes from at least {service.COMPETENCY_MIN_SCENARIOS} different incidents; "
                         "mastery levels follow the adaptive engine's rules (several sessions, distinct subjects).",
    }


@router.get("/sessions")
async def sessions(db: Db, learner: CurrentLearner) -> list[dict]:
    return [summary_out(*r) for r in await service.list_sessions(db, learner)]


@router.post("/sessions")
async def start(db: Db, learner: CurrentLearner, body: StartIn, request: Request):
    from fastapi.responses import JSONResponse
    sess, created = await service.start_session(db, learner, body.scenario, body.mode, fresh=body.fresh)
    s, v, spec = await service.load_session(db, learner, sess.id)
    view = await service.session_view(db, s, v, spec)
    return JSONResponse(status_code=201 if created else 200, content=_jsonable(view))


def _jsonable(x):
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(x)


@router.get("/sessions/{sid}")
async def session(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> dict:
    s, v, spec = await service.load_session(db, learner, sid)
    return await service.session_view(db, s, v, spec)


@router.post("/sessions/{sid}/actions")
async def action(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: ActionIn) -> dict:
    result = await service.perform_action(db, learner, sid, body.action_id, body.client_action_id)
    s, v, spec = await service.load_session(db, learner, sid)
    return {"result": result, "session": await service.session_view(db, s, v, spec)}


@router.post("/sessions/{sid}/commands")
async def command(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: CommandIn) -> dict:
    return await service.run_command(db, learner, sid, body.command, body.client_action_id)


@router.get("/sessions/{sid}/logs")
async def logs(db: Db, learner: CurrentLearner, sid: uuid.UUID,
               service_: Annotated[str | None, Query(alias="service", max_length=64)] = None,
               level: Annotated[Literal["debug", "info", "warning", "error", "critical"] | None, Query()] = None,
               request_id: Annotated[str | None, Query(max_length=64)] = None,
               search: Annotated[str | None, Query(max_length=80)] = None,
               since: Annotated[int | None, Query(ge=-10000, le=10000)] = None,
               until: Annotated[int | None, Query(ge=-10000, le=10000)] = None) -> list[dict]:
    s, _, spec = await service.load_session(db, learner, sid)
    return service.filter_logs(spec, service.state_of(s), service=service_, level=level, request_id=request_id,
                               search=search, since=since, until=until)


@router.get("/sessions/{sid}/metrics")
async def metrics(db: Db, learner: CurrentLearner, sid: uuid.UUID,
                  keys: Annotated[list[str] | None, Query(max_length=40)] = None,
                  window: Annotated[int, Query(ge=5, le=240)] = 60) -> list[dict]:
    s, _, spec = await service.load_session(db, learner, sid)
    return service.metrics_view(spec, service.state_of(s), keys, window)


@router.get("/sessions/{sid}/traces")
async def traces(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    s, _, spec = await service.load_session(db, learner, sid)
    return E.visible_traces(spec, service.state_of(s))


@router.get("/sessions/{sid}/deployments")
async def deployments(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    s, _, spec = await service.load_session(db, learner, sid)
    return E.visible_deployments(spec, service.state_of(s))


@router.get("/sessions/{sid}/artifacts")
async def artifacts(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    s, _, spec = await service.load_session(db, learner, sid)
    return E.visible_artifacts(spec, service.state_of(s))


@router.post("/sessions/{sid}/evidence")
async def pin(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: PinIn) -> dict:
    return {"pinned": await service.pin(db, learner, sid, body.evidence_id, body.note, body.pinned)}


@router.post("/sessions/{sid}/hypotheses", status_code=status.HTTP_201_CREATED)
async def add_hypothesis(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: HypothesisIn) -> dict:
    h = await service.save_hypothesis(db, learner, sid, None, body.statement, body.status, body.evidence_ids)
    return {"number": h.number, "statement": h.statement, "status": h.status, "evidence_ids": h.evidence_ids}


@router.put("/sessions/{sid}/hypotheses/{number}")
async def update_hypothesis(db: Db, learner: CurrentLearner, sid: uuid.UUID, number: int, body: HypothesisIn) -> dict:
    h = await service.save_hypothesis(db, learner, sid, number, body.statement, body.status, body.evidence_ids)
    return {"number": h.number, "statement": h.statement, "status": h.status, "evidence_ids": h.evidence_ids}


@router.put("/sessions/{sid}/notes")
async def notes(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: NotesIn) -> dict:
    await service.save_notes(db, learner, sid, body.notes)
    return {"saved": True}


@router.get("/sessions/{sid}/messages")
async def messages(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    await service.load_session(db, learner, sid)
    return [message_out(m) for m in await service.messages_of(db, sid)]


@router.post("/sessions/{sid}/messages")
async def send(request: Request, db: Db, learner: CurrentLearner, llm: LLM, sid: uuid.UUID, body: MessageIn) -> dict:
    msgs = await service.send_message(db, request.app.state.settings, llm, learner, sid, body.content,
                                      body.client_message_id, body.mode)
    return {"messages": [message_out(m) for m in msgs]}


@router.post("/sessions/{sid}/resolve")
async def resolve(request: Request, db: Db, learner: CurrentLearner, llm: LLM, sid: uuid.UUID, body: ResolveIn) -> dict:
    rca = service.RcaIn(**body.model_dump(exclude={"client_action_id"}))
    await service.resolve(db, request.app.state.settings, llm, learner, sid, rca, body.client_action_id)
    await sync_mastery_best_effort(request, db, learner)
    s, v, spec = await service.load_session(db, learner, sid)
    return {"session": await service.session_view(db, s, v, spec),
            "evaluations": [evaluation_out(e) for e in await service.evaluations_of(db, sid)]}


@router.post("/sessions/{sid}/review")
async def retry_review(request: Request, db: Db, learner: CurrentLearner, llm: LLM, sid: uuid.UUID) -> dict:
    await service.retry_rca_review(db, request.app.state.settings, llm, learner, sid)
    await sync_mastery_best_effort(request, db, learner)
    return {"evaluations": [evaluation_out(e) for e in await service.evaluations_of(db, sid)]}


@router.get("/sessions/{sid}/evaluations")
async def evaluations(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    await service.load_session(db, learner, sid)
    return [evaluation_out(e) for e in await service.evaluations_of(db, sid)]


@router.post("/sessions/{sid}/abandon")
async def abandon(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> dict:
    await service.abandon(db, learner, sid)
    s, v, spec = await service.load_session(db, learner, sid)
    return await service.session_view(db, s, v, spec)


@router.post("/sessions/{sid}/reset", status_code=status.HTTP_201_CREATED)
async def reset(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> dict:
    new = await service.reset(db, learner, sid)
    s, v, spec = await service.load_session(db, learner, new.id)
    return await service.session_view(db, s, v, spec)


@router.get("/sessions/{sid}/replay")
async def replay(db: Db, learner: CurrentLearner, sid: uuid.UUID, seq: Annotated[int | None, Query(ge=1)] = None) -> dict:
    return await service.replay(db, learner, sid, seq)


@router.get("/sessions/{sid}/postmortem")
async def postmortem(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> dict:
    return postmortem_out(await service.get_postmortem(db, learner, sid))


@router.put("/sessions/{sid}/postmortem")
async def save_postmortem(db: Db, learner: CurrentLearner, sid: uuid.UUID, body: service.PostmortemIn) -> dict:
    return postmortem_out(await service.save_postmortem(db, learner, sid, body))


@router.get("/sessions/{sid}/postmortem/revisions")
async def postmortem_revisions(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> list[dict]:
    return [{"revision": r.revision, "content": r.content, "created_at": r.created_at}
            for r in await service.postmortem_revisions(db, learner, sid)]


@router.get("/sessions/{sid}/postmortem/export", response_class=PlainTextResponse)
async def export_postmortem(db: Db, learner: CurrentLearner, sid: uuid.UUID) -> PlainTextResponse:
    pm = await service.get_postmortem(db, learner, sid)
    s, _, spec = await service.load_session(db, learner, sid)
    return PlainTextResponse(service.postmortem_markdown(spec, s, pm), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="postmortem-{spec.slug}.md"'})


@router.post("/sessions/{sid}/postmortem/review")
async def review_postmortem(request: Request, db: Db, learner: CurrentLearner, llm: LLM, sid: uuid.UUID) -> dict:
    return evaluation_out(await service.review_postmortem(db, request.app.state.settings, llm, learner, sid))

