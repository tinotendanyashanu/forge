"""Deterministic incident simulation engine (pure functions, no I/O).

State is small and fully serialisable. Every metric value is computed from the
scenario's metric model, the condition timeline and a hash-based jitter, so
the same state always renders the same numbers. Nothing here invents data.
"""

import hashlib
import re
import shlex
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from app.ops.catalog import OUTCOME_WEIGHTS
from app.ops.scenario import COMMANDS, METRICS, Action, MetricModel, ScenarioSpec

CLOSED = ("resolved", "postmortem", "abandoned")
STATUSES = ("created", "investigating", "mitigating", "monitoring", "resolved", "postmortem", "abandoned")
OBSERVE = Action(
    id="observe", kind="investigate", label="Wait and observe (5 min)", minutes=5, once=False,
    description="Let simulated time pass and watch how the system responds.",
)
INT_METRICS = {"throughput", "p50", "p95", "p99", "memory", "db_connections", "queue_depth", "worker_rate",
               "signups", "login_failures"}


@dataclass(frozen=True)
class SimState:
    status: str
    condition: str
    minute: int
    history: tuple[tuple[int, str], ...]  # (minute entered, condition), ascending
    performed: tuple[tuple[str, int], ...] = ()  # (action id, minute performed)

    def to_json(self) -> dict:
        return {"status": self.status, "condition": self.condition, "minute": self.minute,
                "history": [list(h) for h in self.history], "performed": [list(p) for p in self.performed]}

    @classmethod
    def from_json(cls, d: dict) -> "SimState":
        return cls(status=d["status"], condition=d["condition"], minute=d["minute"],
                   history=tuple((int(m), c) for m, c in d["history"]),
                   performed=tuple((a, int(m)) for a, m in d["performed"]))

    def done(self, action_id: str) -> bool:
        return any(a == action_id for a, _ in self.performed)


@dataclass
class ActionResult:
    accepted: bool
    state: "SimState"
    reason: str | None = None
    outcome: str = ""
    transitions: list[tuple[int, str, str]] = field(default_factory=list)  # (minute, from, to)
    revealed: list[str] = field(default_factory=list)


def initial_state(spec: ScenarioSpec) -> SimState:
    history = tuple(sorted((int(m), c) for m, c in spec.history))
    if not history or history[-1][1] != spec.initial_condition:
        history = (*history, (0, spec.initial_condition))
    return SimState(status="created", condition=spec.initial_condition, minute=0, history=history)


# ---------------------------------------------------------------- conditions


def _chain(spec: ScenarioSpec, name: str) -> list:
    out, seen = [], set()
    while name and name not in seen:
        seen.add(name)
        c = spec.conditions[name]
        out.append(c)
        name = c.inherit
    if "healthy" not in seen:
        out.append(spec.conditions["healthy"])
    return out


def health(spec: ScenarioSpec, condition: str) -> dict[str, str]:
    merged: dict[str, str] = {s.id: "healthy" for s in spec.services}
    for c in reversed(_chain(spec, condition)):
        merged.update(c.health)
    return merged


def _metric_model(spec: ScenarioSpec, condition: str, key: str):
    for c in _chain(spec, condition):
        if key in c.metrics:
            return c.metrics[key]
    return None


def condition_at(state: SimState, minute: float) -> tuple[str, int]:
    current, entered = state.history[0][1], state.history[0][0]
    for m, c in state.history:
        if m <= minute:
            current, entered = c, m
        else:
            break
    return current, entered


PHASE_TEXT = {
    "healthy": ("Healthy", "All services healthy."),
    "incident": ("Incident ongoing", "Customer-facing impact continues."),
    "worse": ("Impact increasing", "The incident is getting worse."),
    "recovering": ("Improving", "Metrics are improving."),
    "recovered": ("Metrics at baseline", "Latency, errors and throughput are back to normal."),
}


def public_condition(spec: ScenarioSpec, condition: str, *, reveal: bool = False) -> dict:
    """What a responder can see. Internal labels describe the mechanism, so they
    are only shown once the attempt has ended."""
    c = spec.conditions[condition]
    if reveal:
        return {"label": c.label, "summary": c.summary}
    default_label, default_summary = PHASE_TEXT[c.phase]
    return {"label": default_label if c.phase not in ("healthy", "recovered") else c.label or default_label,
            "summary": c.symptom or default_summary}


def phase(spec: ScenarioSpec, condition: str) -> str:
    return spec.conditions[condition].phase


