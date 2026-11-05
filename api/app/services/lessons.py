"""Lesson reads and suggestions. Nothing here writes mastery evidence."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import Difficulty
from app.db.models import Lesson, LessonQuestion, LessonRead, Skill
from app.schemas.content import SkillRef, TopicRef
from app.schemas.lessons import (
    LessonCheckOut,
    LessonDetail,
    LessonProgressOut,
    LessonRef,
    LessonResourceOut,
    LessonSuggestion,
    LessonSummary,
)
from app.services.errors import NotFound

LEVEL_ORDER = {Difficulty.BEGINNER: 0, Difficulty.INTERMEDIATE: 1, Difficulty.ADVANCED: 2}


def _base_query():
    return (
        select(Lesson)
        .join(Skill, Skill.id == Lesson.skill_id)
        .where(Lesson.is_active)
        .options(selectinload(Lesson.skill), selectinload(Lesson.topic))
        .order_by(Skill.position, Lesson.position)
    )


def _summary(lesson: Lesson) -> LessonSummary:
    return LessonSummary(
        slug=lesson.slug, title=lesson.title, difficulty=lesson.difficulty,
        estimated_minutes=lesson.estimated_minutes, summary=lesson.summary,
        skill=SkillRef(slug=lesson.skill.slug, title=lesson.skill.title),
        topic=TopicRef(slug=lesson.topic.slug, title=lesson.topic.title) if lesson.topic else None,
        status=lesson.status,
    )


async def list_lessons(db: AsyncSession, skill: str | None = None) -> list[LessonSummary]:
    stmt = _base_query()
    if skill:
        stmt = stmt.where(Skill.slug == skill)
    return [_summary(lesson) for lesson in (await db.scalars(stmt)).all()]


async def get_lesson(db: AsyncSession, slug: str) -> LessonDetail:
    lesson = await db.scalar(
        _base_query()
        .where(Lesson.slug == slug)
        .options(
            selectinload(Lesson.resources),
            selectinload(Lesson.checks).selectinload(LessonQuestion.question),
        )
    )
    if lesson is None:
        raise NotFound("Lesson not found")
    prereqs = {
        p.slug: p
        for p in (
            await db.scalars(select(Lesson).where(Lesson.slug.in_(lesson.prerequisites), Lesson.is_active))
        ).all()
    }
    base = _summary(lesson)
    return LessonDetail(
        **base.model_dump(),
        body=lesson.body,
        objectives=list(lesson.objectives),
        prerequisites=[
            LessonRef(slug=p.slug, title=p.title, difficulty=p.difficulty, estimated_minutes=p.estimated_minutes)
            for s in lesson.prerequisites
            if (p := prereqs.get(s))
        ],
        misconceptions=list(lesson.misconceptions),
        resources=[LessonResourceOut(title=r.title, url=r.url) for r in lesson.resources],
        checks=[
            LessonCheckOut(slug=c.question.slug, title=c.question.title, difficulty=c.question.difficulty, format=c.question.format)
            for c in lesson.checks
            if c.question.is_active
        ],
        version=lesson.version,
        provenance=lesson.provenance,
        updated_at=lesson.updated_at,
    )


async def progress(db: AsyncSession, learner_id: uuid.UUID) -> list[LessonProgressOut]:
    rows = await db.execute(
        select(Lesson.slug, LessonRead.first_opened_at, LessonRead.completed_at)
        .join(LessonRead, LessonRead.lesson_id == Lesson.id)
        .where(LessonRead.learner_id == learner_id)
        .order_by(LessonRead.first_opened_at)
    )
    return [LessonProgressOut(slug=s, first_opened_at=o, completed_at=c) for s, o, c in rows.all()]


async def mark(db: AsyncSession, learner_id: uuid.UUID, slug: str, now: datetime, completed: bool) -> LessonProgressOut:
    lesson = await db.scalar(select(Lesson).where(Lesson.slug == slug, Lesson.is_active))
    if lesson is None:
        raise NotFound("Lesson not found")
    stmt = pg_insert(LessonRead).values(
        learner_id=learner_id, lesson_id=lesson.id, first_opened_at=now,
        completed_at=now if completed else None,
    )
    if completed:
        # Keep the first completion time if the learner re-marks a lesson.
        stmt = stmt.on_conflict_do_update(
            index_elements=[LessonRead.learner_id, LessonRead.lesson_id],
            set_={"completed_at": stmt.excluded.completed_at},
            where=LessonRead.completed_at.is_(None),
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=[LessonRead.learner_id, LessonRead.lesson_id])
    await db.execute(stmt)
    await db.commit()
    row = await db.scalar(
        select(LessonRead).where(LessonRead.learner_id == learner_id, LessonRead.lesson_id == lesson.id)
    )
    return LessonProgressOut(slug=slug, first_opened_at=row.first_opened_at, completed_at=row.completed_at)


async def suggestions(
    db: AsyncSession, learner_id: uuid.UUID, targets: list[tuple[str, Difficulty]]
) -> dict[tuple[str, Difficulty], LessonSuggestion]:
    """For each (skill, level), the first lesson at or below that level the learner hasn't completed."""
    if not targets:
        return {}
    skills = {s for s, _ in targets}
    lessons = (
        await db.scalars(_base_query().where(Skill.slug.in_(skills)))
    ).all()
    done = set(
        (
            await db.scalars(
                select(LessonRead.lesson_id).where(
                    LessonRead.learner_id == learner_id, LessonRead.completed_at.is_not(None)
                )
            )
        ).all()
    )
    out: dict[tuple[str, Difficulty], LessonSuggestion] = {}
    for skill, level in targets:
        candidates = sorted(
            (x for x in lessons if x.skill.slug == skill and LEVEL_ORDER[x.difficulty] <= LEVEL_ORDER[level]),
            key=lambda x: (LEVEL_ORDER[x.difficulty], x.position),
        )
        pick = next((x for x in candidates if x.id not in done), None)
        if pick is not None:
            out[(skill, level)] = LessonSuggestion(
                slug=pick.slug, title=pick.title, difficulty=pick.difficulty,
                estimated_minutes=pick.estimated_minutes, completed=False,
            )
    return out
