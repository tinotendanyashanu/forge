"""FORGE Career: readiness, assessments, reports, roadmap and job matching (Milestone 8)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.workspace.progress import engineering_portfolio
from app.api.deps import CurrentLearner, Db, get_llm
from app.career import jobs as jobmod
from app.career import roadmap as roadmapmod
from app.career import service
from app.career.content import JudgmentScenario, Template, digest, load_content
from app.career.readiness import INSUFFICIENT, SENIORITY_NOTE, compare_reports
from app.db.models import CareerAttempt, CareerContentVersion, CareerJob, CareerResponse, CareerRoadmap
from app.services.errors import NotFound, Unprocessable

public = APIRouter(prefix="/career", tags=["career"])
router = APIRouter(prefix="/career", tags=["career"])
LLM = Annotated[object, Depends(get_llm)]
Track = Literal["fullstack", "backend", "frontend"]
Level = Literal["foundation", "junior", "mid", "senior"]


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: Track
    target_level: Level
    goal: str = Field(default="", max_length=500)
    experience: dict = Field(default_factory=dict)  # self-reported, context only


class AttemptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str = Field(max_length=96)


class ResponseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(max_length=96)
    content: str = Field(min_length=1, max_length=20000)
    client_id: uuid.UUID


class SnapshotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: Track
    target_level: Level


class JobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)
    description: str = Field(min_length=50, max_length=20000)


def _template_out(t: Template, version: int) -> dict:
    return {"slug": t.slug, "title": t.title, "track": t.track, "level": t.level, "purpose": t.purpose, "version": version,
            "time_limit_minutes": t.time_limit_minutes, "description": t.description, "objectives": t.objectives,
            "passing_criteria": t.passing_criteria, "critical_failures": t.critical_failures,
            "evidence_requirements": t.evidence_requirements,
            "sections": [{"key": s.key, "kind": s.kind, "title": s.title, "objectives": s.objectives,
                          "dimensions": s.dimensions, "weight": s.weight, "minutes": s.minutes, "critical": s.critical}
                         for s in t.sections]}


def _experience_view(exp: dict) -> dict:
    return {"self_reported": exp, "note": "Self-reported experience is context only. It never counts as evidence, and years "
                                          "of experience are not treated as proof of proficiency."}


# ---------------------------------------------------------------- public catalogue


@public.get("/framework")
async def framework(db: Db) -> dict:
    row, fw = await service.framework_of(db)
    coverage: dict[str, list[str]] = {d.key: [] for d in fw.dimensions}
    for _, t in await service.templates(db):
        for s in t.sections:
            for d in s.dimensions:
                coverage[d].append(f"{t.slug}/{s.key}")
    return {"version": fw.version, "version_number": row.number, "title": fw.title, "rules": fw.rules.model_dump(),
            "dimensions": [d.model_dump(exclude={"critical_mistakes"}) | {"verifiable": d.verifiable,
                                                                           "assessment_coverage": coverage[d.key]}
                           for d in fw.dimensions],
            "tracks": [t.model_dump() for t in fw.tracks], "seniority_note": SENIORITY_NOTE}


@public.get("/templates")
async def templates(db: Db) -> list[dict]:
    return [_template_out(t, v.number) for v, t in await service.templates(db) if not t.slug.startswith("job-")]


@public.get("/templates/{slug}")
async def template(db: Db, slug: str) -> dict:
    v = await service.current_version(db, "template", slug)
    return _template_out(Template.model_validate(v.content), v.number)


@public.get("/projects")
async def projects() -> list[dict]:
    return [p.model_dump() for p in load_content().projects]


# ---------------------------------------------------------------- profile & dashboard


@router.get("/profile")
async def get_profile(db: Db, learner: CurrentLearner) -> dict:
    p = await service.get_profile(db, learner)
    if p is None:
        return {"track": None, "target_level": None, "goal": "", **_experience_view({})}
    return {"track": p.track, "target_level": p.target_level, "goal": p.goal, **_experience_view(p.experience)}


@router.put("/profile")
async def put_profile(db: Db, learner: CurrentLearner, body: ProfileIn) -> dict:
    exp = {str(k)[:64]: str(v)[:500] for k, v in list(body.experience.items())[:12]}
    p = await service.save_profile(db, learner, track=body.track, target_level=body.target_level, goal=body.goal.strip(),
                                   experience=exp)
    return {"track": p.track, "target_level": p.target_level, "goal": p.goal, **_experience_view(p.experience)}


def _report_summary(r) -> dict:
    s = r.snapshot.get("readiness", {})
    return {"id": str(r.id), "kind": r.kind, "track": r.track, "target_level": r.target_level,
            "demonstrated_level": r.demonstrated_level, "target_status": r.target_status, "created_at": r.created_at,
            "coverage": s.get("target", {}).get("coverage"), "confidence": s.get("confidence"),
            "attempt_id": str(r.attempt_id) if r.attempt_id else None,
            "title": (r.snapshot.get("attempt") or {}).get("title") or "Readiness snapshot"}


def _attempt_summary(a: CareerAttempt) -> dict:
    return {"id": str(a.id), "title": a.title, "template": a.template_slug, "purpose": a.purpose, "track": a.track,
            "level": a.level, "status": a.status, "created_at": a.created_at, "started_at": a.started_at,
            "deadline_at": a.deadline_at, "finalized_at": a.finalized_at}


@router.get("/dashboard")
async def dashboard(db: Db, learner: CurrentLearner, track: Track | None = None, level: Level | None = None) -> dict:
    p = await service.get_profile(db, learner)
    track = track or (p.track if p else "fullstack")
    level = level or (p.target_level if p else "mid")
    live = await service.live_report(db, learner, track, level)
    live.pop("evidence", None)
    reps = await service.reports(db, learner, 100)
    atts = await service.attempts(db, learner, 50)
    tmpls = [t for _, t in await service.templates(db)]
    recommended = next((t for t in tmpls if t.track == track and t.level == level and t.purpose == "formal"), None) \
        or next((t for t in tmpls if t.track == "fullstack" and t.level == level), None)
    roadmap = await db.scalar(select(CareerRoadmap).where(CareerRoadmap.learner_id == learner.id)
                              .order_by(CareerRoadmap.created_at.desc()).limit(1))
    return {
        "profile": {"track": track, "target_level": level, "goal": p.goal if p else "", "configured": p is not None,
                    **_experience_view(p.experience if p else {})},
        "readiness": live,
        "headline": live["target"]["message"] or None,
        "insufficient_message": INSUFFICIENT,
        "active_attempts": [_attempt_summary(a) for a in atts if a.status in ("created", "in_progress")],
        "attempts": [_attempt_summary(a) for a in atts[:10]],
        "reports": [_report_summary(r) for r in reps[:20]],
        "progress": [{"date": r.created_at, "demonstrated_level": r.demonstrated_level, "target_status": r.target_status,
                      "coverage": r.snapshot.get("readiness", {}).get("target", {}).get("coverage"), "kind": r.kind,
                      "id": str(r.id)} for r in reversed(reps) if r.track == track and r.target_level == level],
        "next_assessment": {"template": recommended.slug, "title": recommended.title,
                            "reassess_on": roadmap.snapshot.get("reassess_on") if roadmap else None} if recommended else None,
        "seniority_note": SENIORITY_NOTE,
        "engineering_projects": await engineering_portfolio(db, learner.id),
    }


@router.post("/snapshots", status_code=status.HTTP_201_CREATED)
async def snapshot(db: Db, learner: CurrentLearner, body: SnapshotIn) -> dict:
    return _report_summary(await service.save_snapshot(db, learner, body.track, body.target_level))


# ---------------------------------------------------------------- attempts


async def _attempt_view(db, learner, a: CareerAttempt) -> dict:
    t = await service.template_of(db, a)
    secs = await service.sections_of(db, a)
    closed = a.status in service.CLOSED
    resp = (await db.scalars(select(CareerResponse).where(CareerResponse.section_id.in_([s.id for s in secs] or [uuid.uuid4()])))).all()
    by_section: dict = {}
    for r in resp:
        show = closed or a.purpose != "formal"  # formal feedback is withheld until the attempt ends
        by_section.setdefault(r.section_id, {})[r.item_slug] = {
            "status": r.status, "error_code": r.error_code, "submitted_at": r.created_at, "content": r.content,
            "score": float(r.score) if show and r.score is not None else None,
            "result": r.result if show else None, "eligible": r.eligible if show else None}
    content = load_content()
    out_secs = []
    for s in secs:
        spec = next(x for x in t.sections if x.key == s.key)
        items = []
        if s.kind == "judgment":
            for slug in s.link.get("scenarios", []):
                v = await service.current_version(db, "judgment", slug)
                items.append(JudgmentScenario.model_validate(v.content).public() | {"response": by_section.get(s.id, {}).get(slug)})
        if s.kind == "take_home" and s.link.get("project"):
            pj = content.project(s.link["project"])
            items.append(pj.model_dump(exclude={"rubric"}) | {"rubric": list(pj.rubric.values()),
                                                                "response": by_section.get(s.id, {}).get(pj.slug)})
        out_secs.append({"key": s.key, "kind": s.kind, "title": s.title, "status": s.status, "position": s.position,
                         "objectives": spec.objectives, "dimensions": spec.dimensions, "minutes": spec.minutes,
                         "weight": spec.weight, "critical": spec.critical, "link": s.link, "items": items,
                         "result": s.result if (closed or a.purpose != "formal") else ({"recorded": True} if s.result else None),
                         "started_at": s.started_at, "completed_at": s.completed_at})
    report = None
    if closed:
        from app.db.models import CareerReport
        r = await db.scalar(select(CareerReport).where(CareerReport.attempt_id == a.id))
        report = str(r.id) if r else None
    return _attempt_summary(a) | {"server_time": service.now(), "time_limit_minutes": a.time_limit_minutes,
                                  "revision": a.revision, "template": _template_out(t, (await db.get(CareerContentVersion, a.template_version_id)).number),
                                  "sections": out_secs, "report_id": report}


@router.get("/attempts")
async def list_attempts(db: Db, learner: CurrentLearner) -> list[dict]:
    return [_attempt_summary(a) for a in await service.attempts(db, learner)]


@router.post("/attempts")
async def create_attempt(db: Db, learner: CurrentLearner, body: AttemptIn):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    a, created = await service.create_attempt(db, learner, body.template)
    return JSONResponse(status_code=201 if created else 200, content=jsonable_encoder(await _attempt_view(db, learner, a)))


@router.get("/attempts/{aid}")
async def get_attempt(request: Request, db: Db, learner: CurrentLearner, llm: LLM, aid: uuid.UUID) -> dict:
    a = await service.load_attempt(db, learner, aid)
    if a.status == "in_progress" and service.deadline_passed(a):
        await service.finalize(db, request.app.state.settings, llm, learner, aid, expired=True)
        a = await service.load_attempt(db, learner, aid)
    return await _attempt_view(db, learner, a)


@router.post("/attempts/{aid}/start")
async def start(db: Db, learner: CurrentLearner, aid: uuid.UUID) -> dict:
    a = await service.start_attempt(db, learner, aid)
    return await _attempt_view(db, learner, a)


@router.post("/attempts/{aid}/sections/{key}/start")
async def start_section(request: Request, db: Db, learner: CurrentLearner, llm: LLM, aid: uuid.UUID, key: str) -> dict:
    await service.start_section(db, request.app.state.settings, llm, learner, aid, key)
    return await _attempt_view(db, learner, await service.load_attempt(db, learner, aid))


@router.post("/attempts/{aid}/sections/{key}/complete")
async def complete_section(request: Request, db: Db, learner: CurrentLearner, llm: LLM, aid: uuid.UUID, key: str) -> dict:
    await service.complete_section(db, request.app.state.settings, llm, learner, aid, key)
    return await _attempt_view(db, learner, await service.load_attempt(db, learner, aid))


@router.post("/attempts/{aid}/sections/{key}/responses")
async def respond(request: Request, db: Db, learner: CurrentLearner, llm: LLM, aid: uuid.UUID, key: str, body: ResponseIn) -> dict:
    await service.submit_response(db, request.app.state.settings, llm, learner, aid, key, body.item, body.content, body.client_id)
    return await _attempt_view(db, learner, await service.load_attempt(db, learner, aid))


@router.post("/attempts/{aid}/finalize")
async def finalize(request: Request, db: Db, learner: CurrentLearner, llm: LLM, aid: uuid.UUID) -> dict:
    a = await service.load_attempt(db, learner, aid)
    r = await service.finalize(db, request.app.state.settings, llm, learner, aid,
                               expired=a.status == "in_progress" and service.deadline_passed(a))
    return {"report_id": str(r.id)}


@router.post("/attempts/{aid}/abandon")
async def abandon(db: Db, learner: CurrentLearner, aid: uuid.UUID) -> dict:
    return _attempt_summary(await service.abandon(db, learner, aid))


# ---------------------------------------------------------------- reports


@router.get("/reports")
async def list_reports(db: Db, learner: CurrentLearner) -> list[dict]:
    return [_report_summary(r) for r in await service.reports(db, learner)]


@router.get("/reports/{rid}")
async def get_report(db: Db, learner: CurrentLearner, rid: uuid.UUID) -> dict:
    r = await service.load_report(db, learner, rid)
    fv = await db.get(CareerContentVersion, r.framework_version_id)
    return _report_summary(r) | {"snapshot": r.snapshot, "framework_version_number": fv.number}


@router.get("/reports/{rid}/compare")
async def compare(db: Db, learner: CurrentLearner, rid: uuid.UUID, with_: Annotated[uuid.UUID, Query(alias="with")]) -> dict:
    new = await service.load_report(db, learner, rid)
    old = await service.load_report(db, learner, with_)
    return {"from": _report_summary(old), "to": _report_summary(new),
            "dimensions": compare_reports(old.snapshot["readiness"], new.snapshot["readiness"]),
            "note": None if old.snapshot["readiness"]["framework_version"] == new.snapshot["readiness"]["framework_version"]
            else "The reports use different framework versions; criteria may differ."}


# ---------------------------------------------------------------- roadmap


@router.get("/roadmap")
async def latest_roadmap(db: Db, learner: CurrentLearner) -> dict:
    rm = await db.scalar(select(CareerRoadmap).where(CareerRoadmap.learner_id == learner.id)
                         .order_by(CareerRoadmap.created_at.desc()).limit(1))
    if rm is None:
        raise NotFound("No roadmap yet")
    return rm.snapshot | {"id": str(rm.id), "report_id": str(rm.report_id), "created_at": rm.created_at}


@router.post("/roadmap", status_code=status.HTTP_201_CREATED)
async def roadmap(db: Db, learner: CurrentLearner, track: Track | None = None, level: Level | None = None) -> dict:
    """Records a readiness snapshot for the target and builds a roadmap from it."""
    p = await service.get_profile(db, learner)
    track = track or (p.track if p else "fullstack")
    level = level or (p.target_level if p else "mid")
    rep = await service.save_snapshot(db, learner, track, level)
    _, fw = await service.framework_of(db, rep.framework_version_id)
    snap = await roadmapmod.build(db, fw, learner.id, rep.snapshot["readiness"], p.goal if p else "")
    rm = CareerRoadmap(learner_id=learner.id, report_id=rep.id, snapshot=snap)
    db.add(rm)
    await db.commit()
    return snap | {"id": str(rm.id), "report_id": str(rep.id)}


# ---------------------------------------------------------------- jobs


def _job_out(j: CareerJob) -> dict:
    return {"id": str(j.id), "title": j.title, "created_at": j.created_at, "extraction": j.extraction, "mapping": j.mapping,
            "method": j.extraction_method, "ai_error": j.ai_error, "provider": j.provider, "model": j.model,
            "has_assessment": j.template_version_id is not None}


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(request: Request, db: Db, learner: CurrentLearner, llm: LLM, body: JobIn) -> dict:
    settings = request.app.state.settings
    text_ = body.description.strip()
    extraction = jobmod.keyword_extract(text_)
    extraction["injection_suspected"] = jobmod.injection_flag(text_)
    _, fw = await service.framework_of(db)
    ai, ai_error, provider, model = None, None, None, None
    if getattr(llm, "name", "disabled") != "disabled":
        await service.check_rate(db, settings, learner)
        await db.commit()
        ai, out = await jobmod.ai_extract(llm, fw, text_, settings.llm_max_repair_attempts)
        provider, model = out.provider or getattr(llm, "name", None), out.model or getattr(llm, "model", None)
        if ai is None:
            ai_error = out.error_code
    else:
        ai_error = "provider_not_configured"
    p = await service.get_profile(db, learner)
    live = await service.live_report(db, learner, p.track if p else "fullstack", ai and ai.get("seniority") or extraction["seniority"])
    mapping = jobmod.build_mapping(fw, extraction, ai, live)
    title = body.title.strip() or (ai or {}).get("title") or "Untitled role"
    j = CareerJob(learner_id=learner.id, title=title[:200], description=text_, extraction={"keyword": extraction, "ai": ai},
                  mapping=mapping, extraction_method="keyword+ai" if ai else "keyword", ai_error=ai_error,
                  provider=provider, model=model)
    db.add(j)
    await db.commit()
    await db.refresh(j)
    return _job_out(j)


@router.get("/jobs")
async def list_jobs(db: Db, learner: CurrentLearner) -> list[dict]:
    rows = (await db.scalars(select(CareerJob).where(CareerJob.learner_id == learner.id)
                             .order_by(CareerJob.created_at.desc()).limit(50))).all()
    return [{"id": str(j.id), "title": j.title, "created_at": j.created_at, "summary": j.mapping.get("summary"),
             "level": j.mapping.get("level")} for j in rows]


async def _load_job(db, learner, jid: uuid.UUID) -> CareerJob:
    j = await db.scalar(select(CareerJob).where(CareerJob.id == jid, CareerJob.learner_id == learner.id))
    if j is None:
        raise NotFound("Job description not found")
    return j


@router.get("/jobs/{jid}")
async def get_job(db: Db, learner: CurrentLearner, jid: uuid.UUID) -> dict:
    return _job_out(await _load_job(db, learner, jid))


@router.post("/jobs/{jid}/assessment", status_code=status.HTTP_201_CREATED)
async def job_assessment(db: Db, learner: CurrentLearner, jid: uuid.UUID) -> dict:
    """Builds a practice assessment from existing template sections covering the job's gaps and untested areas."""
    j = await _load_job(db, learner, jid)
    focus = {r["dimension"] for r in j.mapping["rows"] if r["status"] in ("gap", "untested")} or \
        {r["dimension"] for r in j.mapping["rows"]}
    level = j.mapping["level"]
    pool = [t for _, t in await service.templates(db) if t.purpose == "formal"]
    pool.sort(key=lambda t: (t.level != level, t.track != "fullstack"))
    sections, seen_kinds = [], set()
    for t in pool:
        for s in t.sections:
            if s.kind in seen_kinds or not set(s.dimensions) & focus:
                continue
            sections.append(s.model_dump(mode="json"))
            seen_kinds.add(s.kind)
    if not sections:
        raise Unprocessable("No FORGE assessment sections cover this job's requirements yet")
    tmpl = Template.model_validate({
        "slug": f"job-{str(j.id)[:8]}", "title": f"Preparation: {j.title}"[:200], "track": "fullstack", "level": level,
        "purpose": "practice", "time_limit_minutes": 0,
        "description": "A practice assessment generated from a job description. Untimed; results are labelled as practice.",
        "objectives": [f"Cover: {', '.join(sorted(focus))}"], "passing_criteria": "Practice: no pass or fail.",
        "critical_failures": [], "evidence_requirements": "Covers the job's gaps and untested requirements.",
        "sections": sections})
    content = tmpl.model_dump(mode="json")
    v = await db.scalar(select(CareerContentVersion).where(CareerContentVersion.kind == "template",
                                                           CareerContentVersion.key == tmpl.slug,
                                                           CareerContentVersion.content_hash == digest(content)))
    if v is None:
        v = CareerContentVersion(kind="template", key=tmpl.slug, number=1, content_hash=digest(content), content=content)
        db.add(v)
        await db.flush()
    j.template_version_id = v.id
    await db.commit()
    a, _ = await service.create_attempt(db, learner, tmpl.slug)
    return {"attempt_id": str(a.id)}

