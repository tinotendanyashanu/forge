"""Engineering project library: ``app/workspace/projects/<slug>/``.

Layout of a project directory::

    project.toml        metadata, ticket, acceptance criteria, rubric, tests, exercises
    starter/...         the codebase the learner receives
    reference/...       files that differ in the reference solution (overlaid on starter)
    checks/public.py    trusted public check driver (python suite)
    checks/hidden.py    trusted hidden check driver (python suite), may import checks_public
    checks/public.mjs   trusted public check driver (node suite), optional
    checks/hidden.mjs   trusted hidden check driver (node suite), optional

Checks return raw observations; expected values stay in project.toml and are
compared by the worker, outside the sandbox. A content change creates a new
immutable version (see ``sync_projects``).
"""

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import Difficulty, TestVisibility
from app.workspace.paths import normalise

PROJECTS_DIR = Path(__file__).resolve().parent / "projects"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"

Level = Literal["beginner", "junior", "mid", "senior"]
LEVEL_DIFFICULTY: dict[str, Difficulty] = {
    "beginner": Difficulty.BEGINNER, "junior": Difficulty.INTERMEDIATE,
    "mid": Difficulty.INTERMEDIATE, "senior": Difficulty.ADVANCED,
}
TaskType = Literal[
    "bug_fix", "feature", "refactoring", "testing", "database_migration", "performance",
    "security", "api_integration", "architecture", "legacy_maintenance",
]
Suite = Literal["python", "node"]
COMPETENCIES = (
    "codebase_comprehension", "implementation", "debugging", "testing", "database", "api",
    "frontend", "refactoring", "maintainability", "security", "performance",
    "communication", "judgment",
)
Competency = Literal[
    "codebase_comprehension", "implementation", "debugging", "testing", "database", "api",
    "frontend", "refactoring", "maintainability", "security", "performance",
    "communication", "judgment",
]
ExerciseKind = Literal[
    "requirement_change", "clarify_requirements", "review_junior_code", "stakeholder_explanation",
    "implementation_plan", "estimate", "adr", "deployment_plan",
]
CHECK_FILES = {("python", "public"): "public.py", ("python", "hidden"): "hidden.py",
               ("node", "public"): "public.mjs", ("node", "hidden"): "hidden.mjs"}
MAX_FILES = 60
MAX_FILE_BYTES = 64 * 1024


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Ticket(_Strict):
    key: str = Field(pattern=r"^[A-Z]+-\d+(-\d+)?$")
    title: str = Field(min_length=5, max_length=200)
    type: str
    priority: str
    reporter: str
    body: str = Field(min_length=20)
    acceptance_criteria: list[str] = Field(min_length=2)


class ProjectTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=160)
    visibility: TestVisibility
    suite: Suite
    call: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    competency: Competency
    args: list[Any] = Field(default_factory=list)
    args_json: str | None = None
    expected: Any = None
    expected_json: str | None = None
    raises: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

    @model_validator(mode="after")
    def _one_outcome(self) -> Self:
        given = [k for k in ("expected", "expected_json", "raises") if k in self.model_fields_set]
        if len(given) != 1:
            raise ValueError(f"{self.name}: give exactly one of expected, expected_json, raises")
        if self.args_json is not None and "args" in self.model_fields_set:
            raise ValueError(f"{self.name}: give args or args_json, not both")
        return self

    def resolved_args(self) -> list:
        return json.loads(self.args_json) if self.args_json is not None else list(self.args)

    def outcome(self) -> dict:
        if self.raises:
            return {"raises": self.raises}
        if self.expected_json is not None:
            return {"value": json.loads(self.expected_json)}
        return {"value": self.expected}


class Exercise(_Strict):
    slug: str = Field(pattern=SLUG)
    kind: ExerciseKind
    title: str = Field(min_length=5)
    prompt: str = Field(min_length=40)
    rubric: list[str] = Field(min_length=3)


