"""FORGE OPS service: server-authoritative incident sessions.

* Every lookup filters on the owner; another learner's ids behave like unknown ids.
* State-changing calls lock the session row, are idempotent by client id, and
  write an audit entry (accepted or rejected) plus a state snapshot.
* LLM calls never run inside a transaction.
* Hidden material (root cause, action quality, teaching notes) is only
  returned once the attempt has ended.
"""

import hashlib
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import (
    IncidentAction,
    IncidentEvaluation,
    IncidentEvidence,
    IncidentHypothesis,
    IncidentMessage,
    IncidentRca,
    IncidentScenario,
    IncidentScenarioVersion,
    IncidentSession,
    IncidentSnapshot,
    Learner,
    Postmortem,
    PostmortemRevision,
)
from app.design.graph import clean_text
from app.ops import commander as ai
from app.ops import engine as E
from app.ops.catalog import MISTAKES, POSTMORTEM_SECTIONS, RCA_FIELDS, RUBRIC_VERSION
from app.ops.scenario import METRICS, ScenarioSpec
from app.services.errors import Conflict, DomainError, NotFound, Unprocessable

MAX_AUDIT = 600
MAX_HYPOTHESES = 30
MAX_PINS = 40
PENDING_STALE_AFTER = timedelta(minutes=10)
LEVEL_ORDER = ["beginner", "intermediate", "advanced", "senior"]


class RateLimited(DomainError):
    status_code = 429


def _now() -> datetime:
    return datetime.now(UTC)


def clean_block(value: str, limit: int) -> str:
    out = "\n".join(clean_text(line) for line in value.replace("\r\n", "\n").split("\n")).strip()
    if len(out) > limit:
        raise Unprocessable(f"Text must be at most {limit} characters")
    return out


@lru_cache(maxsize=64)
def _spec_cached(version_id: int, content_hash: str, raw: str) -> ScenarioSpec:
    import json
    return ScenarioSpec.model_validate(json.loads(raw))


def spec_of(version: IncidentScenarioVersion) -> ScenarioSpec:
    import json
    return _spec_cached(version.id, version.content_hash, json.dumps(version.content, sort_keys=True))


# ---------------------------------------------------------------- scenarios


async def list_scenarios(db: AsyncSession) -> list[tuple[IncidentScenario, IncidentScenarioVersion]]:
    rows = await db.execute(
        select(IncidentScenario, IncidentScenarioVersion)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
        .where(IncidentScenario.is_active).order_by(IncidentScenario.position))
    return [tuple(r) for r in rows.all()]


async def get_scenario(db: AsyncSession, slug: str) -> tuple[IncidentScenario, IncidentScenarioVersion]:
    row = (await db.execute(
        select(IncidentScenario, IncidentScenarioVersion)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
        .where(IncidentScenario.slug == slug, IncidentScenario.is_active))).first()
    if row is None:
        raise NotFound("Incident scenario not found")
    return row[0], row[1]


def public_scenario(sc: IncidentScenario, version: IncidentScenarioVersion) -> dict:
    s = spec_of(version)
    return {
        "slug": sc.slug, "level": sc.level, "version": version.number, "title": s.title, "summary": s.summary,
        "business_context": s.business_context, "skills": s.skills, "competencies": s.competencies,
        "learning_outcomes": s.learning_outcomes, "initial_symptoms": s.initial_symptoms,
        "customer_impact": s.customer_impact,
        "services": [x.model_dump() for x in s.services],
    }


# ---------------------------------------------------------------- sessions


async def _audit(db: AsyncSession, sess: IncidentSession, before: E.SimState, after: E.SimState, *, kind: str,
                 accepted: bool, action_id: str | None = None, params: dict | None = None, reason: str | None = None,
                 result: dict | None = None, client_action_id: uuid.UUID | None = None, snapshot: bool = False) -> IncidentAction:
    seq = (await db.scalar(select(func.max(IncidentAction.seq)).where(IncidentAction.session_id == sess.id)) or 0) + 1
    if seq > MAX_AUDIT:
        raise Unprocessable("This attempt has reached its action limit. Resolve or reset it.")
    entry = IncidentAction(
        session_id=sess.id, seq=seq, client_action_id=client_action_id, kind=kind, action_id=action_id,
        params=params or {}, accepted=accepted, reason=reason, result=result or {},
        status_before=before.status, status_after=after.status, condition_before=before.condition,
        condition_after=after.condition, minute_before=before.minute, minute_after=after.minute,
    )
    db.add(entry)
    if snapshot:
        db.add(IncidentSnapshot(session_id=sess.id, seq=seq, state=after.to_json()))
    await db.flush()
    return entry


def _set_state(sess: IncidentSession, st: E.SimState) -> None:
    sess.state, sess.status = st.to_json(), st.status
    sess.updated_at = _now()
    sess.revision += 1


async def start_session(db: AsyncSession, learner: Learner, slug: str, mode: str, *, fresh: bool = False) -> tuple[IncidentSession, bool]:
    """Returns (session, created). An open attempt is resumed unless ``fresh``."""
    sc, version = await get_scenario(db, slug)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 7))"), {"k": f"{learner.id}:{sc.id}"})
    if not fresh:
        existing = await db.scalar(select(IncidentSession).where(
            IncidentSession.learner_id == learner.id, IncidentSession.scenario_id == sc.id,
            IncidentSession.status.not_in(E.CLOSED)).order_by(IncidentSession.created_at.desc()).limit(1))
        if existing is not None:
            await db.commit()
            return existing, False
    spec = spec_of(version)
    st = E.initial_state(spec)
    sess = IncidentSession(learner_id=learner.id, scenario_id=sc.id, version_id=version.id, status=st.status,
                           mode=mode, state=st.to_json(), notes="", revision=1)
    db.add(sess)
    await db.flush()
    await _audit(db, sess, st, st, kind="start", accepted=True, params={"mode": mode}, snapshot=True,
                 result={"outcome": "Incident opened."})
    await db.commit()
    await db.refresh(sess)
    return sess, True


