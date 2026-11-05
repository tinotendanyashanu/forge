"""Lesson content: ``app/seed/lessons/*.md`` files with TOML front matter.

A lesson file looks like::

    +++
    slug = "python-functions-and-scope"
    skill = "python"
    topic = "functions"            # one of the skill's curriculum subskills
    difficulty = "beginner"
    title = "..."
    summary = "..."
    estimated_minutes = 15
    objectives = ["..."]
    prerequisites = []             # lesson slugs to read first
    misconceptions = ["..."]
    checks = ["question-slug"]     # assessment questions that test the objectives
    status = "reviewed"            # draft | reviewed | verified
    version = 1
    provenance = "..."
    [[resources]]
    title = "..."
    url = "https://..."
    +++
    Markdown body with the required sections (see REQUIRED_SECTIONS).

Lessons are loaded by slug: changed lessons are updated in place, removed
lessons are deactivated, never deleted. Reading a lesson is engagement, not
mastery evidence.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.curriculum.graph import Curriculum
from app.db.enums import Difficulty
from app.db.models import Lesson, LessonQuestion, LessonResource, Question, Skill, Topic
from app.seed.schema import SLUG

LESSON_DIR = Path(__file__).resolve().parent / "lessons"
REQUIRED_SECTIONS = (
    "Why it matters",
    "Mental model",
    "How it works",
    "Worked example",
    "Common mistakes",
    "In production",
    "Trade-offs and limits",
    "Check your understanding",
    "Practice",
)
FRONT_MATTER = re.compile(r"\A\+\+\+\n(.*?)\n\+\+\+\n(.*)\Z", re.S)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LessonResourceSeed(_Strict):
    title: str = Field(min_length=3, max_length=200)
    url: str = Field(pattern=r"^https://\S+$", max_length=500)


class LessonSeed(_Strict):
    slug: str = Field(pattern=SLUG, max_length=96)
    skill: str = Field(pattern=SLUG)
    topic: str | None = Field(default=None, pattern=SLUG)
    difficulty: Difficulty
    title: str = Field(min_length=3, max_length=160)
    summary: str = Field(min_length=20)
    estimated_minutes: int = Field(ge=1, le=120)
    objectives: list[str] = Field(min_length=2)
    prerequisites: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(min_length=2)
    checks: list[str] = Field(min_length=1)
    status: str = Field(pattern=r"^(draft|reviewed|verified)$")
    version: int = Field(ge=1)
    provenance: str = Field(min_length=5)
    resources: list[LessonResourceSeed] = Field(min_length=1)
    body: str = Field(min_length=800)

    @model_validator(mode="after")
    def _sections(self) -> Self:
        headings = re.findall(r"^##\s+(.+?)\s*$", self.body, re.M)
        missing = [s for s in REQUIRED_SECTIONS if s not in headings]
        if missing:
            raise ValueError(f"{self.slug}: missing sections {missing}")
        return self


def parse_lesson(path: Path) -> LessonSeed:
    m = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: expected +++ TOML front matter +++ then Markdown")
    meta = tomllib.loads(m.group(1))
    return LessonSeed.model_validate({**meta, "body": m.group(2).strip()})


def load_lessons(
    curriculum: Curriculum, question_slugs: set[str], lesson_dir: Path = LESSON_DIR
) -> list[LessonSeed]:
    """Reads and validates every lesson against the curriculum and question bank."""
    lessons = [parse_lesson(p) for p in sorted(lesson_dir.glob("*.md"))] if lesson_dir.exists() else []
    slugs = [x.slug for x in lessons]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ValueError(f"Duplicate lesson slugs: {sorted(dupes)}")
    skills = {s.slug: s for s in curriculum.skills}
    for x in lessons:
        skill = skills.get(x.skill)
        if skill is None:
            raise ValueError(f"{x.slug}: unknown skill {x.skill}")
        if x.topic and x.topic not in {t.slug for t in skill.subskills}:
            raise ValueError(f"{x.slug}: topic {x.topic} is not a subskill of {x.skill}")
        unknown = set(x.prerequisites) - set(slugs)
        if unknown:
            raise ValueError(f"{x.slug}: unknown prerequisite lessons {sorted(unknown)}")
        if x.slug in x.prerequisites:
            raise ValueError(f"{x.slug}: lists itself as a prerequisite")
        missing = set(x.checks) - question_slugs
        if missing:
            raise ValueError(f"{x.slug}: unknown check questions {sorted(missing)}")
    _check_acyclic(lessons)
    return lessons


def _check_acyclic(lessons: list[LessonSeed]) -> None:
    graph = {x.slug: x.prerequisites for x in lessons}
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 1:
            raise ValueError(f"Lesson prerequisite cycle: {' -> '.join(path + [node])}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in graph[node]:
            visit(nxt, path + [node])
        state[node] = 2

    for slug in graph:
        visit(slug, [])


async def sync_lessons(db: AsyncSession, lessons: list[LessonSeed]) -> int:
    """Upserts lessons by slug and deactivates lessons no longer present. Commits."""
    skills = {s.slug: s.id for s in (await db.scalars(select(Skill))).all()}
    topics = {(t.skill_id, t.slug): t.id for t in (await db.scalars(select(Topic))).all()}
    question_ids = {
        q.slug: q.id
        for q in (await db.scalars(select(Question).where(Question.is_active))).all()
    }
    seen: set[str] = set()
    for position, x in enumerate(lessons):
        skill_id = skills[x.skill]
        fields = {
            "skill_id": skill_id,
            "topic_id": topics.get((skill_id, x.topic)) if x.topic else None,
            "difficulty": x.difficulty,
            "title": x.title,
            "summary": x.summary,
            "body": x.body,
            "objectives": list(x.objectives),
            "prerequisites": list(x.prerequisites),
            "misconceptions": list(x.misconceptions),
            "estimated_minutes": x.estimated_minutes,
            "position": position,
            "version": x.version,
            "status": x.status,
            "provenance": x.provenance,
            "is_active": True,
        }
        lesson = await db.scalar(select(Lesson).where(Lesson.slug == x.slug))
        if lesson is None:
            lesson = Lesson(slug=x.slug, **fields)
            db.add(lesson)
            await db.flush()
        else:
            for k, v in fields.items():
                setattr(lesson, k, v)
        await db.execute(delete(LessonResource).where(LessonResource.lesson_id == lesson.id))
        await db.execute(delete(LessonQuestion).where(LessonQuestion.lesson_id == lesson.id))
        db.add_all(
            LessonResource(lesson_id=lesson.id, position=i, title=r.title, url=r.url)
            for i, r in enumerate(x.resources)
        )
        db.add_all(
            LessonQuestion(lesson_id=lesson.id, question_id=question_ids[s], position=i)
            for i, s in enumerate(x.checks)
            if s in question_ids
        )
        seen.add(x.slug)
    await db.flush()
    stmt = update(Lesson).where(Lesson.is_active).values(is_active=False)
    if seen:
        stmt = stmt.where(Lesson.slug.not_in(seen))
    await db.execute(stmt)
    await db.commit()
    return len(seen)