class Project(_Strict):
    slug: str = Field(pattern=SLUG, max_length=96)
    title: str = Field(min_length=5, max_length=160)
    level: Level
    task_type: TaskType
    skill: str = Field(pattern=SLUG)
    area: str = Field(pattern=SLUG)
    prerequisites: list[str] = Field(default_factory=list)
    stack: list[str] = Field(min_length=1)
    dimensions: list[str] = Field(min_length=1)  # career framework dimension keys
    competencies: list[Competency] = Field(min_length=1)
    estimated_minutes: int = Field(ge=10, le=600)
    time_limit_ms: int = Field(ge=500, le=10_000)
    memory_limit_mb: int = Field(ge=64, le=512)
    rubric_version: str = Field(pattern=r"^[a-z0-9][a-z0-9.\-]{2,40}$")
    summary: str = Field(min_length=20, max_length=400)
    description: str = Field(min_length=40)
    architecture: str = Field(min_length=40)
    setup: str = Field(min_length=20)
    misconceptions: list[str] = Field(min_length=1)
    hints: list[str] = Field(min_length=1, max_length=4)
    rubric: list[str] = Field(min_length=3)
    ticket: Ticket
    tests: list[ProjectTest] = Field(min_length=3)
    exercises: list[Exercise] = Field(default_factory=list)
    # Loaded from the directory, not project.toml:
    starter: dict[str, str] = Field(default_factory=dict)
    reference: dict[str, str] = Field(default_factory=dict)
    checks: dict[str, str] = Field(default_factory=dict)  # "<suite>:<visibility>" -> source

    @property
    def difficulty(self) -> Difficulty:
        return LEVEL_DIFFICULTY[self.level]

    @property
    def suites(self) -> list[str]:
        return sorted({t.suite for t in self.tests})

    def reference_tree(self) -> dict[str, str]:
        return {**self.starter, **self.reference}

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        names = [t.name for t in self.tests]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.slug}: duplicate test names")
        if {t.visibility for t in self.tests} != {TestVisibility.PUBLIC, TestVisibility.HIDDEN}:
            raise ValueError(f"{self.slug}: needs public and hidden tests")
        for t in self.tests:
            if f"{t.suite}:{t.visibility.value}" not in self.checks:
                raise ValueError(f"{self.slug}: test '{t.name}' has no {t.suite} {t.visibility.value} checks file")
        if not self.starter:
            raise ValueError(f"{self.slug}: empty starter")
        if not self.reference:
            raise ValueError(f"{self.slug}: no reference changes")
        if len(self.reference_tree()) > MAX_FILES:
            raise ValueError(f"{self.slug}: too many files")
        for tree in (self.starter, self.reference):
            for path, text in tree.items():
                if normalise(path) != path:
                    raise ValueError(f"{self.slug}: invalid path {path}")
                if len(text.encode()) > MAX_FILE_BYTES:
                    raise ValueError(f"{self.slug}: {path} is too large")
        if len({e.slug for e in self.exercises}) != len(self.exercises):
            raise ValueError(f"{self.slug}: duplicate exercise slugs")
        return self

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _read_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"Symlinks are not allowed in project content: {p}")
        if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store":
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return out


def load_project(directory: Path) -> Project:
    data = tomllib.loads((directory / "project.toml").read_text(encoding="utf-8"))
    checks = {}
    for (suite, vis), fname in CHECK_FILES.items():
        f = directory / "checks" / fname
        if f.is_file():
            checks[f"{suite}:{vis}"] = f.read_text(encoding="utf-8")
    return Project.model_validate({
        **data, "starter": _read_tree(directory / "starter"),
        "reference": _read_tree(directory / "reference"), "checks": checks,
    })


LEVEL_ORDER = {"beginner": 0, "junior": 1, "mid": 2, "senior": 3}


def load_projects(projects_dir: Path = PROJECTS_DIR) -> list[Project]:
    """All projects, ordered for the library: by level, then slug."""
    dirs = sorted(d for d in projects_dir.iterdir() if (d / "project.toml").is_file())
    projects = []
    for d in dirs:
        p = load_project(d)
        if p.slug != d.name:
            raise ValueError(f"Project directory {d.name} must match its slug {p.slug}")
        projects.append(p)
    slugs = [p.slug for p in projects]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate project slugs")
    return sorted(projects, key=lambda p: (LEVEL_ORDER[p.level], p.slug))