async def load_session(db: AsyncSession, learner: Learner, sid: uuid.UUID, *, lock: bool = False):
    q = select(IncidentSession).where(IncidentSession.id == sid, IncidentSession.learner_id == learner.id)
    sess = await db.scalar(q.with_for_update() if lock else q)
    if sess is None:
        raise NotFound("Incident session not found")
    version = await db.get(IncidentScenarioVersion, sess.version_id)
    return sess, version, spec_of(version)


async def list_sessions(db: AsyncSession, learner: Learner, limit: int = 50):
    rows = await db.execute(
        select(IncidentSession, IncidentScenario, IncidentScenarioVersion)
        .join(IncidentScenario, IncidentScenario.id == IncidentSession.scenario_id)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentSession.version_id)
        .where(IncidentSession.learner_id == learner.id)
        .order_by(IncidentSession.updated_at.desc()).limit(limit))
    return [tuple(r) for r in rows.all()]


async def pinned_of(db: AsyncSession, sid: uuid.UUID) -> dict[str, str]:
    rows = await db.scalars(select(IncidentEvidence).where(IncidentEvidence.session_id == sid).order_by(IncidentEvidence.pinned_at))
    return {r.evidence_id: r.note for r in rows.all()}


async def hypotheses_of(db: AsyncSession, sid: uuid.UUID) -> list[IncidentHypothesis]:
    return list((await db.scalars(select(IncidentHypothesis).where(IncidentHypothesis.session_id == sid)
                                  .order_by(IncidentHypothesis.number))).all())


def state_of(sess: IncidentSession) -> E.SimState:
    return E.SimState.from_json(sess.state)


def actions_view(spec: ScenarioSpec, st: E.SimState) -> list[dict]:
    out = []
    for a in [E.OBSERVE, *spec.actions]:
        if not E.discovered(st, a):
            continue  # not yet discovered by an investigation
        reason = E.check(spec, st, a)
        out.append({"id": a.id, "kind": a.kind, "label": a.label, "description": a.description, "minutes": a.minutes,
                    "command": a.command, "done": st.done(a.id), "available": reason is None, "reason": reason})
    return out


def state_view(spec: ScenarioSpec, st: E.SimState, *, reveal: bool | None = None) -> dict:
    """Learner-facing state. Until the attempt ends, conditions are described by
    their symptoms only, and internal condition names are not exposed."""
    reveal = st.status in E.CLOSED if reveal is None else reveal
    cond = spec.conditions[st.condition]
    pub = E.public_condition(spec, st.condition, reveal=reveal)
    ok, verify_msg = E.recovery_check(spec, st)
    return {
        "status": st.status, "minute": st.minute, "clock": E.timestamp(spec, st.minute),
        "condition": {"name": st.condition if reveal else None, "label": pub["label"], "phase": cond.phase,
                      "summary": pub["summary"]},
        "health": E.health(spec, st.condition),
        "metrics_now": {k: E.metric_value(spec, st, k, st.minute) for k in E.metric_keys(spec)},
        "recovery": {"verified": ok, "message": verify_msg},
        "timeline": [{"minute": m, "condition": c if reveal else None,
                      "label": E.public_condition(spec, c, reveal=reveal)["summary" if not reveal else "label"],
                      "phase": spec.conditions[c].phase} for m, c in st.history],
    }


async def session_view(db: AsyncSession, sess: IncidentSession, version: IncidentScenarioVersion, spec: ScenarioSpec) -> dict:
    st = state_of(sess)
    sc = await db.get(IncidentScenario, sess.scenario_id)
    closed = st.status in E.CLOSED
    hyps = await hypotheses_of(db, sess.id)
    rca = await db.get(IncidentRca, sess.id)
    out = {
        "id": str(sess.id), "mode": sess.mode, "revision": sess.revision, "notes": sess.notes,
        "created_at": sess.created_at, "updated_at": sess.updated_at, "ended_at": sess.ended_at,
        "scenario": public_scenario(sc, version) | {"current_version": sc.current_version_id == version.id},
        "state": state_view(spec, st), "actions": actions_view(spec, st),
        "metric_catalog": [{"key": k, "service": k.split(".")[0], "metric": k.split(".")[1], **METRICS[k.split(".")[1]]}
                           for k in E.metric_keys(spec)],
        "pinned": await pinned_of(db, sess.id),
        "hypotheses": [{"id": str(h.id), "number": h.number, "statement": h.statement, "status": h.status,
                        "evidence_ids": h.evidence_ids, "updated_at": h.updated_at} for h in hyps],
        "evidence_counts": {"logs": len(E.visible_logs(spec, st)), "traces": len(E.visible_traces(spec, st)),
                            "deployments": len(E.visible_deployments(spec, st)), "artifacts": len(E.visible_artifacts(spec, st))},
        # Shuffled per attempt (deterministically) so authoring order never reveals the answer.
        "root_cause_options": [{"id": r.id, "text": r.text} for r in sorted(
            spec.root_causes, key=lambda r: hashlib.sha256(f"{sess.id}:{r.id}".encode()).hexdigest())]
        if st.status == "monitoring" or closed else None,
        "rca": {"root_cause_choice": rca.root_cause_choice, **rca.content} if rca else None,
        "outcome": sess.outcome, "outcome_score": float(sess.outcome_score) if sess.outcome_score is not None else None,
        "success": sess.success,
        "debrief": E.debrief(spec) if closed else None,
    }
    return out


