from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentLearner, Db
from app.db.models import (
    CodingChallenge,
    CodingChallengeVersion,
    DesignChallenge,
    DesignChallengeVersion,
    IncidentScenario,
    IncidentScenarioVersion,
    EngProject,
    EngProjectVersion,
    LearnerGoal,
    MasteryEvent,
    MasteryEvidence,
    MisconceptionEvent,
    Question,
    Skill,
    SkillLevel,
    Topic,
)
from app.mastery import service
from app.mastery.algorithm import ALGORITHM_VERSION, compute_mastery
from app.schemas.content import SkillRef
from app.schemas.mastery import (
    ActivityOut,
    CurriculumOut,
    CurriculumSkill,
    EvidenceOut,
    GapOut,
    GoalIn,
    GoalOut,
    LevelReportOut,
    LevelSpecOut,
    MasteryEventOut,
    MasteryOverview,
    MisconceptionHistoryOut,
    RecommendationOut,
    ReviewCardOut,
    ReviewQueueOut,
    SkillMasteryDetail,
    SkillMasteryOut,
    SubskillOut,
    SyncOut,
)
from app.services.errors import NotFound

public = APIRouter(tags=["curriculum"])
router = APIRouter(tags=["mastery"])


def get_now(request: Request) -> datetime:
    """Injectable clock so tests can control scheduling."""
    return request.app.state.clock()


Now = Annotated[datetime, Depends(get_now)]


def _ref(skill: Skill) -> SkillRef:
    return SkillRef(slug=skill.slug, title=skill.title)


def _f(v) -> float | None:
    return float(v) if v is not None else None


# ---------------------------------------------------------------- curriculum


async def _curriculum(db) -> tuple[CurriculumOut, dict[str, CurriculumSkill]]:
    contexts, edges, version = await service.load_graph(db)
    levels = defaultdict(dict)
    for lvl in (await db.scalars(select(SkillLevel))).all():
        levels[lvl.skill_id][lvl.difficulty] = lvl
    topic_counts: dict[int, int] = defaultdict(int)
    for q in (await db.scalars(select(Question).where(Question.is_active))).all():
        topic_counts[q.topic_id] += 1
    dependants: dict[str, list[str]] = defaultdict(list)
    for skill, prereqs in edges.items():
        for p in prereqs:
            dependants[p].append(skill)

    depth: dict[str, int] = {}
    for slug in service.topological_order(edges):
        depth[slug] = 1 + max((depth[p] for p in edges[slug]), default=-1)

    skills = []
    for ctx in contexts:
        s = ctx.skill
        skills.append(
            CurriculumSkill(
                slug=s.slug, title=s.title, category=s.category, summary=s.summary,
                position=s.position, depth=depth[s.slug], assessable=ctx.assessable,
                prerequisites=ctx.prerequisites, dependants=dependants[s.slug],
                learning_objectives=list(s.learning_objectives),
                subskills=[SubskillOut(slug=t.slug, title=t.title, question_count=topic_counts[t.id]) for t in s.topics],
                levels=[
                    LevelSpecOut(
                        difficulty=d, objective=levels[s.id][d].objective, competency=levels[s.id][d].competency,
                        question_count=ctx.question_counts[d], verifiable=d in ctx.verifiable_levels,
                    )
                    for d in service.LEVELS
                    if d in levels[s.id]
                ],
            )
        )
    out = CurriculumOut(
        version=version.version if version else None,
        checksum=version.checksum if version else None,
        skills=skills,
    )
    return out, {s.slug: s for s in skills}


@public.get("/curriculum", response_model=CurriculumOut)
async def get_curriculum(db: Db) -> CurriculumOut:
    return (await _curriculum(db))[0]


@public.get("/curriculum/skills/{slug}", response_model=CurriculumSkill)
async def get_curriculum_skill(slug: str, db: Db) -> CurriculumSkill:
    skill = (await _curriculum(db))[1].get(slug)
    if skill is None:
        raise NotFound(f"Skill '{slug}' not found")
    return skill


# ---------------------------------------------------------------- mastery