def _noise(slug: str, key: str, minute: int) -> float:
    h = hashlib.blake2b(f"{slug}|{key}|{minute}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64 * 2 - 1  # [-1, 1)


def metric_value(spec: ScenarioSpec, state: SimState, key: str, minute: int) -> float | None:
    condition, entered = condition_at(state, minute)
    model = _metric_model(spec, condition, key)
    if model is None:
        return None
    m = model if isinstance(model, MetricModel) else MetricModel(v=float(model))
    dt = max(0, minute - entered)
    if m.v is not None:
        base = m.v
    elif m.linear is not None:
        base = m.linear[0] + m.linear[1] * dt
    elif m.sawtooth is not None:
        lo, hi = m.sawtooth
        base = lo + (hi - lo) * ((dt % m.period) / m.period)
    else:
        a, b = m.ramp
        base = a + (b - a) * min(1.0, dt / m.minutes)
    if m.min is not None:
        base = max(m.min, base)
    if m.max is not None:
        base = min(m.max, base)
    value = max(0.0, base * (1 + m.jitter * _noise(spec.slug, key, minute)))
    metric = key.partition(".")[2]
    if metric in ("error_rate", "cpu"):
        value = min(100.0, value)
    return float(round(value)) if metric in INT_METRICS else round(value, 1)


def series(spec: ScenarioSpec, state: SimState, key: str, window: int = 60) -> list[tuple[int, float | None]]:
    end = state.minute
    start = end - window
    return [(m, metric_value(spec, state, key, m)) for m in range(start, end + 1)]


def metric_keys(spec: ScenarioSpec) -> list[str]:
    keys: set[str] = set()
    for c in spec.conditions.values():
        keys |= set(c.metrics)
    order = list(METRICS)
    return sorted(keys, key=lambda k: ([s.id for s in spec.services].index(k.split(".")[0]), order.index(k.split(".")[1])))


def timestamp(spec: ScenarioSpec, minute: float) -> str:
    base = datetime.fromisoformat(spec.start_time.replace("Z", "+00:00"))
    return (base + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------- evidence visibility


def _first_entry(state: SimState, condition: str) -> int | None:
    return next((m for m, c in state.history if c == condition), None)


def _when(state: SimState, t: float, after: str | None) -> float | None:
    """Minute an item appears, or None if its condition never happened."""
    if after is None:
        return t
    entry = _first_entry(state, after)
    return None if entry is None else entry + t


def _revealed(state: SimState, reveal: str) -> bool:
    return reveal == "always" or state.done(reveal)


def visible_logs(spec: ScenarioSpec, state: SimState) -> list[dict]:
    out = []
    for r in spec.logs:
        at = _when(state, r.t, r.after)
        if at is not None and at <= state.minute and _revealed(state, r.reveal):
            out.append({"id": r.id, "ts": timestamp(spec, at), "minute": at, "service": r.service,
                        "level": r.level, "message": r.message, "fields": r.fields})
    return sorted(out, key=lambda x: (x["minute"], x["id"]))


def visible_traces(spec: ScenarioSpec, state: SimState) -> list[dict]:
    out = []
    for tr in spec.traces:
        at = _when(state, tr.t, tr.after)
        if at is not None and at <= state.minute and _revealed(state, tr.reveal):
            total = max(s.start_ms + s.duration_ms for s in tr.spans)
            out.append({"id": tr.id, "ts": timestamp(spec, at), "minute": at, "request_id": tr.request_id,
                        "title": tr.title, "duration_ms": total,
                        "error": any(s.status == "error" for s in tr.spans),
                        "spans": [s.model_dump() for s in tr.spans]})
    return sorted(out, key=lambda x: (x["minute"], x["id"]))


def visible_deployments(spec: ScenarioSpec, state: SimState) -> list[dict]:
    out = [
        {"id": d.id, "ts": timestamp(spec, d.t), "minute": d.t, "service": d.service, "version": d.version,
         "author": d.author, "summary": d.summary, "changes": d.changes, "status": d.status, "by_learner": False}
        for d in spec.deployments if d.t <= state.minute and _revealed(state, d.reveal)
    ]
    actions = {a.id: a for a in spec.actions}
    for aid, m in state.performed:
        a = actions.get(aid)
        if a and a.deployment:
            out.append({"id": f"act-{aid}", "ts": timestamp(spec, m), "minute": m,
                        "service": a.deployment.get("service", ""), "version": a.deployment.get("version", ""),
                        "author": "you", "summary": a.deployment.get("summary", a.label), "changes": [],
                        "status": "succeeded", "by_learner": True})
    return sorted(out, key=lambda x: (x["minute"], x["id"]))


def visible_artifacts(spec: ScenarioSpec, state: SimState) -> list[dict]:
    out = []
    for a in spec.artifacts:
        if not _revealed(state, a.reveal):
            continue
        if a.after is not None and _first_entry(state, a.after) is None:
            continue
        out.append({"id": a.id, "kind": a.kind, "title": a.title, "content": a.content})
    return out


def visible_evidence_ids(spec: ScenarioSpec, state: SimState) -> set[str]:
    return ({x["id"] for x in visible_logs(spec, state)} | {x["id"] for x in visible_traces(spec, state)}
            | {x["id"] for x in visible_deployments(spec, state)} | {x["id"] for x in visible_artifacts(spec, state)})


def _reveals_of(spec: ScenarioSpec, action_id: str) -> list[str]:
    ids = [x.id for group in (spec.logs, spec.traces, spec.deployments, spec.artifacts)
           for x in group if x.reveal == action_id]
    return ids


# ---------------------------------------------------------------- transitions


def _advance(spec: ScenarioSpec, state: SimState, minutes: int, transitions: list) -> SimState:
    target = state.minute + minutes
    history = list(state.history)
    condition = state.condition
    while True:
        c = spec.conditions[condition]
        entered = history[-1][0]
        if c.auto_to is None or entered + c.auto_after > target:
            break
        at = entered + c.auto_after
        transitions.append((at, condition, c.auto_to))
        condition = c.auto_to
        history.append((at, condition))
    return replace(state, minute=target, condition=condition, history=tuple(history))


def _status_after(spec: ScenarioSpec, state: SimState) -> str:
    if state.status in CLOSED:
        return state.status
    p = phase(spec, state.condition)
    if p in ("recovering", "recovered") and state.status in ("investigating", "mitigating"):
        return "monitoring"
    if p in ("incident", "worse") and state.status == "monitoring":
        return "mitigating"
    return state.status


def action_index(spec: ScenarioSpec) -> dict[str, Action]:
    return {"observe": OBSERVE, **{a.id: a for a in spec.actions}}


def discovered(state: SimState, action: Action) -> bool:
    return not action.discovered_by or any(state.done(a) for a in action.discovered_by)


def check(spec: ScenarioSpec, state: SimState, action: Action) -> str | None:
    """Reason the action is not allowed now, or None."""
    if state.status in CLOSED:
        return "This incident is closed."
    if not discovered(state, action):
        return "Unknown action."
    if action.once and state.done(action.id):
        return "You already did this. Its results are in the evidence panels."
    missing = [a for a in action.requires_actions if not state.done(a)]
    if missing:
        labels = {a.id: a.label for a in spec.actions}
        return "Not possible yet: first " + "; ".join(labels.get(m, m) for m in missing) + "."
    if action.requires_phase and phase(spec, state.condition) not in action.requires_phase:
        return "This action doesn't apply in the system's current state."
    return None


def perform(spec: ScenarioSpec, state: SimState, action_id: str) -> ActionResult:
    action = action_index(spec).get(action_id)
    if action is None:
        return ActionResult(False, state, "Unknown action.")
    if (reason := check(spec, state, action)) is not None:
        return ActionResult(False, state, reason)
    transitions: list[tuple[int, str, str]] = []
    st = replace(state, performed=(*state.performed, (action.id, state.minute)))
    if st.status == "created":
        st = replace(st, status="investigating")
    if action.kind == "mitigate" and st.status == "investigating":
        st = replace(st, status="mitigating")
    before = st.condition
    nxt = action.transitions.get(before)
    if nxt and nxt != before:
        transitions.append((st.minute, before, nxt))
        st = replace(st, condition=nxt, history=(*st.history, (st.minute, nxt)))
    outcome = action.outcome.get(before) or action.outcome.get("default") or (
        "No measurable change in the system." if action.kind == "mitigate" else "")
    st = _advance(spec, st, action.minutes, transitions)
    st = replace(st, status=_status_after(spec, st))
    if action.id == "observe":
        outcome = f"{action.minutes} minutes pass. {public_condition(spec, st.condition)['summary']}"
    return ActionResult(True, st, None, outcome, transitions, _reveals_of(spec, action.id))


def recovery_check(spec: ScenarioSpec, state: SimState) -> tuple[bool, str]:
    """Deterministic verification that the simulated service has recovered."""
    p = phase(spec, state.condition)
    if p != "recovered":
        return False, "Service health has not recovered yet. Keep mitigating and observing."
    entered = state.history[-1][0]
    held = state.minute - entered
    if held < spec.verify_minutes:
        return False, f"Recovered for {held} min; observe for {spec.verify_minutes - held} more to verify it holds."
    return True, f"Metrics have stayed healthy for {held} minutes."


def resolve(spec: ScenarioSpec, state: SimState) -> ActionResult:
    if state.status != "monitoring":
        return ActionResult(False, state, "Only an incident in monitoring, with recovery verified, can be resolved.")
    ok, msg = recovery_check(spec, state)
    if not ok:
        return ActionResult(False, state, msg)
    return ActionResult(True, replace(state, status="resolved"), None, msg)


def abandon(state: SimState) -> SimState:
    return state if state.status in CLOSED else replace(state, status="abandoned")


# ---------------------------------------------------------------- verified outcome


def outcome(spec: ScenarioSpec, state: SimState, root_cause_id: str | None, pinned: set[str]) -> dict:
    """Deterministic, verified result of an attempt. Graded only on scenario rules."""
    actions = {a.id: a for a in spec.actions}
    used = [actions[a] for a, _ in state.performed if a in actions]
    harmful = [a.id for a in used if a.quality == "harmful"]
    risky = [a.id for a in used if a.quality == "risky"]
    correct_rc = next(r.id for r in spec.root_causes if r.correct)
    rc_ok = root_cause_id == correct_rc
    key = set(spec.key_evidence)
    found = sorted(key & pinned)
    minutes = _lasting_recovery_start(spec, state)
    efficiency = 0.0 if minutes is None else (
        1.0 if minutes <= spec.target_minutes else max(0.0, 1 - (minutes - spec.target_minutes) / spec.target_minutes))
    safety = max(0.0, 1 - 0.5 * len(harmful) - 0.15 * len(risky))
    evidence = len(found) / len(key)
    review, decisions, flags = decision_review(spec, state)
    w = OUTCOME_WEIGHTS
    score = round(w["root_cause"] * rc_ok + w["evidence"] * evidence + w["safety"] * safety
                  + w["decisions"] * decisions["score"] + w["efficiency"] * efficiency, 3)
    mistakes = sorted({a.mistake for a in used if a.mistake and a.quality in ("risky", "harmful")}
                      | ({"wrong-root-cause"} if not rc_ok else set()))
    recovered = phase(spec, state.condition) == "recovered"
    return {
        "score": score, "recovered": recovered, "root_cause_correct": rc_ok,
        "selected_root_cause": root_cause_id, "correct_root_cause": correct_rc,
        "key_evidence_found": found, "key_evidence_missed": sorted(key - pinned),
        "harmful_actions": harmful, "risky_actions": risky,
        "minutes_to_recovery": minutes, "target_minutes": spec.target_minutes,
        "investigation_actions": sum(1 for a in used if a.kind == "investigate"),
        "mitigation_actions": sum(1 for a in used if a.kind == "mitigate"),
        "mistakes": mistakes,
        "components": {"root_cause": float(rc_ok), "evidence": round(evidence, 3), "safety": round(safety, 3),
                       "decisions": decisions["score"], "efficiency": round(efficiency, 3)},
        "decisions": decisions, "decision_flags": flags, "decision_review": review,
        "success": rc_ok and recovered and not harmful and score >= 0.7,
    }


USEFUL = ("correct", "helpful")


def _lasting_recovery_start(spec: ScenarioSpec, state: SimState) -> int | None:
    """Start of the recovery that lasted: a temporary relief that regressed doesn't count."""
    start = None
    for m, c in state.history:
        p = phase(spec, c)
        if p in ("incident", "worse"):
            start = None
        elif p in ("recovering", "recovered") and start is None and m >= 0:
            start = m
    return start if phase(spec, state.condition) in ("recovering", "recovered") else None


def _last_at(state: SimState, minute: int) -> str | None:
    acts = [a for a, m in state.performed if m == minute]
    return acts[-1] if acts else None


def decision_review(spec: ScenarioSpec, state: SimState) -> tuple[list[dict], dict, list[str]]:
    """Grades each decision in order, from scenario rules only (deterministic).

    * informed: a mitigation counts as informed if a useful investigation came before it.
    * precision: correct/helpful mitigations score 1, neutral 0.5, risky/harmful 0
      (trial and error lowers it even when the incident is eventually fixed).
    * focus: useful investigations score 1, low-yield ones 0.5 (ruling things out is
      legitimate but costs time). Waiting to observe is not graded.
    """
    actions = {a.id: a for a in spec.actions}
    review: list[dict] = []
    useful_seen = False
    informed, precision, focus = [], [], []
    # A mitigation "worked" only if it started the recovery that lasted;
    # temporary relief that regressed (a restart before a leak returns) doesn't count.
    lasting = _lasting_recovery_start(spec, state)
    first_mitigation_blind = False
    for aid, minute in state.performed:
        a = actions.get(aid)
        if a is None:
            continue
        entry = {"minute": minute, "action_id": a.id, "label": a.label, "kind": a.kind, "quality": a.quality,
                 "teach": a.teach}
        if a.kind == "investigate":
            focus.append(1.0 if a.quality in USEFUL else 0.5)
            entry["assessment"] = "useful" if a.quality in USEFUL else "low-yield"
            useful_seen = useful_seen or a.quality in USEFUL
        else:
            entry["informed"] = useful_seen
            if not useful_seen and not informed:
                first_mitigation_blind = True
            informed.append(1.0 if useful_seen else 0.0)
            started_recovery = a.quality == "neutral" and minute == lasting and _last_at(state, minute) == a.id
            temporary = (a.quality == "neutral" and not started_recovery and _last_at(state, minute) == a.id
                         and any(m == minute and phase(spec, c) in ("recovering", "recovered") for m, c in state.history))
            p = 1.0 if a.quality in USEFUL or started_recovery else {"neutral": 0.5}.get(a.quality, 0.0)
            precision.append(p)
            entry["assessment"] = ("effective" if p == 1.0 else "temporary relief" if temporary else
                                   {"neutral": "no real effect", "risky": "risky", "harmful": "harmful"}[a.quality])
        review.append(entry)
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    parts = {"informed": round(mean(informed), 3), "precision": round(mean(precision), 3),
             "focus": round(mean(focus), 3) if focus else 0.0}
    score = round((parts["informed"] + parts["precision"] + parts["focus"]) / 3, 3) if informed else 0.0
    flags = []
    if first_mitigation_blind:
        flags.append("Changed the system before any useful investigation.")
    if sum(1 for p in precision if p < 1) >= 2:
        flags.append("Tried several mitigations that didn't address the cause (trial and error).")
    if not focus:
        flags.append("No investigation before resolving.")
    elif mean(focus) < 0.75:
        flags.append("Most investigation steps were low-yield.")
    return review, {"score": score, **parts}, flags


def debrief(spec: ScenarioSpec) -> dict:
    """Hidden teaching material, released only after the attempt ends."""
    return {
        "root_causes": [r.model_dump() for r in spec.root_causes],
        "contributing_factors": spec.contributing_factors,
        "misleading_signals": [m.model_dump() for m in spec.misleading_signals],
        "investigation_path": spec.investigation_path,
        "explanation": spec.explanation,
        "prevention": spec.prevention,
        "key_evidence": spec.key_evidence,
        "actions": [{"id": a.id, "label": a.label, "kind": a.kind, "quality": a.quality, "teach": a.teach,
                     "mistake": a.mistake, "discovered_by": a.discovered_by} for a in spec.actions],
    }


# ---------------------------------------------------------------- read-only console

_FLAG_VALUE = re.compile(r"^[A-Za-z0-9_.:/@-]{1,64}$")
_FLAGS = {
    "logs": {"--service", "--level", "--request-id", "--search", "--last"},
    "metrics": {"--service", "--metric", "--last"},
    "traces": {"--request-id", "--id", "--errors"},
    "deployments": {"--service"},
    "service-status": set(),
    "database-status": set(),
}
BOOL_FLAGS = {"--errors"}


class CommandError(ValueError):
    pass


def parse_command(text: str) -> tuple[str, dict[str, str]]:
    """Strict allowlist parser. These are simulation queries, not shell commands."""
    if len(text) > 300:
        raise CommandError("Command too long.")
    try:
        parts = shlex.split(text)
    except ValueError:
        raise CommandError("Couldn't parse the command (check your quotes).") from None
    if not parts:
        raise CommandError("Type a command, e.g. `logs --level error`. Try `help`.")
    name, rest = parts[0], parts[1:]
    if name not in COMMANDS:
        raise CommandError(f"Unknown command '{name[:30]}'. Allowed: {', '.join(COMMANDS)}.")
    opts: dict[str, str] = {}
    i = 0
    while i < len(rest):
        flag = rest[i]
        if flag not in _FLAGS[name]:
            raise CommandError(f"Unknown option '{flag[:30]}' for {name}.")
        if flag in BOOL_FLAGS:
            opts[flag] = "true"
            i += 1
            continue
        if i + 1 >= len(rest):
            raise CommandError(f"Option {flag} needs a value.")
        value = rest[i + 1]
        if flag == "--search":
            if len(value) > 80:
                raise CommandError("Search text is too long.")
        elif not _FLAG_VALUE.match(value):
            raise CommandError(f"Invalid value for {flag}.")
        opts[flag] = value
        i += 2
    return name, opts