async def perform_action(db: AsyncSession, learner: Learner, sid: uuid.UUID, action_id: str,
                         client_action_id: uuid.UUID) -> dict:
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    dup = await db.scalar(select(IncidentAction).where(IncidentAction.session_id == sess.id,
                                                       IncidentAction.client_action_id == client_action_id))
    if dup is not None:
        out = {"accepted": dup.accepted, "reason": dup.reason, **dup.result, "duplicate": True}
        await db.commit()
        return out
    if action_id not in E.action_index(spec):
        raise NotFound("Unknown action for this scenario")
    before = state_of(sess)
    res = E.perform(spec, before, action_id)
    result = {"outcome": res.outcome, "transitions": [list(t) for t in res.transitions], "revealed": res.revealed}
    await _audit(db, sess, before, res.state, kind="action", accepted=res.accepted, action_id=action_id,
                 reason=res.reason, result=result, client_action_id=client_action_id, snapshot=res.accepted)
    if res.accepted:
        _set_state(sess, res.state)
    await db.commit()
    return {"accepted": res.accepted, "reason": res.reason, **result, "duplicate": False}


# ---------------------------------------------------------------- evidence queries


def filter_logs(spec: ScenarioSpec, st: E.SimState, *, service: str | None = None, level: str | None = None,
                request_id: str | None = None, search: str | None = None, since: int | None = None,
                until: int | None = None) -> list[dict]:
    levels = ["debug", "info", "warning", "error", "critical"]
    out = []
    for r in E.visible_logs(spec, st):
        if service and r["service"] != service:
            continue
        if level and levels.index(r["level"]) < levels.index(level):
            continue
        if request_id and str(r["fields"].get("request_id", "")) != request_id:
            continue
        if search and search.lower() not in (r["message"] + " " + " ".join(map(str, r["fields"].values()))).lower():
            continue
        if since is not None and r["minute"] < since:
            continue
        if until is not None and r["minute"] > until:
            continue
        out.append(r)
    return out


def metrics_view(spec: ScenarioSpec, st: E.SimState, keys: list[str] | None, window: int) -> list[dict]:
    known = E.metric_keys(spec)
    keys = [k for k in (keys or known) if k in known]
    return [{"key": k, "points": E.series(spec, st, k, window)} for k in keys]


def evidence_lines(spec: ScenarioSpec, st: E.SimState) -> dict[str, str]:
    lines: dict[str, str] = {}
    for r in E.visible_logs(spec, st):
        fields = " ".join(f"{k}={v}" for k, v in r["fields"].items())
        lines[r["id"]] = f"log {r['ts']} {r['service']} {r['level'].upper()} {r['message']} {fields}".strip()
    for t in E.visible_traces(spec, st):
        lines[t["id"]] = f"trace request {t['request_id']} '{t['title']}' {t['duration_ms']:.0f} ms{' ERROR' if t['error'] else ''}"
    for d in E.visible_deployments(spec, st):
        lines[d["id"]] = f"deployment {d['ts']} {d['service']} {d['version']} by {d['author']}: {d['summary']}"
    for a in E.visible_artifacts(spec, st):
        lines[a["id"]] = f"diagnostic '{a['title']}'"
    return lines


def evidence_full(spec: ScenarioSpec, st: E.SimState, eid: str) -> str | None:
    for a in E.visible_artifacts(spec, st):
        if a["id"] == eid:
            return f"{a['title']}\n{a['content'].strip()}"
    for t in E.visible_traces(spec, st):
        if t["id"] == eid:
            spans = "\n".join(f"  {s['service']} {s['name']} start={s['start_ms']}ms dur={s['duration_ms']}ms {s['status']} {s['note']}".rstrip()
                              for s in t["spans"])
            return f"trace {t['request_id']} {t['title']}\n{spans}"
    return evidence_lines(spec, st).get(eid)


async def run_command(db: AsyncSession, learner: Learner, sid: uuid.UUID, command: str, client_action_id: uuid.UUID) -> dict:
    """Read-only simulated console. Never touches a real system."""
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    dup = await db.scalar(select(IncidentAction).where(IncidentAction.session_id == sess.id,
                                                       IncidentAction.client_action_id == client_action_id))
    if dup is not None:
        await db.commit()
        return {**dup.result, "accepted": dup.accepted, "duplicate": True}
    before = state_of(sess)
    try:
        name, opts = E.parse_command(command)
    except E.CommandError as exc:
        await _audit(db, sess, before, before, kind="command", accepted=False, params={"command": command[:300]},
                     reason=str(exc), client_action_id=client_action_id, result={"output": str(exc)})
        await db.commit()
        return {"accepted": False, "output": str(exc), "kind": "error"}
    st, performed = before, None
    mapped = next((a for a in spec.actions if a.command == name), None)
    if mapped is not None and not before.done(mapped.id) and before.status not in E.CLOSED:
        res = E.perform(spec, before, mapped.id)
        if res.accepted:
            st, performed = res.state, mapped.id
    output, kind = _command_output(spec, st, name, opts), name
    await _audit(db, sess, before, st, kind="command", accepted=True, action_id=performed,
                 params={"command": command[:300]}, client_action_id=client_action_id,
                 result={"output": output[:20000], "performed": performed}, snapshot=performed is not None)
    if performed:
        _set_state(sess, st)
    await db.commit()
    return {"accepted": True, "output": output, "kind": kind, "performed": performed}


