import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Question, Skill, Topic
from app.schemas.content import (
    DifficultyCounts,
    OptionPublic,
    QuestionPublic,
    SkillDetail,
    SkillSummary,
    TopicOut,
    TopicRef,
)
from app.services.errors import NotFound
from app.services.option_order import presented_options


async def _question_counts(db: AsyncSession) -> dict[int, dict[int | None, dict[str, int]]]:
    """skill_id -> topic_id -> difficulty -> active question count."""
    rows = await db.execute(
        select(Question.skill_id, Question.topic_id, Question.difficulty, func.count())
        .where(Question.is_active)
        .group_by(Question.skill_id, Question.topic_id, Question.difficulty)
    )
    counts: dict[int, dict[int | None, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for skill_id, topic_id, difficulty, n in rows:
        counts[skill_id][topic_id][difficulty.value] += n
    return counts


def _summary(skill: Skill, by_topic: dict[int | None, dict[str, int]]) -> dict:
    by_difficulty: dict[str, int] = defaultdict(int)
    for per_topic in by_topic.values():
        for difficulty, n in per_topic.items():
            by_difficulty[difficulty] += n
    return {
        "slug": skill.slug,
        "title": skill.title,
        "summary": skill.summary,
        "position": skill.position,
        "topic_count": len(skill.topics),
        "question_count": sum(by_difficulty.values()),
        "questions_by_difficulty": DifficultyCounts(**by_difficulty),
    }


async def list_skills(db: AsyncSession) -> list[SkillSummary]:
    skills = (
        await db.scalars(select(Skill).options(selectinload(Skill.topics)).order_by(Skill.position))
    ).all()
    counts = await _question_counts(db)
    return [SkillSummary(**_summary(s, counts[s.id])) for s in skills]


async def get_skill(db: AsyncSession, slug: str) -> SkillDetail:
    skill = await db.scalar(
        select(Skill).where(Skill.slug == slug).options(selectinload(Skill.topics))
    )
    if skill is None:
        raise NotFound(f"Skill '{slug}' not found")
    counts = (await _question_counts(db))[skill.id]
    return SkillDetail(
        **_summary(skill, counts),
        description=skill.description,
        topics=[
            TopicOut(slug=t.slug, title=t.title, question_count=sum(counts[t.id].values()))
            for t in skill.topics
        ],
    )


def public_question(
    question: Question, topic: Topic, item_id: uuid.UUID | None = None
) -> QuestionPublic:
    """Learner-safe view. Never include correctness, explanations or rubrics here.

    With ``item_id`` (a question served in an assessment), options are shown in
    that item's presentation order and relabelled by position; see option_order.
    """
    if item_id is not None:
        options = [
            OptionPublic(key=k, text=o.text) for k, o in presented_options(item_id, question.options)
        ]
    else:
        options = [OptionPublic(key=o.key, text=o.text) for o in question.options]
    return QuestionPublic(
        slug=question.slug,
        title=question.title,
        prompt=question.prompt,
        code=question.code,
        code_language=question.code_language,
        hint=question.hint,
        format=question.format,
        difficulty=question.difficulty,
        estimated_minutes=question.estimated_minutes,
        topic=TopicRef(slug=topic.slug, title=topic.title),
        options=options,
    )
