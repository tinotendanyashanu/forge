"""Incident scenario specification (app/ops/scenarios/*.toml).

Scenarios are authored, trusted content, validated here at seed time. Every
number the simulator shows comes from a scenario's metric model; nothing is
invented at runtime. Hidden fields (root cause, teaching notes, action
quality) never leave the server before an attempt ends.
"""

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
ID = r"^[a-z0-9][a-z0-9_-]{0,63}$"

METRICS: dict[str, dict[str, str]] = {
    "throughput": {"label": "Throughput", "unit": "req/min"},
    "error_rate": {"label": "Error rate", "unit": "%"},
    "p50": {"label": "Latency p50", "unit": "ms"},
    "p95": {"label": "Latency p95", "unit": "ms"},
    "p99": {"label": "Latency p99", "unit": "ms"},
    "cpu": {"label": "CPU", "unit": "%"},
    "memory": {"label": "Memory", "unit": "MB"},
    "db_connections": {"label": "DB connections", "unit": "conns"},
    "queue_depth": {"label": "Queue depth", "unit": "jobs"},
    "worker_rate": {"label": "Processing rate", "unit": "jobs/min"},
    "signups": {"label": "Sign-ups", "unit": "per min"},
    "login_failures": {"label": "Login failures", "unit": "per min"},
}
LEVELS = ("beginner", "intermediate", "advanced", "senior")
PHASES = ("healthy", "incident", "worse", "recovering", "recovered")
COMPETENCIES = {
    "http_debugging", "database_operations", "performance_analysis", "distributed_systems", "observability",
    "reliability", "security_response", "deployment_engineering", "root_cause_analysis", "technical_communication",
}
COMMANDS = ("logs", "metrics", "traces", "deployments", "service-status", "database-status")


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricModel(_Spec):
    """One metric's deterministic model inside a condition.

    v: constant level; linear: [start, per_minute] since the condition began;
    sawtooth: [low, high] repeating every `period` minutes; ramp: [from, to]
    over `minutes`, then held. `jitter` is a deterministic +/- fraction.
    """
    v: float | None = None
    linear: tuple[float, float] | None = None
    sawtooth: tuple[float, float] | None = None
    period: int = Field(default=10, ge=2, le=240)
    ramp: tuple[float, float] | None = None
    minutes: int = Field(default=5, ge=1, le=240)
    min: float | None = None
    max: float | None = None
    jitter: float = Field(default=0.03, ge=0, le=0.5)

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        if sum(x is not None for x in (self.v, self.linear, self.sawtooth, self.ramp)) != 1:
            raise ValueError("metric model needs exactly one of v, linear, sawtooth, ramp")
        return self


class Service(_Spec):
    id: str = Field(pattern=ID)
    name: str
    kind: str  # icon hint, matches the design lab component types
    depends_on: list[str] = Field(default_factory=list)
    description: str = ""


class Condition(_Spec):
    label: str
    phase: Literal["healthy", "incident", "worse", "recovering", "recovered"]
    inherit: str | None = None
    health: dict[str, Literal["healthy", "degraded", "down"]] = Field(default_factory=dict)
    metrics: dict[str, float | MetricModel] = Field(default_factory=dict)  # "service.metric"
    auto_after: int | None = Field(default=None, ge=1, le=120)  # minutes until `auto_to`
    auto_to: str | None = None
    summary: str = ""  # internal description (shown only in the debrief and post-incident replay)
    # What monitoring would show a responder: symptoms only, never the mechanism.
    symptom: str = ""


class LogRecord(_Spec):
    id: str = Field(pattern=ID)
    t: float  # minutes; relative to incident start, or to entering `after`
    service: str
    level: Literal["debug", "info", "warning", "error", "critical"]
    message: str
    fields: dict[str, str | int | float | bool] = Field(default_factory=dict)
    reveal: str = "always"  # "always" or an action id
    after: str | None = None  # condition name


class Span(_Spec):
    id: str = Field(pattern=ID)
    parent: str | None = None
    service: str
    name: str
    start_ms: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    status: Literal["ok", "error"] = "ok"
    note: str = ""