def _command_output(spec: ScenarioSpec, st: E.SimState, name: str, opts: dict[str, str]) -> str:
    if name == "logs":
        last = int(opts["--last"]) if opts.get("--last", "").isdigit() else None
        rows = filter_logs(spec, st, service=opts.get("--service"), level=opts.get("--level"),
                           request_id=opts.get("--request-id"), search=opts.get("--search"),
                           since=(st.minute - last) if last else None)
        if not rows:
            return "No matching log records you have access to."
        return "\n".join(f"{r['ts']} {r['service']:<8} {r['level'].upper():<8} {r['message']}"
                         + (" " + " ".join(f"{k}={v}" for k, v in r["fields"].items()) if r["fields"] else "")
                         for r in rows[-200:])
    if name == "metrics":
        keys = [k for k in E.metric_keys(spec)
                if (not opts.get("--service") or k.startswith(opts["--service"] + "."))
                and (not opts.get("--metric") or k.endswith("." + opts["--metric"]))]
        if not keys:
            return "No metric matches. Services: " + ", ".join(s.id for s in spec.services)
        window = min(120, int(opts["--last"])) if opts.get("--last", "").isdigit() else 15
        lines = []
        for k in keys:
            pts = [v for _, v in E.series(spec, st, k, window) if v is not None]
            if pts:
                unit = METRICS[k.split(".")[1]]["unit"]
                lines.append(f"{k:<24} now={pts[-1]:<9} min={min(pts):<9} max={max(pts):<9} ({unit}, last {window} min)")
        return "\n".join(lines)
    if name == "traces":
        traces = E.visible_traces(spec, st)
        if opts.get("--request-id"):
            traces = [t for t in traces if t["request_id"] == opts["--request-id"]]
        if opts.get("--id"):
            traces = [t for t in traces if t["id"] == opts["--id"]]
        if opts.get("--errors"):
            traces = [t for t in traces if t["error"]]
        if not traces:
            return "No matching traces you have access to."
        return "\n\n".join(evidence_full(spec, st, t["id"]) or "" for t in traces)
    if name == "deployments":
        deps = [d for d in E.visible_deployments(spec, st) if not opts.get("--service") or d["service"] == opts["--service"]]
        return "\n".join(f"{d['ts']} {d['service']:<8} {d['version']:<10} {d['status']:<10} {d['author']}: {d['summary']}"
                         for d in deps) or "No deployments recorded."
    if name == "service-status":
        h = E.health(spec, st.condition)
        return "\n".join(f"{s.id:<8} {h[s.id]:<9} {s.name}" for s in spec.services)
    # database-status
    arts = [a for a in E.visible_artifacts(spec, st) if a["kind"] == "database_status"]
    if not arts:
        return "No database diagnostics available in this scenario."
    return "\n\n".join(f"{a['title']}\n{a['content'].strip()}" for a in arts)


# ---------------------------------------------------------------- pins, hypotheses, notes


async def pin(db: AsyncSession, learner: Learner, sid: uuid.UUID, evidence_id: str, note: str, pinned: bool) -> dict[str, str]:
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    st = state_of(sess)
    if st.status in E.CLOSED:
        raise Conflict("This incident is closed.")
    existing = await db.get(IncidentEvidence, (sess.id, evidence_id))
    if pinned:
        if evidence_id not in E.visible_evidence_ids(spec, st):
            raise NotFound("Evidence not found")
        if existing is None:
            if len(await pinned_of(db, sess.id)) >= MAX_PINS:
                raise Unprocessable(f"At most {MAX_PINS} pinned items")
            db.add(IncidentEvidence(session_id=sess.id, evidence_id=evidence_id, note=clean_block(note, 1000)))
        else:
            existing.note = clean_block(note, 1000)
    elif existing is not None:
        await db.delete(existing)
    await _audit(db, sess, st, st, kind="pin" if pinned else "unpin", accepted=True, action_id=evidence_id)
    sess.updated_at = _now()
    await db.commit()
    return await pinned_of(db, sess.id)


async def save_hypothesis(db: AsyncSession, learner: Learner, sid: uuid.UUID, number: int | None, statement: str,
                          status: str, evidence_ids: list[str]) -> IncidentHypothesis:
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    st = state_of(sess)
    if st.status in E.CLOSED:
        raise Conflict("This incident is closed.")
    statement = clean_block(statement, 2000)
    if not statement:
        raise Unprocessable("Describe the hypothesis")
    visible = E.visible_evidence_ids(spec, st)
    if unknown := [e for e in evidence_ids if e not in visible]:
        raise Unprocessable(f"Unknown evidence: {', '.join(unknown[:3])}")
    if number is None:
        hyps = await hypotheses_of(db, sess.id)
        if len(hyps) >= MAX_HYPOTHESES:
            raise Unprocessable(f"At most {MAX_HYPOTHESES} hypotheses")
        h = IncidentHypothesis(session_id=sess.id, number=len(hyps) + 1, statement=statement, status=status,
                               evidence_ids=evidence_ids)
        db.add(h)
    else:
        h = await db.scalar(select(IncidentHypothesis).where(IncidentHypothesis.session_id == sess.id,
                                                             IncidentHypothesis.number == number))
        if h is None:
            raise NotFound("Hypothesis not found")
        h.statement, h.status, h.evidence_ids, h.updated_at = statement, status, evidence_ids, _now()
    await db.flush()
    await _audit(db, sess, st, st, kind="hypothesis", accepted=True, params={"number": h.number, "status": status},
                 result={"statement": statement[:500]})
    sess.updated_at = _now()
    await db.commit()
    await db.refresh(h)
    return h


async def save_notes(db: AsyncSession, learner: Learner, sid: uuid.UUID, notes: str) -> None:
    sess, _, _ = await load_session(db, learner, sid, lock=True)
    sess.notes = clean_block(notes, 20000)
    sess.updated_at = _now()
    await db.commit()


# ---------------------------------------------------------------- AI


async def check_rate(db: AsyncSession, settings: Settings, learner: Learner) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 8))"), {"k": str(learner.id)})
    since = _now() - timedelta(hours=1)
    sessions = select(IncidentSession.id).where(IncidentSession.learner_id == learner.id)
    msgs = await db.scalar(select(func.count()).select_from(IncidentMessage).where(
        IncidentMessage.session_id.in_(sessions), IncidentMessage.role == "learner", IncidentMessage.created_at >= since))
    evals = await db.scalar(select(func.count()).select_from(IncidentEvaluation).where(
        IncidentEvaluation.session_id.in_(sessions), IncidentEvaluation.created_at >= since))
    if msgs + evals >= settings.ops_llm_calls_per_hour:
        raise RateLimited("AI commander limit reached for this hour. Keep investigating and try again later.")


