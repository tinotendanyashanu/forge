"""Curriculum definition, validation and loading.

The curriculum (``curriculum.json``) is the source of truth for skills, their
prerequisite graph, subskills, per-level objectives and competency criteria.
It is versioned; loading records the version and a checksum.
"""

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Difficulty
from app.db.models import CurriculumVersion, Skill, SkillLevel, SkillPrerequisite, Topic

CURRICULUM_PATH = Path(__file__).resolve().parent / "curriculum.json"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class CurriculumCycleError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LevelSpec(_Strict):
    objective: str = Field(min_length=10)
    competency: str = Field(min_length=10)


class SubskillSpec(_Strict):
    slug: str = Field(pattern=SLUG)
    title: str = Field(min_length=2)


class SkillSpec(_Strict):
    slug: str = Field(pattern=SLUG)
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=64)
    summary: str = Field(min_length=10)
    prerequisites: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(min_length=1)
    subskills: list[SubskillSpec] = Field(min_length=1)
    levels: dict[Difficulty, LevelSpec]

    @model_validator(mode="after")
    def _levels_complete(self) -> Self:
        if set(self.levels) != set(Difficulty):
            raise ValueError(f"{self.slug}: every difficulty level needs an objective and competency")
        if self.slug in self.prerequisites:
            raise ValueError(f"{self.slug}: a skill cannot be its own prerequisite")
        return self


class Curriculum(_Strict):
    version: str = Field(pattern=r"^\d{4}\.\d{1,2}\.\d+$")
    skills: list[SkillSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _graph_valid(self) -> Self:
        slugs = [s.slug for s in self.skills]
        if len(set(slugs)) != len(slugs):
            raise ValueError("Duplicate skill slug in curriculum")
        known = set(slugs)
        for s in self.skills:
            missing = set(s.prerequisites) - known
            if missing:
                raise ValueError(f"{s.slug}: unknown prerequisites {sorted(missing)}")
        topological_order({s.slug: s.prerequisites for s in self.skills})
        return self

    def by_slug(self) -> dict[str, SkillSpec]:
        return {s.slug: s for s in self.skills}


def topological_order(edges: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm. ``edges`` maps skill -> prerequisites.

    Returns prerequisites before dependants; ties keep input order. Raises
    ``CurriculumCycleError`` naming the skills involved in any cycle.
    """
    indegree = {node: len(set(prereqs)) for node, prereqs in edges.items()}
    dependants: dict[str, list[str]] = {node: [] for node in edges}
    for node, prereqs in edges.items():
        for p in set(prereqs):
            dependants.setdefault(p, []).append(node)
            indegree.setdefault(p, 0)
    order_index = {node: i for i, node in enumerate(edges)}
    queue = deque(sorted((n for n, d in indegree.items() if d == 0), key=lambda n: order_index.get(n, 0)))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in sorted(dependants.get(node, []), key=lambda n: order_index.get(n, 0)):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(indegree):
        stuck = sorted(n for n, d in indegree.items() if d > 0)
        raise CurriculumCycleError(f"Prerequisite cycle involving: {', '.join(stuck)}")
    return order


def ancestors(edges: dict[str, list[str]], node: str) -> set[str]:
    """All transitive prerequisites of ``node``."""
    seen: set[str] = set()
    stack = list(edges.get(node, []))
    while stack:
        p = stack.pop()
        if p not in seen:
            seen.add(p)
            stack.extend(edges.get(p, []))
    return seen


def load_curriculum(path: Path = CURRICULUM_PATH) -> tuple[Curriculum, str]:
    raw = path.read_bytes()
    return Curriculum.model_validate(json.loads(raw)), hashlib.sha256(raw).hexdigest()


async def sync_curriculum(db: AsyncSession, curriculum: Curriculum, checksum: str) -> CurriculumVersion:
    """Upserts skills, subskills (topics), levels and the prerequisite graph."""
    version = await db.scalar(select(CurriculumVersion).where(CurriculumVersion.version == curriculum.version))
    if version is None:
        version = CurriculumVersion(version=curriculum.version, checksum=checksum)
        db.add(version)
    elif version.checksum != checksum:
        raise ValueError(
            f"Curriculum {curriculum.version} changed without a version bump; update 'version'."
        )
    await db.execute(update(CurriculumVersion).values(is_current=False))
    await db.flush()
    version.is_current = True

    # Free positions before reassigning them (unique constraints).
    await db.execute(update(Skill).values(position=-Skill.id))
    await db.execute(update(Topic).values(position=-Topic.id))
    existing = {s.slug: s for s in (await db.scalars(select(Skill))).all()}
    skills: dict[str, Skill] = {}
    for pos, spec in enumerate(curriculum.skills):
        skill = existing.get(spec.slug)
        fields = dict(
            title=spec.title,
            summary=spec.summary,
            category=spec.category,
            learning_objectives=list(spec.learning_objectives),
            position=pos,
        )
        if skill is None:
            skill = Skill(slug=spec.slug, description=spec.summary, **fields)
            db.add(skill)
        else:
            for k, v in fields.items():
                setattr(skill, k, v)
        skills[spec.slug] = skill
    await db.flush()

    for spec in curriculum.skills:
        skill = skills[spec.slug]
        topics = {t.slug: t for t in (await db.scalars(select(Topic).where(Topic.skill_id == skill.id))).all()}
        for pos, sub in enumerate(spec.subskills):
            topic = topics.get(sub.slug)
            if topic is None:
                db.add(Topic(skill_id=skill.id, slug=sub.slug, title=sub.title, position=pos))
            else:
                topic.title, topic.position = sub.title, pos
        for difficulty, level in spec.levels.items():
            await db.execute(
                pg_insert(SkillLevel)
                .values(skill_id=skill.id, difficulty=difficulty, objective=level.objective, competency=level.competency)
                .on_conflict_do_update(
                    index_elements=[SkillLevel.skill_id, SkillLevel.difficulty],
                    set_={"objective": level.objective, "competency": level.competency},
                )
            )

    await db.execute(delete(SkillPrerequisite))
    await db.flush()
    for spec in curriculum.skills:
        for prereq in spec.prerequisites:
            db.add(
                SkillPrerequisite(
                    skill_id=skills[spec.slug].id,
                    prerequisite_id=skills[prereq].id,
                    curriculum_version_id=version.id,
                )
            )
    await db.flush()
    return version