def _mastery_out(ctx, snap, card, snaps, by_slug) -> SkillMasteryOut:
    met = all(
        not by_slug[p].assessable
        or service.STATE_RANK[service.state_of(snaps.get(by_slug[p].skill.id))]
        >= service.STATE_RANK[service.MasteryState.DEVELOPING]
        for p in ctx.prerequisites
    )
    base = dict(
        skill=_ref(ctx.skill), review_due_at=card.due_at if card else None,
        prerequisites_met=met, assessable=ctx.assessable,
    )
    if snap is None:
        return SkillMasteryOut(
            **base, state=service.MasteryState.NOT_STARTED, demonstrated_level=None, unverified_only=False,
            knowledge_accuracy=None, reasoning_score=None, debugging_score=None, practical_score=None,
            retention_score=None, uncertainty=None, inconsistent=False, evidence_count=0, verified_count=0,
            distinct_questions=0, distinct_sessions=0, successful_attempts=0, last_evidence_at=None,
            last_success_at=None,
            reasons=["No evidence yet."] if ctx.assessable else ["No assessments exist for this skill yet."],
        )
    return SkillMasteryOut(
        **base, state=snap.state, demonstrated_level=snap.demonstrated_level,
        unverified_only=snap.unverified_only, knowledge_accuracy=_f(snap.knowledge_accuracy),
        reasoning_score=_f(snap.reasoning_score), debugging_score=_f(snap.debugging_score),
        practical_score=_f(snap.practical_score), retention_score=_f(snap.retention_score),
        uncertainty=_f(snap.uncertainty), inconsistent=snap.inconsistent,
        evidence_count=snap.evidence_count, verified_count=snap.verified_count,
        distinct_questions=snap.distinct_questions, distinct_sessions=snap.distinct_sessions,
        successful_attempts=snap.successful_attempts, last_evidence_at=snap.last_evidence_at,
        last_success_at=snap.last_success_at, reasons=list(snap.reasons),
    )


def _card_out(item_or_card, skill, now) -> ReviewCardOut:
    card = getattr(item_or_card, "card", item_or_card)
    return ReviewCardOut(
        skill=_ref(skill), due_at=card.due_at, interval_days=card.interval_days,
        repetitions=card.repetitions, ease=float(card.ease), lapses=card.lapses,
        consecutive_lapses=card.consecutive_lapses, missed_reviews=card.missed_reviews,
        last_quality=card.last_quality, last_reviewed_at=card.last_reviewed_at,
        overdue_days=max(0, (now - card.due_at).days),
        needs_relearning=card.consecutive_lapses >= service.RELEARN_AFTER_LAPSES,
    )


async def _ai_confidence(db, learner_id) -> dict[int, float]:
    rows = await db.execute(
        select(MasteryEvidence.skill_id, func.avg(MasteryEvidence.confidence))
        .where(MasteryEvidence.learner_id == learner_id, MasteryEvidence.confidence.is_not(None))
        .group_by(MasteryEvidence.skill_id)
    )
    return {skill_id: round(float(avg), 3) for skill_id, avg in rows}


async def _state(db, learner, now):
    await service.sync_learner(db, learner.id, now)
    contexts, edges, _ = await service.load_graph(db)
    snaps = await service.snapshots_for(db, learner.id)
    cards = await service.cards_for(db, learner.id)
    return contexts, edges, snaps, cards


@router.post("/mastery/recalculate", response_model=SyncOut)
async def recalculate(learner: CurrentLearner, db: Db, now: Now) -> SyncOut:
    """Idempotent: repeated calls with no new evidence change nothing."""
    stats = await service.sync_learner(db, learner.id, now)
    return SyncOut(**stats.__dict__)


@router.get("/mastery", response_model=MasteryOverview)
async def mastery_overview(learner: CurrentLearner, db: Db, now: Now) -> MasteryOverview:
    contexts, _, snaps, cards = await _state(db, learner, now)
    by_slug = {c.skill.slug: c for c in contexts}
    conf = await _ai_confidence(db, learner.id)
    skills = []
    for c in contexts:
        out = _mastery_out(c, snaps.get(c.skill.id), cards.get(c.skill.id), snaps, by_slug)
        out.ai_confidence = conf.get(c.skill.id)
        skills.append(out)
    return MasteryOverview(algorithm_version=ALGORITHM_VERSION, skills=skills)


