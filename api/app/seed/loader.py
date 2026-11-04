"""Idempotent loader: syncs validated seed content into the database.

- Skills, topics and questions are matched by slug and updated in place, so ids
  (and therefore learners' answer history) survive re-seeding.
- Questions no longer present in the seed are deactivated, never deleted.
- Option rows referenced by saved answers cannot be removed; the foreign key
  makes such a seed change fail loudly instead of corrupting history.
"""

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    LearningResource,
    Question,
    QuestionOption,
    RubricCriterion,
    Skill,
    Topic,
)
from app.coding.bank_loader import BankChallenge, sync_bank
from app.curriculum.graph import Curriculum, sync_curriculum
from app.design.challenges import sync_challenges
from app.ops.library import sync_scenarios
from app.career.library import sync_career
from app.workspace.library import sync_projects
from app.seed.schema import SeedQuestion, SeedSkillFile


@dataclass(frozen=True)
class SeedStats:
    skills: int
    topics: int
    questions: int
    deactivated: int


async def _sync_options(db: AsyncSession, question: Question, seed: SeedQuestion) -> None:
    existing = {o.key: o for o in question.options}
    wanted = {o.key for o in seed.options}

    # Clear correctness first so the "one correct option" index never sees two.
    if any(o.is_correct for o in existing.values()):
        for o in existing.values():
            o.is_correct = False
        await db.flush()

    for key in set(existing) - wanted:
        await db.delete(existing[key])
    for opt in seed.options:
        row = existing.get(opt.key)
        if row is None:
            db.add(
                QuestionOption(
                    question_id=question.id, key=opt.key, text=opt.text, is_correct=opt.correct
                )
            )
        else:
            row.text = opt.text
            row.is_correct = opt.correct


async def seed_all(
    db: AsyncSession,
    curriculum: Curriculum,
    checksum: str,
    files: list[SeedSkillFile],
    bank: list[BankChallenge] | None = None,
    design: list | None = None,
    incidents: list | None = None,
    career=None,
    projects: list | None = None,
) -> SeedStats:
    """Loads the curriculum, questions and coding challenges in one transaction."""
    await sync_curriculum(db, curriculum, checksum)
    if bank:
        await sync_bank(db, bank)  # flushed; committed by seed_database
    if design:
        await sync_challenges(db, design)
    if incidents:
        await sync_scenarios(db, incidents)
    if career is not None:
        await sync_career(db, career)
    if projects:
        await sync_projects(db, projects)
    return await seed_database(db, files)


async def seed_database(db: AsyncSession, files: list[SeedSkillFile]) -> SeedStats:
    # Skills, their order and topics (subskills) are owned by the curriculum
    # (app/curriculum), which must be loaded first.
    skills_by_slug = {s.slug: s for s in (await db.scalars(select(Skill))).all()}
    seen_question_slugs: set[str] = set()
    topic_count = question_count = 0

    for f in files:
        skill = skills_by_slug.get(f.skill.slug)
        if skill is None:
            raise ValueError(f"Skill '{f.skill.slug}' is not in the curriculum")
        skill.description = f.skill.description
        topics = {
            t.slug: t
            for t in (await db.scalars(select(Topic).where(Topic.skill_id == skill.id))).all()
        }
        if [t.slug for t in f.topics] != sorted(topics, key=lambda k: topics[k].position):
            raise ValueError(
                f"{f.skill.slug}: content topics must match curriculum subskills in order"
            )
        topic_count += len(f.topics)

        for q_pos, q in enumerate(f.questions):
            question = await db.scalar(
                select(Question)
                .where(Question.slug == q.slug)
                .options(selectinload(Question.options))
            )
            fields = {
                "skill_id": skill.id,
                "topic_id": topics[q.topic].id,
                "difficulty": q.difficulty,
                "format": q.format,
                "title": q.title,
                "prompt": q.prompt,
                "code": q.code,
                "code_language": q.code_language,
                "hint": q.hint,
                "explanation": q.explanation,
                "acceptance_criteria": q.acceptance_criteria,
                "expected_concepts": list(q.expected_concepts),
                "misconceptions": list(q.misconceptions),
                "estimated_minutes": q.estimated_minutes,
                "position": q_pos,
                "is_active": True,
            }
            if question is None:
                question = Question(slug=q.slug, **fields)
                question.options = []
                db.add(question)
                await db.flush()
            else:
                for k, v in fields.items():
                    setattr(question, k, v)

            await _sync_options(db, question, q)
            await db.execute(delete(RubricCriterion).where(RubricCriterion.question_id == question.id))
            await db.execute(
                delete(LearningResource).where(LearningResource.question_id == question.id)
            )
            db.add_all(
                RubricCriterion(question_id=question.id, position=i, criterion=c)
                for i, c in enumerate(q.rubric)
            )
            db.add_all(
                LearningResource(question_id=question.id, position=i, title=r.title, url=r.url)
                for i, r in enumerate(q.resources)
            )
            seen_question_slugs.add(q.slug)
            question_count += 1
        await db.flush()

    result = await db.execute(
        update(Question)
        .where(Question.slug.not_in(seen_question_slugs), Question.is_active)
        .values(is_active=False)
    )
    await db.commit()
    return SeedStats(
        skills=len(files),
        topics=topic_count,
        questions=question_count,
        deactivated=result.rowcount or 0,
    )