async def _context(db: AsyncSession, sess: IncidentSession, spec: ScenarioSpec, version: IncidentScenarioVersion,
                   mode: str, extra_texts: list[str] | None = None) -> ai.OpsContext:
    st = state_of(sess)
    view = state_view(spec, st)
    pins = await pinned_of(db, sess.id)
    audit = (await db.scalars(select(IncidentAction).where(IncidentAction.session_id == sess.id)
                              .order_by(IncidentAction.seq.desc()).limit(40))).all()
    labels = {a.id: a.label for a in E.action_index(spec).values()}
    lines = []
    for a in reversed(audit):
        if a.kind == "action":
            lines.append(f"[minute {a.minute_before}] {labels.get(a.action_id, a.action_id)}: "
                         + (a.result.get("outcome", "") if a.accepted else f"REJECTED ({a.reason})"))
        elif a.kind == "command":
            lines.append(f"[minute {a.minute_before}] console: {a.params.get('command', '')}")
        elif a.kind in ("pin", "hypothesis"):
            lines.append(f"[minute {a.minute_before}] {a.kind} {a.action_id or a.params.get('number', '')}")
    msgs = (await db.scalars(select(IncidentMessage).where(IncidentMessage.session_id == sess.id)
                             .order_by(IncidentMessage.seq.desc()).limit(16))).all()
    return ai.OpsContext(
        spec=version.content, status=st.status,
        condition={"label": view["condition"]["label"], "summary": view["condition"]["summary"], "health": view["health"]},
        minute=st.minute, metrics_now=view["metrics_now"], evidence=evidence_lines(spec, st),
        pinned={k: (evidence_full(spec, st, k) or "") + (f"\nLearner note: {v}" if v else "") for k, v in pins.items()},
        audit=lines, hypotheses=[f"H{h.number} [{h.status}] {h.statement}" for h in await hypotheses_of(db, sess.id)],
        notes=sess.notes, transcript=[(m.role, m.content) for m in reversed(msgs)], mode=mode,
        reveal_allowed=st.status in E.CLOSED, learner_texts=extra_texts or [],
        seen=[*(evidence_full(spec, st, e) or "" for e in E.visible_evidence_ids(spec, st)),
              *(f"{a['label']} {a['description']}" for a in actions_view(spec, st)),
              *(f"{x.name} {x.description}" for x in spec.services), spec.customer_impact, spec.business_context],
    )


async def _append_message(db: AsyncSession, sid: uuid.UUID, role: str, kind: str, mode: str, content: str, **extra) -> IncidentMessage:
    seq = (await db.scalar(select(func.max(IncidentMessage.seq)).where(IncidentMessage.session_id == sid)) or 0) + 1
    m = IncidentMessage(session_id=sid, seq=seq, role=role, kind=kind, mode=mode, content=content[:20000], **extra)
    db.add(m)
    await db.flush()
    await db.refresh(m)
    return m


async def messages_of(db: AsyncSession, sid: uuid.UUID) -> list[IncidentMessage]:
    return list((await db.scalars(select(IncidentMessage).where(IncidentMessage.session_id == sid)
                                  .order_by(IncidentMessage.seq))).all())


async def send_message(db: AsyncSession, settings: Settings, llm, learner: Learner, sid: uuid.UUID, content: str,
                       client_message_id: uuid.UUID, mode: str) -> list[IncidentMessage]:
    body = clean_block(content, 6000)
    if not body:
        raise Unprocessable("Message is empty")
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    existing = await db.scalar(select(IncidentMessage).where(IncidentMessage.session_id == sess.id,
                                                             IncidentMessage.client_message_id == client_message_id))
    if existing is not None:
        seq = existing.seq
        await db.commit()
        return [m for m in await messages_of(db, sid) if m.seq >= seq][:2]
    await check_rate(db, settings, learner)
    sess.mode = mode
    mine = await _append_message(db, sess.id, "learner", "message", mode, body, client_message_id=client_message_id)
    await db.commit()
    ctx = await _context(db, sess, spec, version, mode)
    await db.commit()
    out = await ai.commander_turn(llm, ctx, settings.llm_max_repair_attempts)
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    if out.ok:
        d = out.data
        warn = {"caution": "\n\nCaution: that change carries risk.", "danger": "\n\nStop: that change could widen the impact."}.get(d["risk"], "")
        reply = await _append_message(db, sess.id, "commander", "question", mode, f"{d['reply']}{warn}\n\n{d['question']}",
                                      cited_evidence=d["cited_evidence"], provider=out.provider, model=out.model,
                                      prompt_tokens=out.prompt_tokens, completion_tokens=out.completion_tokens)
    else:
        reply = await _append_message(db, sess.id, "system", "notice", mode,
                                      f"The AI incident commander is unavailable ({out.error_code}). Your message is saved; send another to retry.",
                                      provider=out.provider or None, model=out.model or None)
    await db.commit()
    return [mine, reply]


# ---------------------------------------------------------------- resolution


class RcaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause_choice: str = Field(max_length=64)
    summary: str = Field(min_length=10, max_length=4000)
    customer_impact: str = Field(min_length=5, max_length=4000)
    evidence: str = Field(min_length=5, max_length=4000)
    root_cause: str = Field(min_length=10, max_length=4000)
    contributing_factors: str = Field(default="", max_length=4000)
    mitigation: str = Field(min_length=5, max_length=4000)
    recovery_validation: str = Field(min_length=5, max_length=4000)
    prevention: str = Field(min_length=5, max_length=4000)


