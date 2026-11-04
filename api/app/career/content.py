"""FORGE Career content: competency framework, assessment templates, judgment
scenarios and take-home projects (app/career/content/*.toml).

Everything is validated here; cross-references must resolve. Content is
versioned by hash, and historical attempts and reports keep the exact version
they were created with.
"""

import hashlib
import json
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTENT_DIR = Path(__file__).resolve().parent / "content"
LEVELS = ("foundation", "junior", "mid", "senior")
Level = Literal["foundation", "junior", "mid", "senior"]
Difficulty = Literal["beginner", "intermediate", "advanced"]
EVIDENCE_KINDS = ("coding_objective", "simulation", "knowledge_objective", "rubric_ai", "architecture_ai",
                  "communication_ai", "self_report")
SECTION_KINDS = ("interview", "coding", "design", "incident", "judgment", "take_home")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- framework


class Rules(_M):
    score_threshold: float = Field(gt=0, le=1)
    weak_threshold: float = Field(gt=0, le=1)
    default_freshness_days: int = Field(ge=30, le=3650)
    foundation_threshold: float
    foundation_min_weight: float
    min_weight: dict[str, float]
    min_sessions: dict[str, int]
    verified_required: list[str]
    reasoning_required: list[str]
    insufficient_coverage: float = Field(gt=0, le=1)
    reliability: dict[str, float]


class Dimension(_M):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    title: str
    why: str
    knowledge: str
    implementation: str
    debugging: str
    architecture: str
    critical_gap: str
    levels: dict[Level, str]
    freshness_days: int | None = None
    # Evidence mapping (where this competency is demonstrated in FORGE):
    skills: list[str] = Field(default_factory=list)
    coding_areas: list[str] = Field(default_factory=list)
    design_competencies: list[str] = Field(default_factory=list)
    incident_competencies: list[str] = Field(default_factory=list)
    judgment_tags: list[str] = Field(default_factory=list)
    evidence_dimensions: list[str] = Field(default_factory=list)  # mastery evidence dimensions, e.g. debugging
    all_design_evidence: bool = False
    all_incident_evidence: bool = False
    failure_evidence: bool = False
    incident_review_evidence: bool = False
    critical_mistakes: list[str] = Field(default_factory=list)

    @property
    def verifiable(self) -> bool:
        """Has a deterministic evidence source in FORGE (coding, simulation or objective questions)."""
        return bool(self.coding_areas or self.skills or self.incident_competencies or self.all_incident_evidence)


class TrackLevel(_M):
    gates: dict[str, Level]
    required: dict[str, Level] = Field(default_factory=dict)


class Track(_M):
    key: Literal["fullstack", "backend", "frontend"]
    title: str
    description: str
    levels: dict[Level, TrackLevel]


class Framework(_M):
    version: str
    title: str
    rules: Rules
    dimensions: list[Dimension] = Field(min_length=18)
    tracks: list[Track] = Field(min_length=3)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        keys = [d.key for d in self.dimensions]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate dimension keys")
        for t in self.tracks:
            if set(t.levels) != set(LEVELS):
                raise ValueError(f"track {t.key} must define every level")
            for lvl, tl in t.levels.items():
                unknown = (set(tl.gates) | set(tl.required)) - set(keys)
                if unknown:
                    raise ValueError(f"track {t.key}/{lvl}: unknown dimensions {sorted(unknown)}")
        if set(self.rules.reliability) != set(EVIDENCE_KINDS):
            raise ValueError("reliability must cover every evidence kind")
        return self

    def dim(self, key: str) -> Dimension:
        return next(d for d in self.dimensions if d.key == key)

    def track(self, key: str) -> Track:
        return next(t for t in self.tracks if t.key == key)

    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json"))


# ---------------------------------------------------------------- judgment & projects


class JudgmentScenario(_M):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    tags: list[Literal["judgment", "communication", "code_review"]] = Field(min_length=1)
    level: Level
    context: str
    prompt: str
    criteria: dict[str, str] = Field(min_length=3)
    considerations: list[str] = Field(min_length=2)  # hidden until finalized
    red_flags: list[str] = Field(default_factory=list)  # hidden until finalized

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("slug", "title", "tags", "level", "context", "prompt")} | {
            "criteria": list(self.criteria.values())}


class Project(_M):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    level: Level
    dimensions: list[str] = Field(min_length=1)
    hours: int = Field(ge=1, le=40)
    summary: str
    requirements: list[str] = Field(min_length=2)
    acceptance: list[str] = Field(min_length=1)
    architecture: str
    linked_challenges: list[str] = Field(default_factory=list)
    rubric: dict[str, str] = Field(min_length=3)
    starter: str


# ---------------------------------------------------------------- templates


class Section(_M):
    key: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    kind: Literal["interview", "coding", "design", "incident", "judgment", "take_home"]
    title: str
    objectives: list[str] = Field(min_length=1)
    dimensions: list[str] = Field(min_length=1)
    weight: float = Field(gt=0, le=5)
    minutes: int = Field(ge=5, le=480)
    critical: bool = False
    params: dict = Field(default_factory=dict)


class Template(_M):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    track: Literal["fullstack", "backend", "frontend"]
    level: Level
    purpose: Literal["formal", "practice", "diagnostic"]
    time_limit_minutes: int = Field(ge=0, le=720)  # 0 = untimed
    description: str
    objectives: list[str] = Field(min_length=1)
    passing_criteria: str
    critical_failures: list[str] = Field(default_factory=list)
    evidence_requirements: str
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys(self) -> Self:
        keys = [s.key for s in self.sections]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{self.slug}: duplicate section keys")
        return self

    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json"))


class Content(_M):
    framework: Framework
    templates: list[Template]
    judgment: list[JudgmentScenario]
    projects: list[Project]

    @model_validator(mode="after")
    def _refs(self) -> Self:
        dims = {d.key for d in self.framework.dimensions}
        scen = {s.slug for s in self.judgment}
        projects = {p.slug for p in self.projects}
        for t in self.templates:
            for s in t.sections:
                if unknown := set(s.dimensions) - dims:
                    raise ValueError(f"{t.slug}/{s.key}: unknown dimensions {sorted(unknown)}")
                if s.kind == "judgment" and not set(s.params.get("include", [])) <= scen:
                    raise ValueError(f"{t.slug}/{s.key}: unknown judgment scenarios")
                if s.kind == "take_home" and s.params.get("project") not in projects:
                    raise ValueError(f"{t.slug}/{s.key}: unknown project")
        for p in self.projects:
            if unknown := set(p.dimensions) - dims:
                raise ValueError(f"project {p.slug}: unknown dimensions {sorted(unknown)}")
        if len({t.slug for t in self.templates}) != len(self.templates):
            raise ValueError("duplicate template slugs")
        return self

    def template(self, slug: str) -> Template:
        return next(t for t in self.templates if t.slug == slug)

    def scenario(self, slug: str) -> JudgmentScenario:
        return next(s for s in self.judgment if s.slug == slug)

    def project(self, slug: str) -> Project:
        return next(p for p in self.projects if p.slug == slug)


def _read(name: str) -> dict:
    return tomllib.loads((CONTENT_DIR / name).read_text())


@lru_cache(maxsize=1)
def load_content() -> Content:
    return Content(
        framework=Framework.model_validate(_read("framework.toml")),
        templates=[Template.model_validate(t) for t in _read("templates.toml")["templates"]],
        judgment=[JudgmentScenario.model_validate(s) for s in _read("judgment.toml")["scenarios"]],
        projects=[Project.model_validate(p) for p in _read("projects.toml")["projects"]],
    )
