"""FORGE Career: assessment attempts composed from existing FORGE modules.

* Ownership: every lookup filters on the learner (other ids behave as 404).
* Time: deadlines are set and enforced on the server; work after the deadline
  is ignored, and an expired attempt is finalized with what was done in time.
* Sections start real activities in M3/M5/M6/M7 and, on completion, snapshot
  only the results produced inside the section's time window.
* Finalization stores an immutable report snapshot (framework version, template
  version, evidence and results), so later content changes never alter it.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.workspace.progress import engineering_portfolio
from app.career import evidence as ev
from app.career import reviewer
from app.career.content import LEVELS, Framework, JudgmentScenario, Project, Template
from app.career.readiness import LEVEL_RANK, build_report
from app.core.config import Settings
from app.db.models import (
    ArchitectureProject,
    CareerAttempt,
    CareerContentVersion,
    CareerProfile,
    CareerReport,
    CareerResponse,
    CareerSection,
    CodingChallenge,
    CodingChallengeVersion,
    CodingSubmission,
    DesignChallenge,
    DesignEvaluation,
    FailureAttempt,
    IncidentScenario,
    IncidentSession,
    InterviewChallenge,
    InterviewEvaluation,
    InterviewSession,
    Learner,
    Skill,
)
from app.services.errors import Conflict, DomainError, NotFound, Unprocessable

LEVEL_TO_DIFFICULTY = {"foundation": "beginner", "junior": "beginner", "mid": "intermediate", "senior": "advanced"}
CLOSED = ("finalized", "expired", "abandoned")


class RateLimited(DomainError):
    status_code = 429


def now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- content versions


async def current_version(db: AsyncSession, kind: str, key: str) -> CareerContentVersion:
    row = await db.scalar(select(CareerContentVersion).where(
        CareerContentVersion.kind == kind, CareerContentVersion.key == key, CareerContentVersion.is_current))
    if row is None:
        raise NotFound(f"{kind} '{key}' not found")
    return row


async def framework_of(db: AsyncSession, version_id: int | None = None) -> tuple[CareerContentVersion, Framework]:
    row = (await db.get(CareerContentVersion, version_id)) if version_id else await current_version(db, "framework", "framework")
    return row, Framework.model_validate(row.content)


async def templates(db: AsyncSession) -> list[tuple[CareerContentVersion, Template]]:
    rows = (await db.scalars(select(CareerContentVersion).where(
        CareerContentVersion.kind == "template", CareerContentVersion.is_current).order_by(CareerContentVersion.id))).all()
    return [(r, Template.model_validate(r.content)) for r in rows]


# ---------------------------------------------------------------- profile


async def get_profile(db: AsyncSession, learner: Learner) -> CareerProfile | None:
    return await db.get(CareerProfile, learner.id)


async def save_profile(db: AsyncSession, learner: Learner, *, track: str, target_level: str, goal: str,
                       experience: dict) -> CareerProfile:
    p = await db.get(CareerProfile, learner.id, with_for_update=True)
    if p is None:
        p = CareerProfile(learner_id=learner.id, track=track, target_level=target_level, goal=goal, experience=experience)
        db.add(p)
    else:
        p.track, p.target_level, p.goal, p.experience, p.updated_at = track, target_level, goal, experience, now()
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------- attempts


async def create_attempt(db: AsyncSession, learner: Learner, slug: str, *, template_key: str | None = None) -> tuple[CareerAttempt, bool]:
    """Creates an attempt (or returns the open one for the same template)."""
    tv = await current_version(db, "template", template_key or slug)
    t = Template.model_validate(tv.content)
    fv, _ = await framework_of(db)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 9))"), {"k": f"{learner.id}:{t.slug}"})
    open_ = await db.scalar(select(CareerAttempt).where(
        CareerAttempt.learner_id == learner.id, CareerAttempt.template_slug == t.slug,
        CareerAttempt.status.in_(("created", "in_progress"))))
    if open_ is not None:
        await db.commit()
        return open_, False
    a = CareerAttempt(learner_id=learner.id, template_version_id=tv.id, framework_version_id=fv.id, template_slug=t.slug,
                      title=t.title, track=t.track, level=t.level, purpose=t.purpose, status="created",
                      time_limit_minutes=t.time_limit_minutes, revision=1)
    db.add(a)
    await db.flush()
    for i, s in enumerate(t.sections):
        db.add(CareerSection(attempt_id=a.id, position=i, key=s.key, kind=s.kind, title=s.title, status="pending"))
    await db.commit()
    await db.refresh(a)
    return a, True


async def load_attempt(db: AsyncSession, learner: Learner, attempt_id: uuid.UUID, *, lock: bool = False) -> CareerAttempt:
    q = select(CareerAttempt).where(CareerAttempt.id == attempt_id, CareerAttempt.learner_id == learner.id)
    a = await db.scalar(q.with_for_update() if lock else q)
    if a is None:
        raise NotFound("Assessment attempt not found")
    return a


async def template_of(db: AsyncSession, a: CareerAttempt) -> Template:
    return Template.model_validate((await db.get(CareerContentVersion, a.template_version_id)).content)


async def sections_of(db: AsyncSession, a: CareerAttempt) -> list[CareerSection]:
    return list((await db.scalars(select(CareerSection).where(CareerSection.attempt_id == a.id)
                                  .order_by(CareerSection.position))).all())


def _section_spec(t: Template, key: str):
    return next(s for s in t.sections if s.key == key)


def deadline_passed(a: CareerAttempt, at: datetime | None = None) -> bool:
    return a.deadline_at is not None and (at or now()) >= a.deadline_at


async def start_attempt(db: AsyncSession, learner: Learner, attempt_id: uuid.UUID) -> CareerAttempt:
    a = await load_attempt(db, learner, attempt_id, lock=True)
    if a.status == "created":
        a.status, a.started_at = "in_progress", now()
        a.deadline_at = a.started_at + timedelta(minutes=a.time_limit_minutes) if a.time_limit_minutes else None
        a.revision += 1
        a.updated_at = now()
    elif a.status in CLOSED:
        raise Conflict("This assessment has ended.")
    await db.commit()
    return a


async def ensure_open(db: AsyncSession, settings: Settings, llm, learner: Learner, a: CareerAttempt) -> None:
    """Rejects work on closed attempts; finalizes attempts whose deadline has passed."""
    if a.status in CLOSED:
        raise Conflict("This assessment has ended.")
    if a.status != "in_progress":
        raise Conflict("Start the assessment first.")
    if deadline_passed(a):
        await finalize(db, settings, llm, learner, a.id, expired=True)
        raise Conflict("Time is up. The assessment was finalized with the work completed before the deadline.")


# ---------------------------------------------------------------- section start


async def _unseen_coding(db: AsyncSession, learner: Learner, pick: dict, taken: set[str]) -> tuple[str | None, bool]:
    q = select(CodingChallenge, Skill.slug).join(Skill, Skill.id == CodingChallenge.skill_id).where(CodingChallenge.is_active)
    if pick.get("skill"):
        q = q.where(Skill.slug == pick["skill"])
    if pick.get("area"):
        q = q.where(CodingChallenge.area == pick["area"])
    if pick.get("difficulty"):
        q = q.where(CodingChallenge.difficulty == pick["difficulty"])
    rows = [c for c, _ in (await db.execute(q.order_by(CodingChallenge.slug))).all() if c.slug not in taken]
    if not rows:
        return None, False
    seen = set((await db.scalars(select(CodingSubmission.challenge_id).where(CodingSubmission.learner_id == learner.id))).all())
    fresh = [c for c in rows if c.id not in seen]
    return (fresh[0].slug, False) if fresh else (rows[0].slug, True)


DESIGN_LEVEL = {"beginner": "beginner", "intermediate": "intermediate", "advanced": "advanced", "senior": "senior"}
OPS_LEVEL = DESIGN_LEVEL


async def start_section(db: AsyncSession, settings: Settings, llm, learner: Learner, attempt_id: uuid.UUID, key: str) -> CareerSection:
    a = await load_attempt(db, learner, attempt_id, lock=True)
    await ensure_open(db, settings, llm, learner, a)
    sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key))
    if sec is None:
        raise NotFound("Section not found")
    if sec.status != "pending":
        await db.commit()
        return sec  # idempotent
    t = await template_of(db, a)
    spec = _section_spec(t, key)
    p = spec.params
    link: dict = {}
    status = "in_progress"
    if spec.kind == "interview":
        from app.db.enums import Difficulty, InterviewMode
        from app.interview.engine import start_interview
        from app.schemas.interviews import InterviewCreate
        await db.commit()  # start_interview manages its own transaction
        state = await start_interview(db, learner, InterviewCreate(
            skill_slug=p["skill"], difficulty=Difficulty(p["difficulty"]), mode=InterviewMode(p["mode"]),
            challenge_count=int(p.get("questions", 2))), llm)
        a = await load_attempt(db, learner, attempt_id, lock=True)
        sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key))
        link = {"interview_session_id": str(state.session.id), "url": f"/interview/{state.session.id}",
                "formal_rules": "No hints are offered before a first attempt; hints used are recorded."}
    elif spec.kind == "coding":
        from app.coding.service import execution_status
        st = await execution_status(db, settings)
        if not st["verified"]:
            status = "unavailable"
            link = {"reason": "No verified execution sandbox is available, so executable coding assessments are disabled. "
                              "Nothing was run. Start the sandbox worker (see docs/coding-lab.md) and start a new attempt.",
                    "problems": st.get("problems", [])}
        else:
            taken: set[str] = set()
            chosen, repeated = [], []
            for pick in p.get("picks", []):
                slug, rep = await _unseen_coding(db, learner, pick, taken)
                if slug:
                    taken.add(slug)
                    chosen.append(slug)
                    if rep:
                        repeated.append(slug)
            link = {"challenges": chosen, "repeated": repeated, "urls": {c: f"/lab/challenges/{c}" for c in chosen}}
    elif spec.kind == "design":
        from app.design import service as design
        lvl = DESIGN_LEVEL[p["level"]]
        chs = (await db.scalars(select(DesignChallenge).where(DesignChallenge.is_active, DesignChallenge.level == lvl)
                                .order_by(DesignChallenge.position))).all()
        done = set((await db.scalars(select(ArchitectureProject.challenge_id).where(ArchitectureProject.learner_id == learner.id))).all())
        pick = next((c for c in chs if c.id not in done), chs[0] if chs else None)
        if pick is None:
            raise Unprocessable("No design challenge at this level")
        _, version = await design.get_challenge(db, pick.slug)
        offered = version.content.get("failure_scenarios", [])
        change = next((c for c in p.get("constraint_changes", []) if c in offered), (p.get("constraint_changes") or offered)[0])
        await db.commit()
        proj = await design.create_project(db, learner, pick.slug, f"Assessment: {version.title}")
        a = await load_attempt(db, learner, attempt_id, lock=True)
        sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key))
        link = {"project_id": str(proj.id), "challenge": pick.slug, "constraint_change": change,
                "repeated": pick.id in done, "url": f"/design/projects/{proj.id}",
                "instructions": ["Clarify requirements and assumptions in the explanation",
                                 "Build the architecture and record ADRs for key decisions",
                                 "Start a review in Interview mode, answer follow-ups, then request an evaluation",
                                 f"Run the failure drill '{change}' (changed constraint) and submit impact and mitigation"]}
    elif spec.kind == "incident":
        from app.ops import service as ops
        lvl = OPS_LEVEL[p["level"]]
        scs = (await db.scalars(select(IncidentScenario).where(IncidentScenario.is_active, IncidentScenario.level == lvl)
                                .order_by(IncidentScenario.position))).all()
        done = set((await db.scalars(select(IncidentSession.scenario_id).where(IncidentSession.learner_id == learner.id))).all())
        pick = next((s for s in scs if s.id not in done), scs[0] if scs else None)
        if pick is None:
            raise Unprocessable("No incident scenario at this level")
        await db.commit()
        sess, _ = await ops.start_session(db, learner, pick.slug, "interview", fresh=True)
        a = await load_attempt(db, learner, attempt_id, lock=True)
        sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key))
        link = {"incident_session_id": str(sess.id), "scenario": pick.slug, "repeated": pick.id in done,
                "url": f"/ops/sessions/{sess.id}",
                "formal_rules": "The AI commander runs in interview mode and never confirms the root cause."}
    elif spec.kind == "judgment":
        from app.career.content import load_content
        content = load_content()
        answered = set((await db.scalars(select(CareerResponse.item_slug).where(
            CareerResponse.learner_id == learner.id, CareerResponse.kind == "judgment"))).all())
        pool = [s for s in content.judgment if LEVEL_RANK[s.level] <= LEVEL_RANK[p.get("level", "mid")]]
        chosen = [s for s in p.get("include", [])]
        for s in sorted(pool, key=lambda s: (s.slug in answered, s.slug)):
            if len(chosen) >= int(p.get("count", 1)):
                break
            if s.slug not in chosen:
                chosen.append(s.slug)
        link = {"scenarios": chosen, "repeated": [s for s in chosen if s in answered]}
    elif spec.kind == "take_home":
        link = {"project": p["project"]}
    sec.status, sec.started_at, sec.link = status, now(), link
    if status == "unavailable":
        sec.result = {"kind": sec.kind, "unavailable": True, "reason": link.get("reason"), "score": None}
    a.revision += 1
    a.updated_at = now()
    await db.commit()
    await db.refresh(sec)
    return sec


# ---------------------------------------------------------------- responses (judgment / take-home)


async def check_rate(db: AsyncSession, settings: Settings, learner: Learner) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 10))"), {"k": str(learner.id)})
    since = now() - timedelta(hours=1)
    from app.db.models import CareerJob
    n = (await db.scalar(select(func.count()).select_from(CareerResponse).where(
        CareerResponse.learner_id == learner.id, CareerResponse.created_at >= since)) or 0)
    n += (await db.scalar(select(func.count()).select_from(CareerJob).where(
        CareerJob.learner_id == learner.id, CareerJob.created_at >= since, CareerJob.provider.is_not(None))) or 0)
    if n >= settings.career_llm_calls_per_hour:
        raise RateLimited("AI evaluation limit reached for this hour. Try again later.")


async def submit_response(db: AsyncSession, settings: Settings, llm, learner: Learner, attempt_id: uuid.UUID, key: str,
                          item: str, content: str, client_id: uuid.UUID) -> CareerResponse:
    body = "\n".join(line.rstrip() for line in content.replace("\r\n", "\n").split("\n")).strip()
    if len(body) < 40:
        raise Unprocessable("Write at least a few sentences (40 characters or more).")
    if len(body) > 20000:
        raise Unprocessable("Responses are limited to 20,000 characters.")
    a = await load_attempt(db, learner, attempt_id, lock=True)
    dup = await db.scalar(select(CareerResponse).where(CareerResponse.learner_id == learner.id, CareerResponse.client_id == client_id))
    if dup is not None:
        await db.commit()
        return dup
    await ensure_open(db, settings, llm, learner, a)
    sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key))
    if sec is None or sec.kind not in ("judgment", "take_home"):
        raise NotFound("Section not found")
    if sec.status != "in_progress":
        raise Conflict("Start this section first." if sec.status == "pending" else "This section is closed.")
    items = sec.link.get("scenarios", []) if sec.kind == "judgment" else [sec.link.get("project")]
    if item not in items:
        raise NotFound("This item is not part of the section")
    existing = await db.scalar(select(CareerResponse).where(CareerResponse.section_id == sec.id, CareerResponse.item_slug == item))
    if existing is not None and existing.status != "ungraded":
        raise Conflict("You already answered this item. Formal answers can't be changed.")
    await check_rate(db, settings, learner)
    iv = await current_version(db, "judgment" if sec.kind == "judgment" else "project", item)
    if existing is not None:  # resubmission after an ungraded evaluation
        existing.content, existing.client_id, existing.status, existing.error_code = body, client_id, "pending", None
        resp = existing
    else:
        resp = CareerResponse(section_id=sec.id, learner_id=learner.id, kind=sec.kind, item_slug=item, item_version_id=iv.id,
                              content=body, client_id=client_id, status="pending", evaluation_version=reviewer.EVALUATION_VERSION,
                              provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"))
        db.add(resp)
    await db.commit()
    await db.refresh(resp)
    rid = resp.id
    if sec.kind == "judgment":
        out = await reviewer.review_judgment(llm, JudgmentScenario.model_validate(iv.content), body, settings.llm_max_repair_attempts)
    else:
        verified = await _linked_results(db, learner, Project.model_validate(iv.content).linked_challenges, sec.started_at, a.deadline_at)
        out = await reviewer.review_project(llm, Project.model_validate(iv.content), body, verified, settings.llm_max_repair_attempts)
    resp = await db.get(CareerResponse, rid, with_for_update=True)
    resp.provider, resp.model = out.provider or resp.provider, out.model or resp.model
    resp.prompt_tokens, resp.completion_tokens, resp.completed_at = out.prompt_tokens, out.completion_tokens, now()
    if out.ok:
        d = out.data
        resp.status, resp.score, resp.confidence, resp.result = "evaluated", d["score"], d["confidence"], d["result"]
        resp.injection_suspected, resp.eligible = d["injection_suspected"], d["eligible"]
    else:
        resp.status, resp.error_code = "ungraded", out.error_code or "provider_error"
    await db.commit()
    await db.refresh(resp)
    return resp


async def _linked_results(db: AsyncSession, learner: Learner, slugs: list[str], since: datetime | None,
                          until: datetime | None) -> dict:
    out = {}
    for slug in slugs:
        q = (select(CodingSubmission).join(CodingChallenge, CodingChallenge.id == CodingSubmission.challenge_id)
             .where(CodingSubmission.learner_id == learner.id, CodingChallenge.slug == slug,
                    CodingSubmission.executed, CodingSubmission.verified))
        if since:
            q = q.where(CodingSubmission.created_at >= since)
        if until:
            q = q.where(CodingSubmission.created_at <= until)
        best = (await db.scalars(q.order_by(CodingSubmission.passed.desc(), CodingSubmission.created_at.desc()).limit(1))).first()
        out[slug] = ({"submission_id": str(best.id), "passed": best.passed, "total": best.total, "all_passed": best.all_passed}
                     if best else None)
    return out


# ---------------------------------------------------------------- section completion


async def _section_result(db: AsyncSession, learner: Learner, a: CareerAttempt, sec: CareerSection, spec) -> dict:
    since, until = sec.started_at, a.deadline_at or now()
    link = sec.link or {}
    if sec.kind == "interview":
        sid = uuid.UUID(link["interview_session_id"])
        sess = await db.get(InterviewSession, sid)
        chs = (await db.scalars(select(InterviewChallenge).where(InterviewChallenge.session_id == sid)
                                .order_by(InterviewChallenge.position))).all()
        rows, scores = [], []
        for c in chs:
            e = await db.scalar(select(InterviewEvaluation).where(InterviewEvaluation.challenge_id == c.id)
                                .order_by(InterviewEvaluation.created_at.desc()).limit(1))
            evaluated = e is not None and e.status.value == "evaluated" and e.created_at <= until
            rows.append({"position": c.position, "status": c.status.value, "hints_used": c.hints_used,
                         "said_dont_know": c.said_dont_know,
                         "score": float(e.total_score) if evaluated else None,
                         "evaluation": e.status.value if e else "none"})
            if evaluated:
                scores.append(float(e.total_score))
        return {"kind": "interview", "session_status": sess.status.value, "questions": rows,
                "score": round(sum(scores) / len(rows), 3) if rows and scores else None,
                "evidence": "AI rubric (advisory)", "model": sess.model}
    if sec.kind == "coding":
        if sec.status == "unavailable":
            return {"kind": "coding", "unavailable": True, "reason": link.get("reason"), "score": None}
        res = await _linked_results(db, learner, link.get("challenges", []), since, until)
        rates = [(r["passed"] / r["total"]) if r and r["total"] else 0.0 for r in res.values()]
        return {"kind": "coding", "challenges": res, "repeated": link.get("repeated", []),
                "submission_ids": [r["submission_id"] for r in res.values() if r],
                "score": round(sum(rates) / len(rates), 3) if rates else None,
                "evidence": "Hidden tests in the verified sandbox (objective)"}
    if sec.kind == "design":
        pid = uuid.UUID(link["project_id"])
        evs = (await db.scalars(select(DesignEvaluation).where(
            DesignEvaluation.project_id == pid, DesignEvaluation.status == "evaluated",
            DesignEvaluation.created_at >= since, DesignEvaluation.created_at <= until)
            .order_by(DesignEvaluation.created_at.desc()))).all()
        fail = (await db.scalars(select(FailureAttempt).where(
            FailureAttempt.project_id == pid, FailureAttempt.scenario_slug == link.get("constraint_change"),
            FailureAttempt.status == "evaluated", FailureAttempt.created_at >= since,
            FailureAttempt.completed_at <= until).order_by(FailureAttempt.completed_at.desc()))).first()
        best = max((float(e.total_score) for e in evs), default=None)
        parts = [x for x in (best, float(fail.score) if fail else None) if x is not None]
        return {"kind": "design", "evaluations": len(evs), "architecture_score": best,
                "constraint_change": link.get("constraint_change"),
                "constraint_change_score": float(fail.score) if fail else None,
                "score": round(sum(parts) / 2, 3) if parts else None,  # missing half counts as zero
                "evidence": "AI architecture evaluation (advisory)"}
    if sec.kind == "incident":
        s = await db.get(IncidentSession, uuid.UUID(link["incident_session_id"]))
        o = s.outcome or {}
        resolved = s.outcome is not None and s.ended_at is not None and s.ended_at <= until
        return {"kind": "incident", "status": s.status, "resolved": resolved,
                "score": float(s.outcome_score) if resolved else None, "success": s.success if resolved else None,
                "harmful_actions": o.get("harmful_actions", []), "root_cause_correct": o.get("root_cause_correct"),
                "decisions": o.get("decisions"), "decision_flags": o.get("decision_flags", []),
                "lucky_guess": bool(resolved and o.get("root_cause_correct") and (o.get("decisions") or {}).get("informed", 1) == 0),
                "evidence": "Deterministic simulation outcome (verified)"}
    # judgment / take_home
    rs = (await db.scalars(select(CareerResponse).where(CareerResponse.section_id == sec.id))).all()
    items = link.get("scenarios") if sec.kind == "judgment" else [link.get("project")]
    by = {r.item_slug: r for r in rs}
    rows = [{"item": i, "status": by[i].status if i in by else "not_answered",
             "score": float(by[i].score) if i in by and by[i].score is not None else None} for i in items]
    vals = [r["score"] or 0.0 for r in rows]
    out = {"kind": sec.kind, "items": rows, "score": round(sum(vals) / len(vals), 3) if vals else None,
           "evidence": "AI rubric (advisory)"}
    if sec.kind == "take_home":
        out["linked_challenges"] = await _linked_results(db, learner, Project.model_validate(
            (await current_version(db, "project", link["project"])).content).linked_challenges, since, until)
        out["note"] = "The repository itself was not inspected; only linked sandbox challenges are verified."
    return out


async def complete_section(db: AsyncSession, settings: Settings, llm, learner: Learner, attempt_id: uuid.UUID, key: str) -> CareerSection:
    a = await load_attempt(db, learner, attempt_id, lock=True)
    sec = await db.scalar(select(CareerSection).where(CareerSection.attempt_id == a.id, CareerSection.key == key).with_for_update())
    if sec is None:
        raise NotFound("Section not found")
    if sec.status in ("completed", "skipped"):
        await db.commit()
        return sec  # idempotent
    await ensure_open(db, settings, llm, learner, a)
    if sec.status == "pending":
        raise Conflict("Start this section first.")
    t = await template_of(db, a)
    sec.result = await _section_result(db, learner, a, sec, _section_spec(t, key))
    sec.status = "completed" if sec.status == "in_progress" else sec.status
    sec.completed_at = now()
    a.revision += 1
    a.updated_at = now()
    await db.commit()
    await db.refresh(sec)
    return sec


# ---------------------------------------------------------------- finalize & reports


def _critical_failures(t: Template, sections: list[CareerSection], report: dict) -> list[str]:
    out = []
    for s in sections:
        r = s.result or {}
        if s.kind == "incident" and r.get("harmful_actions"):
            out.append(f"Harmful action during the incident: {', '.join(r['harmful_actions'])}")
        if s.kind == "coding" and (r.get("unavailable") or s.status == "unavailable"):
            out.append("Executable coding was unavailable (no verified sandbox): implementation evidence is missing.")
        if s.kind == "incident" and r.get("lucky_guess"):
            out.append("Incident resolved without any useful investigation first (possible lucky guess).")
    for g in report["critical_gaps"]:
        out.append(f"Critical gap in a gated competency: {g['title']}")
    return out


async def finalize(db: AsyncSession, settings: Settings, llm, learner: Learner, attempt_id: uuid.UUID,
                   *, expired: bool = False) -> CareerReport:
    a = await load_attempt(db, learner, attempt_id, lock=True)
    existing = await db.scalar(select(CareerReport).where(CareerReport.attempt_id == a.id))
    if existing is not None:
        await db.commit()
        return existing  # idempotent
    if a.status not in ("in_progress",) and not expired:
        raise Conflict("Only an assessment in progress can be finalized.")
    t = await template_of(db, a)
    secs = await sections_of(db, a)
    for s in secs:
        if s.status == "in_progress":
            s.result = await _section_result(db, learner, a, s, _section_spec(t, s.key))
            s.status, s.completed_at = "completed", now()
        elif s.status == "pending":
            s.status = "skipped"
            s.result = {"kind": s.kind, "skipped": True, "score": None}
    await db.flush()
    fv, fw = await framework_of(db, a.framework_version_id)
    items = await ev.collect(db, fw, learner.id)
    at = now()
    report = build_report(fw, a.track, a.level, items, at)
    weights = {s.key: s.weight for s in t.sections}
    scored = [(weights[s.key], (s.result or {}).get("score")) for s in secs]
    total_w = sum(w for w, _ in scored)
    attempt_items = [i for i in items if i.context == f"formal:{a.id}"]
    snapshot = {
        "kind": "assessment", "attempt": {
            "id": str(a.id), "title": a.title, "template": a.template_slug,
            "template_version": (await db.get(CareerContentVersion, a.template_version_id)).number,
            "purpose": a.purpose, "track": a.track, "level": a.level,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "deadline_at": a.deadline_at.isoformat() if a.deadline_at else None, "finalized_at": at.isoformat(),
            "expired": expired, "passing_criteria": t.passing_criteria,
        },
        "sections": [{"key": s.key, "title": s.title, "kind": s.kind, "status": s.status, "weight": weights[s.key],
                      "dimensions": _section_spec(t, s.key).dimensions, "result": s.result,
                      "started_at": s.started_at.isoformat() if s.started_at else None,
                      "completed_at": s.completed_at.isoformat() if s.completed_at else None} for s in secs],
        "section_summary": round(sum(w * (sc or 0.0) for w, sc in scored) / total_w, 3) if total_w else None,
        "critical_failures": _critical_failures(t, secs, report),
        "passed": report["target"]["status"] in ("ready", "ready_with_gaps") and not _critical_failures(t, secs, report),
        "readiness": report,
        "evidence": [i.to_json() for i in items],
        "attempt_evidence_ids": [i.id for i in attempt_items],
    }
    r = CareerReport(learner_id=learner.id, attempt_id=a.id, framework_version_id=fv.id, kind="assessment",
                     track=a.track, target_level=a.level, demonstrated_level=report["demonstrated_level"],
                     target_status=report["target"]["status"], snapshot=snapshot)
    db.add(r)
    a.status, a.finalized_at = ("expired" if expired else "finalized"), at
    a.revision += 1
    a.updated_at = at
    await db.commit()
    await db.refresh(r)
    return r


async def abandon(db: AsyncSession, learner: Learner, attempt_id: uuid.UUID) -> CareerAttempt:
    a = await load_attempt(db, learner, attempt_id, lock=True)
    if a.status in CLOSED:
        raise Conflict("This assessment has already ended.")
    a.status, a.finalized_at, a.updated_at = "abandoned", now(), now()
    await db.commit()
    return a


async def live_report(db: AsyncSession, learner: Learner, track: str, target: str) -> dict:
    _, fw = await framework_of(db)
    items = await ev.collect(db, fw, learner.id)
    return build_report(fw, track, target, items, now()) | {"evidence": [i.to_json() for i in items]}


async def save_snapshot(db: AsyncSession, learner: Learner, track: str, target: str) -> CareerReport:
    fv, fw = await framework_of(db)
    items = await ev.collect(db, fw, learner.id)
    rep = build_report(fw, track, target, items, now())
    r = CareerReport(learner_id=learner.id, framework_version_id=fv.id, kind="snapshot", track=track, target_level=target,
                     demonstrated_level=rep["demonstrated_level"], target_status=rep["target"]["status"],
                     snapshot={"kind": "snapshot", "readiness": rep, "evidence": [i.to_json() for i in items],
                               "engineering_projects": await engineering_portfolio(db, learner.id)})
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def load_report(db: AsyncSession, learner: Learner, report_id: uuid.UUID) -> CareerReport:
    r = await db.scalar(select(CareerReport).where(CareerReport.id == report_id, CareerReport.learner_id == learner.id))
    if r is None:
        raise NotFound("Report not found")
    return r


async def reports(db: AsyncSession, learner: Learner, limit: int = 50) -> list[CareerReport]:
    return list((await db.scalars(select(CareerReport).where(CareerReport.learner_id == learner.id)
                                  .order_by(CareerReport.created_at.desc()).limit(limit))).all())


async def attempts(db: AsyncSession, learner: Learner, limit: int = 50) -> list[CareerAttempt]:
    return list((await db.scalars(select(CareerAttempt).where(CareerAttempt.learner_id == learner.id)
                                  .order_by(CareerAttempt.created_at.desc()).limit(limit))).all())


def level_ok(x: str) -> str:
    if x not in LEVELS:
        raise Unprocessable("Unknown level")
    return x