async def resolve(db: AsyncSession, settings: Settings, llm, learner: Learner, sid: uuid.UUID, rca: RcaIn,
                  client_action_id: uuid.UUID) -> IncidentSession:
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    dup = await db.scalar(select(IncidentAction).where(IncidentAction.session_id == sess.id,
                                                       IncidentAction.client_action_id == client_action_id))
    if dup is not None:
        await db.commit()
        return sess
    if rca.root_cause_choice not in {r.id for r in spec.root_causes}:
        raise Unprocessable("Choose one of the listed root causes")
    before = state_of(sess)
    res = E.resolve(spec, before)
    if not res.accepted:
        await _audit(db, sess, before, before, kind="resolve", accepted=False, reason=res.reason,
                     client_action_id=client_action_id)
        await db.commit()
        raise Conflict(res.reason)
    content = {k: clean_block(getattr(rca, k), 4000) for k in RCA_FIELDS}
    db.add(IncidentRca(session_id=sess.id, root_cause_choice=rca.root_cause_choice, content=content))
    pins = set(await pinned_of(db, sess.id))
    result = E.outcome(spec, res.state, rca.root_cause_choice, pins)
    _set_state(sess, res.state)
    sess.outcome, sess.outcome_score, sess.success = result, Decimal(str(result["score"])), result["success"]
    sess.ended_at = _now()
    await _audit(db, sess, before, res.state, kind="resolve", accepted=True, client_action_id=client_action_id,
                 result={"outcome": res.outcome, "score": result["score"]}, snapshot=True)
    ev = IncidentEvaluation(session_id=sess.id, kind="rca", status="pending", rubric_version=RUBRIC_VERSION,
                            evaluation_version=ai.EVALUATION_VERSION, scenario_version_id=version.id,
                            provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"))
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    await _run_rca_review(db, settings, llm, learner, sid, ev.id)
    return sess


async def _run_rca_review(db: AsyncSession, settings: Settings, llm, learner: Learner, sid: uuid.UUID, ev_id: uuid.UUID) -> None:
    sess, version, spec = await load_session(db, learner, sid)
    rca = await db.get(IncidentRca, sess.id)
    ctx = await _context(db, sess, spec, version, "postmortem", extra_texts=list(rca.content.values()))
    outcome = dict(sess.outcome)
    await db.commit()
    try:
        await check_rate(db, settings, learner)
        await db.commit()
        out = await ai.evaluate_rca(llm, ctx, {"root_cause_choice": rca.root_cause_choice, **rca.content}, outcome,
                                    settings.llm_max_repair_attempts)
    except RateLimited:
        await db.rollback()
        out = ai.Outcome(False, "rate_limited")
    ev = await db.get(IncidentEvaluation, ev_id, with_for_update=True)
    _apply_eval(ev, out)
    await db.commit()


def _apply_eval(ev: IncidentEvaluation, out) -> None:
    ev.provider, ev.model = out.provider or ev.provider, out.model or ev.model
    ev.llm_attempts, ev.prompt_tokens, ev.completion_tokens = out.attempts, out.prompt_tokens, out.completion_tokens
    ev.completed_at = _now()
    if out.ok:
        d = out.data
        ev.status, ev.result, ev.confidence = "evaluated", d["result"], d["confidence"]
        ev.injection_suspected = d["injection_suspected"]
        if ev.kind == "rca":
            ev.total_score, ev.model_total_score = d["total_score"], d["model_total_score"]
            ev.mastery_eligible = d["mastery_eligible"]
    else:
        ev.status, ev.error_code = "ungraded", out.error_code or "provider_error"


async def retry_rca_review(db: AsyncSession, settings: Settings, llm, learner: Learner, sid: uuid.UUID) -> None:
    sess, version, _ = await load_session(db, learner, sid, lock=True)
    if sess.outcome is None:
        raise Conflict("Resolve the incident first")
    last = await db.scalar(select(IncidentEvaluation).where(IncidentEvaluation.session_id == sess.id,
                                                            IncidentEvaluation.kind == "rca")
                           .order_by(IncidentEvaluation.created_at.desc()).limit(1))
    if last is not None and last.status == "evaluated":
        raise Conflict("This analysis has already been reviewed")
    if last is not None and last.status == "pending" and _now() - last.created_at < PENDING_STALE_AFTER:
        raise Conflict("A review is already running")
    if last is not None and last.status == "pending":
        last.status, last.error_code, last.completed_at = "ungraded", "abandoned", _now()
    ev = IncidentEvaluation(session_id=sess.id, kind="rca", status="pending", rubric_version=RUBRIC_VERSION,
                            evaluation_version=ai.EVALUATION_VERSION, scenario_version_id=version.id,
                            provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"))
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    await _run_rca_review(db, settings, llm, learner, sid, ev.id)


async def abandon(db: AsyncSession, learner: Learner, sid: uuid.UUID) -> IncidentSession:
    sess, _, _ = await load_session(db, learner, sid, lock=True)
    before = state_of(sess)
    if before.status in E.CLOSED:
        raise Conflict("This incident is already closed")
    after = E.abandon(before)
    await _audit(db, sess, before, after, kind="abandon", accepted=True, snapshot=True,
                 result={"outcome": "Attempt ended. The debrief is now available; no mastery evidence is recorded."})
    _set_state(sess, after)
    sess.ended_at = _now()
    await db.commit()
    return sess


async def reset(db: AsyncSession, learner: Learner, sid: uuid.UUID) -> IncidentSession:
    """Ends this attempt (kept in history) and starts a fresh one."""
    sess, version, _ = await load_session(db, learner, sid, lock=True)
    if state_of(sess).status not in E.CLOSED:
        await abandon(db, learner, sid)
    sc = await db.get(IncidentScenario, sess.scenario_id)
    new, _ = await start_session(db, learner, sc.slug, sess.mode, fresh=True)
    return new


async def evaluations_of(db: AsyncSession, sid: uuid.UUID) -> list[IncidentEvaluation]:
    return list((await db.scalars(select(IncidentEvaluation).where(IncidentEvaluation.session_id == sid)
                                  .order_by(IncidentEvaluation.created_at.desc()))).all())


# ---------------------------------------------------------------- postmortem


def default_postmortem(spec: ScenarioSpec, audit: list[IncidentAction], rca: IncidentRca | None) -> dict:
    labels = {a.id: a.label for a in E.action_index(spec).values()}
    lines = []
    for a in audit:
        if a.kind == "action" and a.accepted:
            lines.append(f"- {E.timestamp(spec, a.minute_before)[11:16]} UTC: {labels.get(a.action_id, a.action_id)}"
                         + (f" ({a.result.get('outcome')})" if a.result.get("outcome") else ""))
        elif a.kind == "resolve" and a.accepted:
            lines.append(f"- {E.timestamp(spec, a.minute_after)[11:16]} UTC: Incident resolved; recovery verified.")
    c = rca.content if rca else {}
    return {
        "timeline": "\n".join(lines), "impact": c.get("customer_impact", ""), "detection": "",
        "root_cause": c.get("root_cause", ""), "contributing_factors": c.get("contributing_factors", ""),
        "mitigation": c.get("mitigation", ""), "recovery_verification": c.get("recovery_validation", ""),
        "went_well": "", "could_improve": "", "follow_ups": c.get("prevention", ""),
    }


async def get_postmortem(db: AsyncSession, learner: Learner, sid: uuid.UUID) -> Postmortem:
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    pm = await db.scalar(select(Postmortem).where(Postmortem.session_id == sess.id))
    if pm is not None:
        await db.commit()
        return pm
    st = state_of(sess)
    if st.status not in ("resolved", "postmortem"):
        raise Conflict("Resolve the incident before writing the postmortem")
    audit = (await db.scalars(select(IncidentAction).where(IncidentAction.session_id == sess.id)
                              .order_by(IncidentAction.seq))).all()
    content = default_postmortem(spec, list(audit), await db.get(IncidentRca, sess.id))
    pm = Postmortem(session_id=sess.id, revision=1, content=content)
    db.add(pm)
    await db.flush()
    db.add(PostmortemRevision(postmortem_id=pm.id, revision=1, content=content))
    if st.status == "resolved":
        after = replace(st, status="postmortem")
        await _audit(db, sess, st, after, kind="postmortem", accepted=True, snapshot=True,
                     result={"outcome": "Postmortem started."})
        _set_state(sess, after)
    await db.commit()
    await db.refresh(pm)
    return pm


class PostmortemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    content: dict[str, str]


async def save_postmortem(db: AsyncSession, learner: Learner, sid: uuid.UUID, body: PostmortemIn) -> Postmortem:
    await load_session(db, learner, sid)
    pm = await db.scalar(select(Postmortem).where(Postmortem.session_id == sid).with_for_update())
    if pm is None:
        raise NotFound("Postmortem not started")
    if body.base_revision != pm.revision:
        raise Conflict(f"This postmortem was changed elsewhere (revision {pm.revision}). Reload to continue.")
    if unknown := set(body.content) - set(POSTMORTEM_SECTIONS):
        raise Unprocessable(f"Unknown sections: {', '.join(sorted(unknown))}")
    content = {k: clean_block(body.content.get(k, pm.content.get(k, "")), 8000) for k in POSTMORTEM_SECTIONS}
    pm.revision += 1
    pm.content, pm.updated_at = content, _now()
    db.add(PostmortemRevision(postmortem_id=pm.id, revision=pm.revision, content=content))
    await db.commit()
    return pm


async def postmortem_revisions(db: AsyncSession, learner: Learner, sid: uuid.UUID) -> list[PostmortemRevision]:
    pm = await get_postmortem(db, learner, sid)
    return list((await db.scalars(select(PostmortemRevision).where(PostmortemRevision.postmortem_id == pm.id)
                                  .order_by(PostmortemRevision.revision.desc()))).all())


def postmortem_markdown(spec: ScenarioSpec, sess: IncidentSession, pm: Postmortem) -> str:
    head = (f"# Postmortem: {spec.title}\n\n_Blameless postmortem. FORGE OPS simulated incident, "
            f"attempt {sess.id}, revision {pm.revision}._\n\n")
    return head + "\n\n".join(f"## {title}\n\n{pm.content.get(k, '').strip() or '_Not written yet._'}"
                              for k, title in POSTMORTEM_SECTIONS.items()) + "\n"


async def review_postmortem(db: AsyncSession, settings: Settings, llm, learner: Learner, sid: uuid.UUID) -> IncidentEvaluation:
    pm = await get_postmortem(db, learner, sid)
    sess, version, spec = await load_session(db, learner, sid, lock=True)
    pending = await db.scalar(select(IncidentEvaluation).where(IncidentEvaluation.session_id == sid,
                                                               IncidentEvaluation.kind == "postmortem",
                                                               IncidentEvaluation.status == "pending"))
    if pending is not None and _now() - pending.created_at < PENDING_STALE_AFTER:
        raise Conflict("A review is already running")
    await check_rate(db, settings, learner)
    ev = IncidentEvaluation(session_id=sid, kind="postmortem", status="pending", rubric_version=RUBRIC_VERSION,
                            evaluation_version=ai.EVALUATION_VERSION, scenario_version_id=version.id,
                            postmortem_revision=pm.revision, provider=getattr(llm, "name", "?"), model=getattr(llm, "model", "?"))
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    ctx = await _context(db, sess, spec, version, "postmortem", extra_texts=list(pm.content.values()))
    content = dict(pm.content)
    await db.commit()
    out = await ai.review_postmortem(llm, ctx, content, settings.llm_max_repair_attempts)
    ev = await db.get(IncidentEvaluation, ev.id, with_for_update=True)
    _apply_eval(ev, out)
    if out.ok:
        qs = "\n".join(f"- {q}" for q in out.data["result"]["follow_up_questions"])
        await _append_message(db, sid, "commander", "review", "postmortem",
                              f"Postmortem review (revision {pm.revision}): {out.data['result']['summary']}\n\n{qs}",
                              provider=out.provider, model=out.model)
    await db.commit()
    await db.refresh(ev)
    return ev


# ---------------------------------------------------------------- replay & dashboard


async def replay(db: AsyncSession, learner: Learner, sid: uuid.UUID, seq: int | None) -> dict:
    sess, version, spec = await load_session(db, learner, sid)
    snaps = (await db.scalars(select(IncidentSnapshot).where(IncidentSnapshot.session_id == sid)
                              .order_by(IncidentSnapshot.seq))).all()
    audit = (await db.scalars(select(IncidentAction).where(IncidentAction.session_id == sid)
                              .order_by(IncidentAction.seq))).all()
    labels = {a.id: a.label for a in E.action_index(spec).values()}
    def label_of(a: IncidentAction) -> str | None:
        if a.kind in ("pin", "unpin"):
            return f"{'Pinned' if a.kind == 'pin' else 'Unpinned'} evidence {a.action_id}"
        if a.kind == "hypothesis":
            return f"Hypothesis H{a.params.get('number')} ({a.params.get('status')})"
        if a.kind in ("start", "resolve", "abandon", "postmortem"):
            return {"start": "Incident opened", "resolve": "Resolved with root-cause analysis",
                    "abandon": "Attempt ended", "postmortem": "Postmortem started"}[a.kind]
        return labels.get(a.action_id or "", a.action_id)

    steps = [{"seq": a.seq, "kind": a.kind, "action_id": a.action_id, "label": label_of(a),
              "accepted": a.accepted, "reason": a.reason, "result": a.result, "params": a.params,
              "status_before": a.status_before, "status_after": a.status_after,
              "condition_before": a.condition_before, "condition_after": a.condition_after,
              "minute_before": a.minute_before, "minute_after": a.minute_after, "created_at": a.created_at,
              "has_snapshot": any(s.seq == a.seq for s in snaps)} for a in audit]
    chosen = None
    if seq is not None:
        snap = next((s for s in snaps if s.seq == seq), None)
        if snap is None:
            raise NotFound("No snapshot at that step")
        chosen = E.SimState.from_json(snap.state)
    st = chosen or state_of(sess)
    closed = state_of(sess).status in E.CLOSED
    if not closed:  # audit entries carry internal condition names
        for step in steps:
            step["condition_before"] = step["condition_after"] = None
    return {"steps": steps, "seq": seq, "state": state_view(spec, st, reveal=closed),
            "metrics": metrics_view(spec, st, None, 60)}


def recurring_mistakes(sessions: list[IncidentSession]) -> list[dict]:
    counts: dict[str, int] = {}
    for s in sessions:
        for tag in (s.outcome or {}).get("mistakes", []):
            counts[tag] = counts.get(tag, 0) + 1
    return [{"tag": t, "count": n, **MISTAKES[t]} for t, n in sorted(counts.items(), key=lambda x: -x[1]) if t in MISTAKES]


def recommend(scenarios: list[tuple[IncidentScenario, IncidentScenarioVersion]], sessions: list[IncidentSession],
              mistakes: list[dict]) -> dict | None:
    """Retry a failed scenario first; else the next unresolved scenario whose level is unlocked
    (beginner, or a success one level below), preferring skills tied to recurring mistakes."""
    best: dict[int, float] = {}
    for s in sessions:
        if s.outcome_score is not None:
            best[s.scenario_id] = max(best.get(s.scenario_id, 0.0), float(s.outcome_score))
    passed_levels = {sc.level for sc, _ in scenarios if best.get(sc.id, 0) >= 0.7}
    for sc, v in scenarios:
        if sc.id in best and best[sc.id] < 0.5:
            return {"slug": sc.slug, "title": v.title, "level": sc.level, "reason": "retry",
                    "detail": f"Your best verified outcome here is {best[sc.id] * 100:.0f}%. Try a different investigation path."}
    weak_skills = {m["skill"] for m in mistakes if m["count"] >= 1}
    pick, key = None, None
    for sc, v in scenarios:
        if sc.id in best:
            continue
        lvl = LEVEL_ORDER.index(sc.level)
        if lvl > 0 and LEVEL_ORDER[lvl - 1] not in passed_levels:
            continue
        overlap = len(set(v.content["skills"]) & weak_skills)
        k = (-overlap, lvl, sc.position)
        if key is None or k < key:
            pick, key = (sc, v, overlap), k
    if pick is None:
        return None
    sc, v, overlap = pick
    return {"slug": sc.slug, "title": v.title, "level": sc.level,
            "reason": "remediation" if overlap else ("start" if not best else "next"),
            "detail": "Practises the skills behind your recurring mistakes." if overlap
            else ("A good first incident." if not best else "The next incident you've unlocked.")}


COMPETENCY_MIN_SCENARIOS = 2


def competencies(rows: list[tuple[IncidentSession, IncidentScenario, IncidentScenarioVersion]]) -> dict[str, dict]:
    acc: dict[str, dict] = {}
    for s, sc, v in rows:
        if s.outcome_score is None:
            continue
        for comp in v.content["competencies"]:
            a = acc.setdefault(comp, {"scores": [], "scenarios": set()})
            a["scores"].append(float(s.outcome_score))
            a["scenarios"].add(sc.id)
    return {k: {"score": round(sum(a["scores"]) / len(a["scores"]), 3), "attempts": len(a["scores"]),
                "distinct_scenarios": len(a["scenarios"]),
                "status": "assessed" if len(a["scenarios"]) >= COMPETENCY_MIN_SCENARIOS else "insufficient_evidence"}
            for k, a in acc.items()}