@router.get("/mastery/{slug}", response_model=SkillMasteryDetail)
async def mastery_detail(slug: str, learner: CurrentLearner, db: Db, now: Now) -> SkillMasteryDetail:
    contexts, _, snaps, cards = await _state(db, learner, now)
    by_slug = {c.skill.slug: c for c in contexts}
    ctx = by_slug.get(slug)
    if ctx is None:
        raise NotFound(f"Skill '{slug}' not found")
    _, curriculum = await _curriculum(db)
    skill = ctx.skill

    rows = (
        await db.execute(
            # Evidence comes from questions, coding or design challenges: outer joins keep all.
            select(MasteryEvidence, func.coalesce(Question.title, CodingChallengeVersion.title, DesignChallengeVersion.title,
                                                  IncidentScenarioVersion.title, EngProjectVersion.title))
            .outerjoin(Question, Question.id == MasteryEvidence.question_id)
            .outerjoin(CodingChallenge, CodingChallenge.id == MasteryEvidence.coding_challenge_id)
            .outerjoin(CodingChallengeVersion, CodingChallengeVersion.id == CodingChallenge.current_version_id)
            .outerjoin(DesignChallenge, DesignChallenge.id == MasteryEvidence.design_challenge_id)
            .outerjoin(DesignChallengeVersion, DesignChallengeVersion.id == DesignChallenge.current_version_id)
            .outerjoin(IncidentScenario, IncidentScenario.id == MasteryEvidence.incident_scenario_id)
            .outerjoin(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
            .outerjoin(EngProject, EngProject.id == MasteryEvidence.engineering_project_id)
            .outerjoin(EngProjectVersion, EngProjectVersion.id == EngProject.current_version_id)
            .where(MasteryEvidence.learner_id == learner.id, MasteryEvidence.skill_id == skill.id)
            .order_by(MasteryEvidence.observed_at.desc())
        )
    ).all()
    ev_models = [m for m, _ in rows]
    reviews = [
        r for r in (await db.scalars(
            select(service.ReviewEvent)
            .where(service.ReviewEvent.learner_id == learner.id, service.ReviewEvent.skill_id == skill.id)
            .order_by(service.ReviewEvent.occurred_at)
        )).all()
    ]
    recurring = await service._recurring_misconceptions(db, learner.id)
    report = compute_mastery(
        [service._to_evidence(m) for m in ev_models], now=now, verifiable_levels=ctx.verifiable_levels,
        due_review_qualities=[r.quality for r in reviews[1:] if r.was_due],
        recurring_misconception=bool(recurring.get(skill.id)),
    )
    history = (
        await db.scalars(
            select(MasteryEvent)
            .where(MasteryEvent.learner_id == learner.id, MasteryEvent.skill_id == skill.id)
            .order_by(MasteryEvent.occurred_at.desc(), MasteryEvent.created_at.desc())
        )
    ).all()
    misconceptions = (
        await db.execute(
            select(MisconceptionEvent, Question.title)
            .join(Question, Question.id == MisconceptionEvent.question_id)
            .where(MisconceptionEvent.learner_id == learner.id, MisconceptionEvent.skill_id == skill.id)
            .order_by(MisconceptionEvent.created_at.desc())
            .limit(20)
        )
    ).all()
    card = cards.get(skill.id)
    mastery_out = _mastery_out(ctx, snaps.get(skill.id), card, snaps, by_slug)
    mastery_out.ai_confidence = (await _ai_confidence(db, learner.id)).get(skill.id)
    return SkillMasteryDetail(
        curriculum=curriculum[slug],
        mastery=mastery_out,
        levels=[LevelReportOut(**r.__dict__) for r in report.levels] if ev_models else [],
        evidence=[
            EvidenceOut(
                id=str(m.id), source=m.source, dimension=m.dimension, verified=m.verified,
                difficulty=m.difficulty, question_title=title, score=float(m.score), success=m.success,
                hints_used=m.hints_used, said_dont_know=m.said_dont_know, observed_at=m.observed_at,
            )
            for m, title in rows[:50]
        ],
        review=_card_out(card, skill, now) if card else None,
        history=[_event_out(e, skill) for e in history],
        misconceptions=[
            MisconceptionHistoryOut(
                description=m.description, known_misconception=m.known_misconception, quote=m.quote,
                observed=m.observed, question_title=title, created_at=m.created_at,
            )
            for m, title in misconceptions
        ],
        prerequisite_states={p: service.state_of(snaps.get(by_slug[p].skill.id)) for p in ctx.prerequisites},
    )


def _event_out(e: MasteryEvent, skill: Skill) -> MasteryEventOut:
    return MasteryEventOut(
        skill=_ref(skill), from_state=e.from_state, to_state=e.to_state, from_level=e.from_level,
        to_level=e.to_level, reason=e.reason, occurred_at=e.occurred_at,
    )


@router.get("/progress/history", response_model=list[MasteryEventOut])
async def progress_history(
    learner: CurrentLearner, db: Db, now: Now, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[MasteryEventOut]:
    await service.sync_learner(db, learner.id, now)
    rows = (
        await db.execute(
            select(MasteryEvent, Skill)
            .join(Skill, Skill.id == MasteryEvent.skill_id)
            .where(MasteryEvent.learner_id == learner.id)
            .order_by(MasteryEvent.occurred_at.desc(), MasteryEvent.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [_event_out(e, s) for e, s in rows]


# ---------------------------------------------------------------- reviews, gaps, recommendations


@router.get("/reviews", response_model=ReviewQueueOut)
async def reviews(learner: CurrentLearner, db: Db, now: Now) -> ReviewQueueOut:
    contexts, _, snaps, cards = await _state(db, learner, now)
    due, upcoming, total = service.review_queue(contexts, cards, snaps, now)
    return ReviewQueueOut(
        daily_limit=service.DAILY_REVIEW_LIMIT,
        total_due=total,
        due=[_card_out(i, i.skill, now) for i in due],
        upcoming=[_card_out(i, i.skill, now) for i in upcoming],
    )


def _gap_out(g: service.Gap) -> GapOut:
    return GapOut(
        kind=g.kind, skill=_ref(g.skill), title=g.title, detail=g.detail, occurrences=g.occurrences,
        last_seen=g.last_seen, related_skill=_ref(g.related_skill) if g.related_skill else None,
        evidence=[e for e in (g.evidence or []) if e],
    )


@router.get("/gaps", response_model=list[GapOut])
async def gaps(learner: CurrentLearner, db: Db, now: Now) -> list[GapOut]:
    contexts, _, _, _ = await _state(db, learner, now)
    return [_gap_out(g) for g in await service.detect_gaps(db, learner.id, contexts, now)]


@router.get("/recommendations", response_model=list[RecommendationOut])
async def recommendations(
    learner: CurrentLearner, db: Db, now: Now, limit: Annotated[int, Query(ge=1, le=20)] = 6
) -> list[RecommendationOut]:
    contexts, edges, snaps, cards = await _state(db, learner, now)
    found = await service.detect_gaps(db, learner.id, contexts, now)
    goals = await service.goals_for(db, learner.id)
    coding = await service.coding_progress(db, learner.id)
    recs = service.recommend(contexts, edges, snaps, cards, found, goals, now, limit, coding)
    by_slug = {c.skill.slug: c for c in contexts}
    return [
        RecommendationOut(
            key=r.key, kind=r.kind, skill=_ref(r.skill),
            activity=ActivityOut(
                type=r.activity.type, skill_slug=r.activity.skill_slug,
                difficulty=r.activity.difficulty, mode=r.activity.mode,
                challenge_slug=r.activity.challenge_slug,
            ),
            priority=round(r.priority, 2), reasons=r.reasons,
            interview_alternative=_interview_alternative(r, by_slug),
        )
        for r in recs
    ]


def _interview_alternative(r, by_slug) -> ActivityOut | None:
    if r.activity.type == "interview":
        return None
    if not any(by_slug[r.skill.slug].question_counts.values()):
        return None  # no interview content for coding-only skills
    alt = service._activity(by_slug[r.skill.slug], r.activity.difficulty, prefer_interview=_mode_for(r))
    return ActivityOut(type="interview", skill_slug=alt.skill_slug, difficulty=alt.difficulty, mode=alt.mode)


def _mode_for(r) -> service.InterviewMode:
    if r.skill.slug == "system-design":
        return service.InterviewMode.ARCHITECT
    if r.kind in ("review", "advance") and r.activity.difficulty is service.Difficulty.ADVANCED:
        return service.InterviewMode.GRILL
    return service.InterviewMode.TUTOR


# ---------------------------------------------------------------- goals


@router.get("/goals", response_model=list[GoalOut])
async def list_goals(learner: CurrentLearner, db: Db) -> list[GoalOut]:
    rows = (
        await db.execute(
            select(LearnerGoal, Skill).join(Skill, Skill.id == LearnerGoal.skill_id)
            .where(LearnerGoal.learner_id == learner.id).order_by(Skill.position)
        )
    ).all()
    return [GoalOut(skill=_ref(s), target_level=g.target_level, created_at=g.created_at) for g, s in rows]


@router.put("/goals/{slug}", response_model=GoalOut)
async def set_goal(slug: str, payload: GoalIn, learner: CurrentLearner, db: Db) -> GoalOut:
    skill = await db.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        raise NotFound(f"Skill '{slug}' not found")
    row = await db.scalar(
        pg_insert(LearnerGoal)
        .values(learner_id=learner.id, skill_id=skill.id, target_level=payload.target_level)
        .on_conflict_do_update(
            index_elements=[LearnerGoal.learner_id, LearnerGoal.skill_id],
            set_={"target_level": payload.target_level},
        )
        .returning(LearnerGoal)
    )
    await db.commit()
    return GoalOut(skill=_ref(skill), target_level=row.target_level, created_at=row.created_at)


@router.delete("/goals/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(slug: str, learner: CurrentLearner, db: Db) -> Response:
    skill = await db.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        raise NotFound(f"Skill '{slug}' not found")
    await db.execute(delete(LearnerGoal).where(LearnerGoal.learner_id == learner.id, LearnerGoal.skill_id == skill.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