class Trace(_Spec):
    id: str = Field(pattern=ID)
    t: float
    request_id: str
    title: str
    spans: list[Span] = Field(min_length=1)
    reveal: str = "always"
    after: str | None = None


class Deployment(_Spec):
    id: str = Field(pattern=ID)
    t: float
    service: str
    version: str
    author: str
    summary: str
    changes: list[str] = Field(default_factory=list)
    status: Literal["succeeded", "failed", "rolled_back"] = "succeeded"
    reveal: str = "always"


class Artifact(_Spec):
    """Diagnostic output such as pg_stat_activity, a config diff or a flag list."""
    id: str = Field(pattern=ID)
    kind: Literal["database_status", "service_status", "config", "feature_flags", "runbook", "dashboard", "other"]
    title: str
    content: str
    reveal: str
    after: str | None = None


class Action(_Spec):
    id: str = Field(pattern=ID)
    kind: Literal["investigate", "mitigate"]
    label: str
    description: str
    minutes: int = Field(default=2, ge=0, le=60)
    command: str | None = None  # an allowlisted console command that performs this action
    once: bool = True
    requires_actions: list[str] = Field(default_factory=list)
    # Hidden from the action list until any of these investigations is done:
    # targeted fixes have to be discovered, not picked from a menu.
    discovered_by: list[str] = Field(default_factory=list)
    requires_phase: list[str] = Field(default_factory=list)
    # mitigation effect: condition -> next condition; absent means no effect
    transitions: dict[str, str] = Field(default_factory=dict)
    outcome: dict[str, str] = Field(default_factory=dict)  # condition -> text; "default"
    deployment: dict[str, str] | None = None  # e.g. rollback adds a deployment record
    # Hidden until the attempt ends:
    quality: Literal["correct", "helpful", "neutral", "risky", "harmful"] = "neutral"
    mistake: str | None = None
    teach: str = ""


class RootCause(_Spec):
    id: str = Field(pattern=ID)
    text: str
    correct: bool = False
    explanation: str  # hidden until the attempt ends


class MisleadingSignal(_Spec):
    signal: str
    why: str


class ScenarioSpec(_Spec):
    slug: str = Field(pattern=SLUG)
    title: str
    summary: str
    business_context: str
    skills: list[str] = Field(min_length=1)  # curriculum slugs, primary first
    competencies: list[str] = Field(min_length=1)
    learning_outcomes: list[str] = Field(min_length=2)
    initial_symptoms: list[str] = Field(min_length=1)
    customer_impact: str
    start_time: str  # ISO timestamp of minute 0 (display only)
    history: list[tuple[float, str]] = Field(min_length=1)  # (minute, condition) before/at start
    initial_condition: str
    verify_minutes: int = Field(default=5, ge=1, le=60)
    target_minutes: int = Field(default=25, ge=5, le=240)
    services: list[Service] = Field(min_length=2)
    conditions: dict[str, Condition]
    logs: list[LogRecord] = Field(min_length=5)
    traces: list[Trace] = Field(default_factory=list)
    deployments: list[Deployment] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    actions: list[Action] = Field(min_length=4)
    # Hidden:
    root_causes: list[RootCause] = Field(min_length=3)
    key_evidence: list[str] = Field(min_length=2)
    contributing_factors: list[str] = Field(min_length=1)
    misleading_signals: list[MisleadingSignal] = Field(min_length=1)
    investigation_path: list[str] = Field(min_length=2)
    explanation: str
    prevention: list[str] = Field(min_length=1)
    rubric_focus: dict[str, str] = Field(min_length=3)
    # Phrases that give the root cause away; the AI commander may not use one
    # until the learner has seen it in evidence or written it themselves.
    spoiler_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        from app.ops.catalog import MISTAKES, RCA_CRITERIA

        services = {s.id for s in self.services}
        actions = {a.id for a in self.actions}
        evidence: set[str] = set()

        def need(cond: bool, msg: str) -> None:
            if not cond:
                raise ValueError(f"{self.slug}: {msg}")

        for s in self.services:
            need(set(s.depends_on) <= services, f"service {s.id} depends on unknown services")
        need("healthy" in self.conditions, "a 'healthy' condition is required")
        need(self.initial_condition in self.conditions, "unknown initial_condition")
        for name, c in self.conditions.items():
            need(c.inherit is None or c.inherit in self.conditions, f"condition {name} inherits unknown")
            need((c.auto_after is None) == (c.auto_to is None), f"condition {name}: auto_after needs auto_to")
            need(c.auto_to is None or c.auto_to in self.conditions, f"condition {name}: unknown auto_to")
            need(set(c.health) <= services, f"condition {name}: health for unknown service")
            for key in c.metrics:
                svc, _, metric = key.partition(".")
                need(svc in services and metric in METRICS, f"condition {name}: bad metric key {key}")
        for _, cond in self.history:
            need(cond in self.conditions, f"history uses unknown condition {cond}")
        need(any(self.conditions[n].phase == "recovered" for n in self.conditions), "needs a recovered condition")

        def reveal_ok(r: str) -> bool:
            return r == "always" or r in actions

        for group in (self.logs, self.traces, self.deployments, self.artifacts):
            for item in group:
                need(item.id not in evidence, f"duplicate evidence id {item.id}")
                evidence.add(item.id)
                need(reveal_ok(item.reveal), f"{item.id} revealed by unknown action {item.reveal}")
                if getattr(item, "after", None):
                    need(item.after in self.conditions, f"{item.id}: unknown condition {item.after}")
        for log in self.logs:
            need(log.service in services, f"log {log.id}: unknown service")
        for tr in self.traces:
            ids = {s.id for s in tr.spans}
            for sp in tr.spans:
                need(sp.service in services, f"trace {tr.id}: unknown service {sp.service}")
                need(sp.parent is None or sp.parent in ids, f"trace {tr.id}: unknown parent {sp.parent}")
        for a in self.actions:
            need(set(a.requires_actions) <= actions, f"action {a.id}: unknown required action")
            need(set(a.discovered_by) <= actions, f"action {a.id}: unknown discovering action")
            need(set(a.requires_phase) <= set(PHASES), f"action {a.id}: unknown phase")
            for f, t in a.transitions.items():
                need(f in self.conditions and t in self.conditions, f"action {a.id}: unknown transition {f}->{t}")
            need(a.command is None or a.command in COMMANDS, f"action {a.id}: command not allowlisted")
            need(a.mistake is None or a.mistake in MISTAKES, f"action {a.id}: unknown mistake {a.mistake}")
            need(a.kind == "investigate" or a.transitions or a.quality in ("neutral", "risky", "harmful"),
                 f"action {a.id}: a helpful mitigation needs transitions")
        need(sum(r.correct for r in self.root_causes) == 1, "exactly one correct root cause")
        need(set(self.key_evidence) <= evidence, "key_evidence references unknown evidence")
        need(set(self.rubric_focus) <= set(RCA_CRITERIA), "rubric_focus uses unknown criteria")
        need(set(self.competencies) <= COMPETENCIES, "unknown competencies")
        need(any(a.quality == "correct" for a in self.actions), "needs at least one correct mitigation")
        return self

    def content_hash(self) -> str:
        from app.ops.catalog import RUBRIC_VERSION
        payload = {"spec": self.model_dump(mode="json"), "rubric": RUBRIC_VERSION}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class LevelFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["beginner", "intermediate", "advanced", "senior"]
    scenarios: list[ScenarioSpec] = Field(min_length=1)


def load_scenarios(directory: Path = SCENARIO_DIR) -> list[tuple[str, ScenarioSpec]]:
    out: list[tuple[str, ScenarioSpec]] = []
    for path in sorted(directory.glob("*.toml")):
        f = LevelFile.model_validate(tomllib.loads(path.read_text()))
        out += [(f.level, s) for s in f.scenarios]
    slugs = [s.slug for _, s in out]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate incident scenario slugs")
    # Authoring rules for new content only (stored versions must always load):
    for _, spec in out:
        for name, c in spec.conditions.items():
            if c.phase not in ("healthy", "recovered") and not c.symptom:
                raise ValueError(f"{spec.slug}: condition {name} needs a learner-facing symptom")
    return out
