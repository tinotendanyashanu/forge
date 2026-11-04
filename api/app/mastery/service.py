"""Mastery engine: evidence ingestion, recalculation, gaps, reviews, recommendations.

``sync_learner`` is the only writer. It is idempotent: evidence is unique per
source, review events are unique per evidence, snapshots are recomputed only
when the evidence hash changes, and mastery events are unique per hash.
"""

import hashlib
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.curriculum.graph import ancestors, topological_order
from app.db.enums import (
    ChallengeStatus,
    DesignLevel,
    Difficulty,
    EvaluationStatus,
    EvidenceDimension,
    EvidenceSource,
    InterviewEvaluationStatus,
    InterviewMode,
    MasteryState,
    QuestionFormat,
)
from app.db.models import (
    Answer,
    ArchitectureProject,
    CodingChallenge,
    CodingSubmission,
    EngProject,
    EngSubmission,
    CurriculumVersion,
    DesignChallenge,
    DesignChallengeVersion,
    DesignEvaluation,
    DesignReview,
    EvaluationResult,
    FailureAttempt,
    IncidentEvaluation,
    IncidentScenario,
    IncidentScenarioVersion,
    IncidentSession,
    InterviewChallenge,
    InterviewEvaluation,
    InterviewSession,
    LearnerGoal,
    MasteryEvent,
    MasteryEvidence,
    MisconceptionEvent,
    Question,
    ReviewCard,
    ReviewEvent,
    SessionItem,
    Skill,
    SkillMastery,
    SkillPrerequisite,
)
from app.mastery.algorithm import (
    AI_SUCCESS_SCORE,
    ALGORITHM_VERSION,
    LEVELS,
    CardState,
    Evidence,
    MasteryResult,
    apply_review,
    compute_mastery,
    new_card,
    quality_for,
)

DAILY_REVIEW_LIMIT = 5
RELEARN_AFTER_LAPSES = 3
RECURRING_THRESHOLD = 2
RECENT_DAYS = 30
STATE_RANK = {
    MasteryState.NOT_STARTED: 0,
    MasteryState.INSUFFICIENT_EVIDENCE: 1,
    MasteryState.LEARNING: 2,
    MasteryState.DEVELOPING: 3,
    MasteryState.PROFICIENT: 4,
    MasteryState.MASTERED: 5,
}


# ---------------------------------------------------------------- ingestion


async def _objective_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(Answer, EvaluationResult, SessionItem.session_id, Question)
        .join(EvaluationResult, EvaluationResult.answer_id == Answer.id)
        .join(SessionItem, SessionItem.id == Answer.session_item_id)
        .join(Question, Question.id == Answer.question_id)
        .where(Answer.learner_id == learner_id, EvaluationResult.status == EvaluationStatus.GRADED)
    )
    return [
        dict(
            learner_id=learner_id, skill_id=q.skill_id, question_id=q.id, difficulty=q.difficulty,
            coding_challenge_id=None, design_challenge_id=None, incident_scenario_id=None,
            source=EvidenceSource.OBJECTIVE_ASSESSMENT, source_id=a.id, session_id=sid,
            verified=True, dimension=EvidenceDimension.KNOWLEDGE,
            score=Decimal(1 if ev.is_correct else 0), success=bool(ev.is_correct),
            hints_used=0, said_dont_know=False, confidence=None, observed_at=a.submitted_at,
        )
        for a, ev, sid, q in rows
    ]


async def _interview_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    challenges = (
        await db.scalars(
            select(InterviewChallenge)
            .join(InterviewSession, InterviewSession.id == InterviewChallenge.session_id)
            .where(
                InterviewSession.learner_id == learner_id,
                InterviewChallenge.status == ChallengeStatus.COMPLETED,
            )
            .options(
                selectinload(InterviewChallenge.evaluations),
                selectinload(InterviewChallenge.session),
                selectinload(InterviewChallenge.question),
            )
        )
    ).all()
    out: list[dict] = []
    for c in challenges:
        evaluated = [e for e in c.evaluations if e.status is InterviewEvaluationStatus.EVALUATED]
        final = evaluated[-1] if evaluated else None
        base = dict(
            learner_id=learner_id, skill_id=c.question.skill_id, question_id=c.question_id,
            coding_challenge_id=None, design_challenge_id=None, incident_scenario_id=None, difficulty=c.difficulty, source_id=c.id, session_id=c.session_id, verified=False,
            hints_used=c.hints_used, said_dont_know=c.said_dont_know, observed_at=c.completed_at,
        )
        if final is not None and final.mastery_eligible:
            score = float(final.total_score or 0)
            out.append(
                base | dict(
                    source=EvidenceSource.AI_INTERVIEW,
                    dimension=EvidenceDimension.DEBUGGING
                    if c.session.mode is InterviewMode.DEBUG
                    else EvidenceDimension.REASONING,
                    score=final.total_score,
                    success=score >= AI_SUCCESS_SCORE and c.hints_used <= 1 and not c.said_dont_know,
                    confidence=final.confidence,
                )
            )
        elif final is None and c.said_dont_know:
            out.append(
                base | dict(
                    source=EvidenceSource.SELF_REPORT, dimension=EvidenceDimension.KNOWLEDGE,
                    score=Decimal(0), success=False, confidence=None,
                )
            )
        # Ineligible AI evaluations (low confidence, suspected injection, no
        # verified quotes) and ungraded answers produce no evidence at all.
    return out


async def _coding_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    """Only submissions executed by a verified sandbox are evidence. Mock runs never are."""
    rows = await db.execute(
        select(CodingSubmission, CodingChallenge)
        .join(CodingChallenge, CodingChallenge.id == CodingSubmission.challenge_id)
        .where(
            CodingSubmission.learner_id == learner_id,
            CodingSubmission.executed,
            CodingSubmission.verified,
        )
    )
    return [
        dict(
            learner_id=learner_id, skill_id=ch.skill_id, question_id=None, coding_challenge_id=ch.id, design_challenge_id=None, incident_scenario_id=None,
            difficulty=ch.difficulty, source=EvidenceSource.CODING_SUBMISSION, source_id=sub.id,
            session_id=sub.id, verified=True, dimension=EvidenceDimension.PRACTICAL,
            score=Decimal(sub.passed) / Decimal(sub.total) if sub.total else Decimal(0),
            success=sub.all_passed and sub.hints_used <= 1, hints_used=sub.hints_used,
            said_dont_know=False, confidence=None, observed_at=sub.created_at,
        )
        for sub, ch in rows
    ]


DESIGN_DIFFICULTY = {
    DesignLevel.BEGINNER: Difficulty.BEGINNER,
    DesignLevel.INTERMEDIATE: Difficulty.INTERMEDIATE,
    DesignLevel.ADVANCED: Difficulty.ADVANCED,
    DesignLevel.SENIOR: Difficulty.ADVANCED,
}


async def _design_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    """AI design evaluations and failure-scenario analyses: unverified reasoning evidence.

    Only mastery-eligible results count (validated output, verified evidence,
    confidence threshold, no suspected injection). Ungraded attempts never do.
    Evidence goes to the challenge's primary skill; the project is the session.
    """
    evals = await db.execute(
        select(DesignEvaluation, ArchitectureProject, DesignChallenge, DesignChallengeVersion, DesignReview)
        .join(ArchitectureProject, ArchitectureProject.id == DesignEvaluation.project_id)
        .join(DesignChallenge, DesignChallenge.id == ArchitectureProject.challenge_id)
        .join(DesignChallengeVersion, DesignChallengeVersion.id == DesignEvaluation.challenge_version_id)
        .join(DesignReview, DesignReview.id == DesignEvaluation.review_id)
        .where(ArchitectureProject.learner_id == learner_id, DesignEvaluation.status == "evaluated",
               DesignEvaluation.mastery_eligible)
    )
    fails = await db.execute(
        select(FailureAttempt, ArchitectureProject, DesignChallenge, DesignChallengeVersion)
        .join(ArchitectureProject, ArchitectureProject.id == FailureAttempt.project_id)
        .join(DesignChallenge, DesignChallenge.id == ArchitectureProject.challenge_id)
        .join(DesignChallengeVersion, DesignChallengeVersion.id == ArchitectureProject.challenge_version_id)
        .where(ArchitectureProject.learner_id == learner_id, FailureAttempt.status == "evaluated",
               FailureAttempt.mastery_eligible)
    )
    skills = {s.slug: s.id for s in (await db.scalars(select(Skill))).all()}
    out: list[dict] = []

    def base(project, ch, version) -> dict | None:
        skill_id = skills.get(version.content["skills"][0])
        if skill_id is None:
            return None
        return dict(learner_id=learner_id, skill_id=skill_id, question_id=None, coding_challenge_id=None,
                    design_challenge_id=ch.id, incident_scenario_id=None, difficulty=DESIGN_DIFFICULTY[ch.level], session_id=project.id,
                    verified=False, dimension=EvidenceDimension.REASONING, said_dont_know=False)

    for ev, project, ch, version, review in evals:
        if (b := base(project, ch, version)) is None:
            continue
        out.append(b | dict(
            source=EvidenceSource.DESIGN_EVALUATION, source_id=ev.id, score=ev.total_score,
            success=float(ev.total_score) >= AI_SUCCESS_SCORE and review.hints_used <= 1,
            hints_used=review.hints_used, confidence=ev.confidence, observed_at=ev.completed_at,
        ))
    for fa, project, ch, version in fails:
        if (b := base(project, ch, version)) is None:
            continue
        out.append(b | dict(
            source=EvidenceSource.FAILURE_SCENARIO, source_id=fa.id, score=fa.score,
            success=float(fa.score) >= AI_SUCCESS_SCORE, hints_used=0,
            confidence=Decimal(str(round(float((fa.result or {}).get("confidence", 0)), 3))),
            observed_at=fa.completed_at,
        ))
    return out


OPS_DIFFICULTY = {"beginner": Difficulty.BEGINNER, "intermediate": Difficulty.INTERMEDIATE,
                  "advanced": Difficulty.ADVANCED, "senior": Difficulty.ADVANCED}


async def _incident_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    """FORGE OPS. Two separate kinds of evidence, on the scenario's primary skill:

    * incident_simulation (verified, practical): the deterministic outcome of a
      resolved attempt (root cause chosen, key evidence, safety, efficiency),
      graded only by scenario rules.
    * incident_review (unverified, debugging): a mastery-eligible AI review of
      the root-cause analysis. Advisory, weight 0.5.
    Abandoned or unresolved attempts produce no evidence.
    """
    skills = {s.slug: s.id for s in (await db.scalars(select(Skill))).all()}
    sessions = (await db.execute(
        select(IncidentSession, IncidentScenario, IncidentScenarioVersion)
        .join(IncidentScenario, IncidentScenario.id == IncidentSession.scenario_id)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentSession.version_id)
        .where(IncidentSession.learner_id == learner_id, IncidentSession.outcome_score.is_not(None),
               IncidentSession.status.in_(("resolved", "postmortem")))
    )).all()
    reviews = {e.session_id: e for e in (await db.scalars(
        select(IncidentEvaluation).where(
            IncidentEvaluation.session_id.in_([s.id for s, _, _ in sessions] or [uuid.uuid4()]),
            IncidentEvaluation.kind == "rca", IncidentEvaluation.status == "evaluated",
            IncidentEvaluation.mastery_eligible,
        ).order_by(IncidentEvaluation.created_at)
    )).all()}
    out: list[dict] = []
    for sess, sc, version in sessions:
        skill_id = skills.get(version.content["skills"][0])
        if skill_id is None:
            continue
        base = dict(learner_id=learner_id, skill_id=skill_id, question_id=None, coding_challenge_id=None,
                    design_challenge_id=None, incident_scenario_id=sc.id, difficulty=OPS_DIFFICULTY[sc.level],
                    session_id=sess.id, said_dont_know=False, hints_used=0, observed_at=sess.ended_at)
        out.append(base | dict(source=EvidenceSource.INCIDENT_SIMULATION, source_id=sess.id, verified=True,
                               dimension=EvidenceDimension.PRACTICAL, score=sess.outcome_score,
                               success=bool(sess.success), confidence=None))
        if (ev := reviews.get(sess.id)) is not None:
            out.append(base | dict(source=EvidenceSource.INCIDENT_REVIEW, source_id=ev.id, verified=False,
                                   dimension=EvidenceDimension.DEBUGGING, score=ev.total_score,
                                   success=float(ev.total_score) >= AI_SUCCESS_SCORE,
                                   confidence=ev.confidence, observed_at=ev.completed_at))
    return out


async def _engineering_rows(db: AsyncSession, learner_id: uuid.UUID) -> list[dict]:
    """FORGE Workspace (v1.5): project submissions executed by a verified sandbox.

    Verified practical evidence on the project's primary skill, score = share of
    hidden tests passed, success = every test passed with at most one hint.
    The workspace is the session, so advanced levels need successes on two
    different projects. Mock or unverified runs and AI reviews never count.
    """
    rows = await db.execute(
        select(EngSubmission, EngProject)
        .join(EngProject, EngProject.id == EngSubmission.project_id)
        .where(EngSubmission.learner_id == learner_id, EngSubmission.executed, EngSubmission.verified)
    )
    return [
        dict(
            learner_id=learner_id, skill_id=project.skill_id, question_id=None, coding_challenge_id=None,
            design_challenge_id=None, incident_scenario_id=None, engineering_project_id=project.id,
            difficulty=project.difficulty, source=EvidenceSource.ENGINEERING_TASK, source_id=sub.id,
            session_id=sub.workspace_id, verified=True, dimension=EvidenceDimension.PRACTICAL,
            score=Decimal(sub.hidden_passed) / Decimal(sub.hidden_total) if sub.hidden_total else Decimal(0),
            success=sub.all_passed and sub.hints_used <= 1, hints_used=sub.hints_used,
            said_dont_know=False, confidence=None, observed_at=sub.created_at,
        )
        for sub, project in rows
    ]


async def ingest_evidence(db: AsyncSession, learner_id: uuid.UUID) -> int:
    rows = (
        await _objective_rows(db, learner_id)
        + await _interview_rows(db, learner_id)
        + await _coding_rows(db, learner_id)
        + await _design_rows(db, learner_id)
        + await _incident_rows(db, learner_id)
    )
    # Multi-row inserts need uniform keys; only engineering rows set this subject.
    rows = [{"engineering_project_id": None, **r} for r in rows] + await _engineering_rows(db, learner_id)
    if not rows:
        return 0
    result = await db.execute(
        pg_insert(MasteryEvidence)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[MasteryEvidence.source, MasteryEvidence.source_id])
        .returning(MasteryEvidence.id)
    )
    return len(result.all())


# ---------------------------------------------------------------- recalculation


def _to_evidence(m: MasteryEvidence) -> Evidence:
    return Evidence(
        id=str(m.id),
        question_id=m.question_id if m.question_id is not None
        else f"c{m.coding_challenge_id}" if m.coding_challenge_id is not None
        else f"d{m.design_challenge_id}" if m.design_challenge_id is not None
        else f"e{m.engineering_project_id}" if m.engineering_project_id is not None else f"i{m.incident_scenario_id}",
        session_id=str(m.session_id),
        difficulty=m.difficulty, source=m.source, dimension=m.dimension, verified=m.verified,
        score=float(m.score), success=m.success, hints_used=m.hints_used,
        said_dont_know=m.said_dont_know, observed_at=m.observed_at,
    )


async def _process_reviews(db: AsyncSession, learner_id: uuid.UUID) -> None:
    pending = (
        await db.scalars(
            select(MasteryEvidence)
            .outerjoin(ReviewEvent, ReviewEvent.evidence_id == MasteryEvidence.id)
            .where(MasteryEvidence.learner_id == learner_id, ReviewEvent.id.is_(None))
            .order_by(MasteryEvidence.observed_at, MasteryEvidence.id)
        )
    ).all()
    cards = {
        c.skill_id: c
        for c in (await db.scalars(select(ReviewCard).where(ReviewCard.learner_id == learner_id))).all()
    }
    for m in pending:
        card = cards.get(m.skill_id)
        if card is None:
            state = new_card(m.observed_at)
            card = ReviewCard(learner_id=learner_id, skill_id=m.skill_id, due_at=state.due_at)
            db.add(card)
            cards[m.skill_id] = card
        else:
            state = CardState(
                card.repetitions, card.interval_days, Decimal(card.ease), card.due_at,
                card.lapses, card.consecutive_lapses, card.missed_reviews,
            )
        outcome = apply_review(state, quality_for(_to_evidence(m)), m.observed_at)
        new = outcome.card
        db.add(
            ReviewEvent(
                learner_id=learner_id, skill_id=m.skill_id, evidence_id=m.id,
                quality=outcome.quality, was_due=outcome.was_due, overdue_days=outcome.overdue_days,
                interval_before=state.interval_days, interval_after=new.interval_days,
                due_before=state.due_at, due_after=new.due_at, occurred_at=m.observed_at,
            )
        )
        card.repetitions, card.interval_days, card.ease = new.repetitions, new.interval_days, new.ease
        card.due_at, card.lapses = new.due_at, new.lapses
        card.consecutive_lapses, card.missed_reviews = new.consecutive_lapses, new.missed_reviews
        card.last_quality, card.last_reviewed_at = outcome.quality, m.observed_at
        await db.flush()


async def _verifiable_levels(db: AsyncSession) -> dict[int, set[Difficulty]]:
    """Levels with deterministic grading: objective questions or coding challenges."""
    out: dict[int, set[Difficulty]] = defaultdict(set)
    for skill_id, difficulty in await db.execute(
        select(Question.skill_id, Question.difficulty)
        .where(Question.is_active, Question.format == QuestionFormat.SINGLE_CHOICE)
        .distinct()
    ):
        out[skill_id].add(difficulty)
    for skill_id, difficulty in await db.execute(
        select(CodingChallenge.skill_id, CodingChallenge.difficulty).where(CodingChallenge.is_active).distinct()
    ):
        out[skill_id].add(difficulty)
    # FORGE Workspace projects are graded by hidden tests in the sandbox (v1.5).
    for skill_id, difficulty in await db.execute(
        select(EngProject.skill_id, EngProject.difficulty).where(EngProject.is_active).distinct()
    ):
        out[skill_id].add(difficulty)
    # FORGE OPS outcomes are graded deterministically by scenario rules (v1.4).
    skills = {s.slug: s.id for s in (await db.scalars(select(Skill))).all()}
    for level, content in await db.execute(
        select(IncidentScenario.level, IncidentScenarioVersion.content)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
        .where(IncidentScenario.is_active)
    ):
        if (sid := skills.get(content["skills"][0])) is not None:
            out[sid].add(OPS_DIFFICULTY[level])
    return out


async def _recurring_misconceptions(db: AsyncSession, learner_id: uuid.UUID) -> dict[int, list[tuple[str, int]]]:
    rows = (
        await db.scalars(select(MisconceptionEvent).where(MisconceptionEvent.learner_id == learner_id))
    ).all()
    counts: dict[int, Counter] = defaultdict(Counter)
    for m in rows:
        counts[m.skill_id][(m.known_misconception or m.description).strip().lower()] += 1
    return {
        skill: [(k, n) for k, n in c.most_common() if n >= RECURRING_THRESHOLD]
        for skill, c in counts.items()
    }


def _hash(evidence: list[MasteryEvidence], reviews: list[ReviewEvent], recurring: bool) -> str:
    h = hashlib.sha256(ALGORITHM_VERSION.encode())
    for m in sorted(evidence, key=lambda m: str(m.id)):
        h.update(str(m.id).encode())
    for r in sorted(reviews, key=lambda r: str(r.id)):
        h.update(f"{r.id}:{r.quality}:{int(r.was_due)}".encode())
    h.update(b"recurring" if recurring else b"-")
    return h.hexdigest()


@dataclass(frozen=True)
class SyncStats:
    new_evidence: int
    skills_recomputed: int
    events_created: int


async def sync_learner(db: AsyncSession, learner_id: uuid.UUID, now: datetime) -> SyncStats:
    """Idempotent: running it twice with no new evidence changes nothing."""
    # Serialise concurrent syncs for the same learner.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": str(learner_id)})
    new_evidence = await ingest_evidence(db, learner_id)
    await _process_reviews(db, learner_id)

    evidence = (
        await db.scalars(select(MasteryEvidence).where(MasteryEvidence.learner_id == learner_id))
    ).all()
    reviews = (await db.scalars(select(ReviewEvent).where(ReviewEvent.learner_id == learner_id))).all()
    snapshots = {
        s.skill_id: s
        for s in (await db.scalars(select(SkillMastery).where(SkillMastery.learner_id == learner_id))).all()
    }
    verifiable = await _verifiable_levels(db)
    recurring = await _recurring_misconceptions(db, learner_id)

    by_skill: dict[int, list[MasteryEvidence]] = defaultdict(list)
    for m in evidence:
        by_skill[m.skill_id].append(m)
    reviews_by_skill: dict[int, list[ReviewEvent]] = defaultdict(list)
    for r in reviews:
        reviews_by_skill[r.skill_id].append(r)

    recomputed = events = 0
    for skill_id, items in by_skill.items():
        skill_reviews = sorted(reviews_by_skill[skill_id], key=lambda r: (r.occurred_at, str(r.id)))
        is_recurring = bool(recurring.get(skill_id))
        digest = _hash(items, skill_reviews, is_recurring)
        previous = snapshots.get(skill_id)
        if previous is not None and previous.evidence_hash == digest:
            continue
        result = compute_mastery(
            [_to_evidence(m) for m in items],
            now=now,
            verifiable_levels=verifiable.get(skill_id, set()),
            # The first exposure isn't a retention check: nothing was learned before it.
            due_review_qualities=[r.quality for r in skill_reviews[1:] if r.was_due],
            recurring_misconception=is_recurring,
        )
        # Capture before writing: _write_snapshot updates the row in place.
        prev_state = previous.state if previous else None
        prev_level = previous.demonstrated_level if previous else None
        _write_snapshot(db, learner_id, skill_id, previous, result, digest, now)
        recomputed += 1
        changed = previous is None or (
            prev_state != result.state or prev_level != result.demonstrated_level
        )
        if changed:
            inserted = await db.execute(
                pg_insert(MasteryEvent)
                .values(
                    learner_id=learner_id, skill_id=skill_id,
                    from_state=prev_state, to_state=result.state,
                    from_level=prev_level,
                    to_level=result.demonstrated_level, reason=result.reasons[0],
                    evidence_hash=digest, occurred_at=result.last_evidence_at or now,
                )
                .on_conflict_do_nothing(
                    index_elements=[MasteryEvent.learner_id, MasteryEvent.skill_id, MasteryEvent.evidence_hash]
                )
                .returning(MasteryEvent.id)
            )
            events += len(inserted.all())
    await db.commit()
    return SyncStats(new_evidence, recomputed, events)


def _write_snapshot(
    db: AsyncSession,
    learner_id: uuid.UUID,
    skill_id: int,
    row: SkillMastery | None,
    r: MasteryResult,
    digest: str,
    now: datetime,
) -> None:
    fields = dict(
        state=r.state, demonstrated_level=r.demonstrated_level, unverified_only=r.unverified_only,
        knowledge_accuracy=r.knowledge_accuracy, reasoning_score=r.reasoning_score,
        debugging_score=r.debugging_score, practical_score=r.practical_score,
        retention_score=r.retention_score, uncertainty=r.uncertainty, inconsistent=r.inconsistent,
        evidence_count=r.evidence_count, verified_count=r.verified_count,
        distinct_questions=r.distinct_questions, distinct_sessions=r.distinct_sessions,
        successful_attempts=r.successful_attempts, last_evidence_at=r.last_evidence_at,
        last_success_at=r.last_success_at, reasons=r.reasons, evidence_hash=digest,
        algorithm_version=ALGORITHM_VERSION, computed_at=now,
    )
    if row is None:
        db.add(SkillMastery(learner_id=learner_id, skill_id=skill_id, **fields))
    else:
        for k, v in fields.items():
            setattr(row, k, v)


# ---------------------------------------------------------------- read models


@dataclass
class CodingInfo:
    slug: str
    title: str
    difficulty: Difficulty
    prerequisites: list[str]


@dataclass
class SkillContext:
    skill: Skill
    prerequisites: list[str]
    assessable: bool
    question_counts: dict[Difficulty, int]
    verifiable_levels: set[Difficulty]
    challenges: list[CodingInfo] = field(default_factory=list)
    objective_levels: set[Difficulty] = field(default_factory=set)


async def load_graph(db: AsyncSession) -> tuple[list[SkillContext], dict[str, list[str]], CurriculumVersion | None]:
    skills = (
        await db.scalars(select(Skill).options(selectinload(Skill.topics)).order_by(Skill.position))
    ).all()
    by_id = {s.id: s for s in skills}
    edges: dict[str, list[str]] = {s.slug: [] for s in skills}
    for e in (await db.scalars(select(SkillPrerequisite))).all():
        edges[by_id[e.skill_id].slug].append(by_id[e.prerequisite_id].slug)
    counts: dict[int, dict[Difficulty, int]] = defaultdict(lambda: defaultdict(int))
    for skill_id, difficulty, n in await db.execute(
        select(Question.skill_id, Question.difficulty, func.count())
        .where(Question.is_active)
        .group_by(Question.skill_id, Question.difficulty)
    ):
        counts[skill_id][difficulty] = n
    verifiable = await _verifiable_levels(db)
    objective: dict[int, set[Difficulty]] = defaultdict(set)
    for skill_id, difficulty in await db.execute(
        select(Question.skill_id, Question.difficulty)
        .where(Question.is_active, Question.format == QuestionFormat.SINGLE_CHOICE).distinct()
    ):
        objective[skill_id].add(difficulty)
    version = await db.scalar(select(CurriculumVersion).where(CurriculumVersion.is_current))
    coding: dict[int, list[CodingInfo]] = defaultdict(list)
    for ch in (await db.scalars(
        select(CodingChallenge).where(CodingChallenge.is_active)
        .options(selectinload(CodingChallenge.current_version)).order_by(CodingChallenge.position)
    )).all():
        if ch.current_version is not None:
            coding[ch.skill_id].append(CodingInfo(
                ch.slug, ch.current_version.title, ch.difficulty, list(ch.current_version.prerequisites)))
    contexts = [
        SkillContext(
            skill=s,
            prerequisites=sorted(edges[s.slug], key=lambda slug: next(x.position for x in skills if x.slug == slug)),
            assessable=sum(counts[s.id].values()) > 0 or bool(coding[s.id]),
            question_counts={d: counts[s.id].get(d, 0) for d in LEVELS},
            verifiable_levels=verifiable.get(s.id, set()),
            challenges=coding[s.id],
            objective_levels=objective.get(s.id, set()),
        )
        for s in skills
    ]
    return contexts, edges, version


async def snapshots_for(db: AsyncSession, learner_id: uuid.UUID) -> dict[int, SkillMastery]:
    return {
        s.skill_id: s
        for s in (await db.scalars(select(SkillMastery).where(SkillMastery.learner_id == learner_id))).all()
    }


async def cards_for(db: AsyncSession, learner_id: uuid.UUID) -> dict[int, ReviewCard]:
    return {
        c.skill_id: c
        for c in (await db.scalars(select(ReviewCard).where(ReviewCard.learner_id == learner_id))).all()
    }


def state_of(snap: SkillMastery | None) -> MasteryState:
    return snap.state if snap else MasteryState.NOT_STARTED


# ---------------------------------------------------------------- reviews


@dataclass
class ReviewItem:
    skill: Skill
    card: ReviewCard
    overdue_days: int
    needs_relearning: bool
    priority: float


def review_queue(
    contexts: list[SkillContext],
    cards: dict[int, ReviewCard],
    snaps: dict[int, SkillMastery],
    now: datetime,
) -> tuple[list[ReviewItem], list[ReviewItem], int]:
    """(due today — capped, upcoming within 7 days, total due).

    Cards reviewed today are excluded so a failed review can't loop the same
    day; SM-2 already reschedules failures for tomorrow.
    """
    due: list[ReviewItem] = []
    upcoming: list[ReviewItem] = []
    for ctx in contexts:
        card = cards.get(ctx.skill.id)
        if card is None:
            continue
        reviewed_today = card.last_reviewed_at is not None and card.last_reviewed_at.date() == now.date()
        overdue = max(0, (now - card.due_at).days)
        weakness = 5 - STATE_RANK[state_of(snaps.get(ctx.skill.id))]
        item = ReviewItem(
            skill=ctx.skill,
            card=card,
            overdue_days=overdue,
            needs_relearning=card.consecutive_lapses >= RELEARN_AFTER_LAPSES,
            priority=min(overdue, 14) * 2 + weakness * 3 + card.lapses * 2,
        )
        if card.due_at <= now and not reviewed_today:
            due.append(item)
        elif now < card.due_at <= now + timedelta(days=7):
            upcoming.append(item)
    due.sort(key=lambda i: (-i.priority, i.skill.position))
    upcoming.sort(key=lambda i: i.card.due_at)
    return due[:DAILY_REVIEW_LIMIT], upcoming, len(due)


# ---------------------------------------------------------------- gaps


@dataclass
class Gap:
    kind: str  # recurring_misconception | missing_prerequisite | inconsistent | repeated_failure | missing_concept
    skill: Skill
    title: str
    detail: str
    occurrences: int
    last_seen: datetime | None
    related_skill: Skill | None = None
    evidence: list[str] | None = None


async def detect_gaps(
    db: AsyncSession, learner_id: uuid.UUID, contexts: list[SkillContext], now: datetime
) -> list[Gap]:
    by_id = {c.skill.id: c for c in contexts}
    by_slug = {c.skill.slug: c for c in contexts}
    snaps = await snapshots_for(db, learner_id)
    gaps: list[Gap] = []

    # 1. Recurring misconceptions (from evaluations, with the learner's words).
    events = (
        await db.scalars(
            select(MisconceptionEvent)
            .where(MisconceptionEvent.learner_id == learner_id)
            .order_by(MisconceptionEvent.created_at)
        )
    ).all()
    grouped: dict[tuple[int, str], list[MisconceptionEvent]] = defaultdict(list)
    for m in events:
        grouped[(m.skill_id, (m.known_misconception or m.description).strip().lower())].append(m)
    for (skill_id, _), items in grouped.items():
        if len(items) >= RECURRING_THRESHOLD and skill_id in by_id:
            gaps.append(Gap(
                "recurring_misconception", by_id[skill_id].skill,
                items[-1].known_misconception or items[-1].description,
                f"Appeared in {len(items)} separate evaluations.",
                len(items), items[-1].created_at,
                evidence=[m.quote for m in items if m.quote][:3],
            ))

    evidence = (
        await db.scalars(
            select(MasteryEvidence)
            .where(MasteryEvidence.learner_id == learner_id)
            .order_by(MasteryEvidence.observed_at)
        )
    ).all()
    recent_cutoff = now - timedelta(days=RECENT_DAYS)
    by_skill: dict[int, list[MasteryEvidence]] = defaultdict(list)
    for e in evidence:
        by_skill[e.skill_id].append(e)

    qids = {e.question_id for e in evidence if e.question_id is not None}
    question_titles = {
        q.id: q for q in (await db.scalars(select(Question).where(Question.id.in_(qids)))).all()
    } if qids else {}
    cids = {e.coding_challenge_id for e in evidence if e.coding_challenge_id is not None}
    challenge_info = {
        ch.id: (ch.current_version.title, list(ch.current_version.misconceptions))
        for ch in (await db.scalars(
            select(CodingChallenge).where(CodingChallenge.id.in_(cids))
            .options(selectinload(CodingChallenge.current_version))
        )).all()
        if ch.current_version is not None
    } if cids else {}

    for skill_id, items in by_skill.items():
        ctx = by_id.get(skill_id)
        if ctx is None:
            continue
        failures = [e for e in items if not e.success and e.observed_at >= recent_cutoff]

        # 2. Missing prerequisites behind recent failures.
        if failures:
            for prereq_slug in ctx.prerequisites:
                p = by_slug[prereq_slug]
                if p.assessable and STATE_RANK[state_of(snaps.get(p.skill.id))] < STATE_RANK[MasteryState.DEVELOPING]:
                    gaps.append(Gap(
                        "missing_prerequisite", ctx.skill, f"{p.skill.title} not yet demonstrated",
                        f"{len(failures)} recent miss(es) in {ctx.skill.title}; its prerequisite "
                        f"{p.skill.title} has no demonstrated level.",
                        len(failures), failures[-1].observed_at, related_skill=p.skill,
                    ))

        # 3. Inconsistent performance at one level.
        per_level: dict[Difficulty, list[MasteryEvidence]] = defaultdict(list)
        for e in items:
            per_level[e.difficulty].append(e)
        for level, level_items in per_level.items():
            last = level_items[-4:]
            if len(last) == 4 and sum(e.success for e in last) >= 2 and sum(not e.success for e in last) >= 2:
                gaps.append(Gap(
                    "inconsistent", ctx.skill, f"Inconsistent at {level.value} level",
                    "Your last four attempts at this level were split between successes and misses.",
                    4, last[-1].observed_at,
                ))

        # 4. Repeatedly missed questions (misunderstood concepts).
        misses = Counter(e.question_id for e in items if not e.success and e.question_id is not None)
        for qid, n in misses.items():
            if n >= RECURRING_THRESHOLD and qid in question_titles:
                q = question_titles[qid]
                gaps.append(Gap(
                    "repeated_failure", ctx.skill, q.title,
                    "Missed on " + str(n) + " attempts. Concepts: " + ", ".join(q.expected_concepts[:3]) + ".",
                    n, max(e.observed_at for e in items if e.question_id == qid),
                ))
        # ...and repeatedly failed coding challenges (verified test outcomes).
        coding_misses = Counter(e.coding_challenge_id for e in items if not e.success and e.coding_challenge_id)
        for cid, n in coding_misses.items():
            if n >= RECURRING_THRESHOLD and cid in challenge_info:
                title, misconceptions = challenge_info[cid]
                gaps.append(Gap(
                    "repeated_failure", ctx.skill, title,
                    f"Hidden tests failed on {n} submissions. Common misconception: {misconceptions[0]}",
                    n, max(e.observed_at for e in items if e.coding_challenge_id == cid),
                ))

    # 5. Concepts the grader repeatedly found missing.
    rows = await db.execute(
        select(Question.skill_id, InterviewEvaluation.missing_concepts, InterviewEvaluation.created_at)
        .join(InterviewChallenge, InterviewChallenge.id == InterviewEvaluation.challenge_id)
        .join(InterviewSession, InterviewSession.id == InterviewChallenge.session_id)
        .join(Question, Question.id == InterviewChallenge.question_id)
        .where(
            InterviewSession.learner_id == learner_id,
            InterviewEvaluation.status == InterviewEvaluationStatus.EVALUATED,
            InterviewEvaluation.mastery_eligible,
        )
    )
    concepts: dict[tuple[int, str], list[datetime]] = defaultdict(list)
    for skill_id, missing, created in rows:
        for c in missing or []:
            concepts[(skill_id, str(c).strip().lower())].append(created)
    for (skill_id, concept), seen in concepts.items():
        if len(seen) >= RECURRING_THRESHOLD and skill_id in by_id:
            gaps.append(Gap(
                "missing_concept", by_id[skill_id].skill, concept,
                f"Flagged as missing in {len(seen)} AI evaluations (unverified).",
                len(seen), max(seen),
            ))

    order = {"recurring_misconception": 0, "missing_prerequisite": 1, "repeated_failure": 2,
             "inconsistent": 3, "missing_concept": 4}
    gaps.sort(key=lambda g: (order[g.kind], -g.occurrences, g.skill.position))
    return gaps


# ---------------------------------------------------------------- recommendations


@dataclass
class Activity:
    type: str  # assessment | interview | coding
    skill_slug: str
    difficulty: Difficulty
    mode: InterviewMode | None = None
    challenge_slug: str | None = None


@dataclass
class CodingProgress:
    """Per-learner coding history used for recommendations."""

    solved: set[str] = field(default_factory=set)
    # slug -> (passed, total, failed submissions) for unsolved, attempted challenges
    failing: dict[str, tuple[int, int, int]] = field(default_factory=dict)


@dataclass
class Recommendation:
    key: str
    kind: str  # review | relearn | remediate | prerequisite | practice | advance | start
    skill: Skill
    activity: Activity
    priority: float
    reasons: list[str]


def _activity(
    ctx: SkillContext,
    level: Difficulty,
    *,
    prefer_interview: InterviewMode | None = None,
    solved: set[str] | None = None,
) -> Activity:
    if prefer_interview is None and level in ctx.verifiable_levels:
        # Verified evidence first: objective questions, else a coding challenge.
        if ctx.question_counts.get(level, 0) and level in ctx.objective_levels:
            return Activity("assessment", ctx.skill.slug, level)
        challenge = next(
            (c for c in ctx.challenges if c.difficulty is level and c.slug not in (solved or set())),
            next((c for c in ctx.challenges if c.difficulty is level), None),
        )
        if challenge is not None:
            return Activity("coding", ctx.skill.slug, level, challenge_slug=challenge.slug)
    if sum(ctx.question_counts.values()) == 0 and ctx.challenges:
        # Skills taught only through coding challenges.
        challenge = min(ctx.challenges, key=lambda c: abs(LEVELS.index(c.difficulty) - LEVELS.index(level)))
        return Activity("coding", ctx.skill.slug, challenge.difficulty, challenge_slug=challenge.slug)
    if ctx.question_counts.get(level, 0) == 0:
        # Fall back to the nearest level that has content.
        level = next((lvl for lvl in LEVELS if ctx.question_counts.get(lvl, 0) > 0), level)
    mode = prefer_interview or (
        InterviewMode.ARCHITECT if ctx.skill.slug == "system-design" else InterviewMode.GRILL
        if level is Difficulty.ADVANCED else InterviewMode.TUTOR
    )
    return Activity("interview", ctx.skill.slug, level, mode)


def _next_level(level: Difficulty | None) -> Difficulty | None:
    if level is None:
        return Difficulty.BEGINNER
    i = LEVELS.index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


def recommend(
    contexts: list[SkillContext],
    edges: dict[str, list[str]],
    snaps: dict[int, SkillMastery],
    cards: dict[int, ReviewCard],
    gaps: list[Gap],
    goals: dict[int, Difficulty],
    now: datetime,
    limit: int = 6,
    coding: CodingProgress | None = None,
) -> list[Recommendation]:
    """Ranks one activity per skill; every recommendation carries its reasons."""
    coding = coding or CodingProgress()
    by_slug = {c.skill.slug: c for c in contexts}
    topo = {slug: i for i, slug in enumerate(topological_order(edges))}
    goal_slugs = {c.skill.slug for c in contexts if c.skill.id in goals}
    on_goal_path = set(goal_slugs)
    for g in goal_slugs:
        on_goal_path |= ancestors(edges, g)
    gaps_by_skill: dict[int, list[Gap]] = defaultdict(list)
    for g in gaps:
        gaps_by_skill[g.skill.id].append(g)
    due, _, _ = review_queue(contexts, cards, snaps, now)
    due_ids = {i.skill.id: i for i in due}

    def unmet_prereqs(ctx: SkillContext) -> list[SkillContext]:
        return [
            by_slug[p] for p in ctx.prerequisites
            if by_slug[p].assessable
            and STATE_RANK[state_of(snaps.get(by_slug[p].skill.id))] < STATE_RANK[MasteryState.DEVELOPING]
        ]

    def boost(ctx: SkillContext, reasons: list[str]) -> float:
        if ctx.skill.slug in goal_slugs:
            reasons.append("It's one of your goals.")
            return 20
        if ctx.skill.slug in on_goal_path:
            reasons.append("It's on the path to one of your goals.")
            return 12
        return 0

    candidates: dict[str, Recommendation] = {}

    def offer(rec: Recommendation) -> None:
        current = candidates.get(rec.skill.slug)
        if current is None or rec.priority > current.priority:
            candidates[rec.skill.slug] = rec

    for ctx in contexts:
        if not ctx.assessable:
            continue
        snap = snaps.get(ctx.skill.id)
        state = state_of(snap)
        level = snap.demonstrated_level if snap else None
        skill_gaps = gaps_by_skill.get(ctx.skill.id, [])
        unassessable = [by_slug[p].skill.title for p in ctx.prerequisites if not by_slug[p].assessable]

        # Review due (spaced repetition).
        if ctx.skill.id in due_ids:
            item = due_ids[ctx.skill.id]
            reasons = [
                f"Review due{' ' + str(item.overdue_days) + ' day(s) ago' if item.overdue_days else ' today'} "
                f"(interval {item.card.interval_days} day(s))."
            ]
            if item.needs_relearning:
                reasons.append(f"{item.card.consecutive_lapses} reviews in a row were missed, so relearn with guidance.")
                act = _activity(ctx, level or Difficulty.BEGINNER, prefer_interview=InterviewMode.TUTOR)
                kind = "relearn"
            else:
                act = _activity(ctx, level or Difficulty.BEGINNER)
                kind = "review"
            offer(Recommendation(f"{kind}:{ctx.skill.slug}", kind, ctx.skill, act,
                                 80 + item.priority + boost(ctx, reasons), reasons))

        # Remediation, or a prerequisite first if one is missing.
        prereq_gaps = [g for g in skill_gaps if g.kind == "missing_prerequisite" and g.related_skill]
        if prereq_gaps:
            p = by_slug[prereq_gaps[0].related_skill.slug]
            p_level = _next_level(snaps[p.skill.id].demonstrated_level if p.skill.id in snaps else None) or Difficulty.BEGINNER
            reasons = [
                f"Recent misses in {ctx.skill.title} point to {p.skill.title}, a prerequisite "
                "you haven't demonstrated yet.",
                "Strengthening fundamentals first prevents repeated failures.",
            ]
            offer(Recommendation(f"prerequisite:{p.skill.slug}", "prerequisite", p.skill,
                                 _activity(p, p_level), 75 + boost(p, reasons), reasons))
        other = [g for g in skill_gaps if g.kind != "missing_prerequisite"]
        if other:
            g = other[0]
            reasons = [f"Knowledge gap: {g.title} ({g.detail})"]
            offer(Recommendation(f"remediate:{ctx.skill.slug}", "remediate", ctx.skill,
                                 _activity(ctx, level or Difficulty.BEGINNER, prefer_interview=InterviewMode.TUTOR),
                                 70 + min(g.occurrences, 5) * 2 + boost(ctx, reasons), reasons))

        # Progression.
        missing = unmet_prereqs(ctx)
        if state is MasteryState.NOT_STARTED:
            if missing:
                continue  # locked; surfaced via prerequisite recommendations and the graph
            reasons = ["You haven't started this skill."]
            if ctx.prerequisites:
                reasons.append("Prerequisites are in place" + (
                    f" ({', '.join(unassessable)} has no assessments yet, so it doesn't block)." if unassessable else "."
                ))
            else:
                reasons.append("It has no prerequisites.")
            offer(Recommendation(f"start:{ctx.skill.slug}", "start", ctx.skill,
                                 _activity(ctx, Difficulty.BEGINNER),
                                 40 + boost(ctx, reasons) - topo.get(ctx.skill.slug, 0) * 0.5, reasons))
        elif state in (MasteryState.INSUFFICIENT_EVIDENCE, MasteryState.LEARNING):
            target = _next_level(level) or Difficulty.BEGINNER
            reasons = [snap.reasons[0] if snap and snap.reasons else "More evidence is needed."]
            offer(Recommendation(f"practice:{ctx.skill.slug}", "practice", ctx.skill,
                                 _activity(ctx, target), 55 + boost(ctx, reasons), reasons))
        elif state is not MasteryState.MASTERED:
            target = _next_level(level)
            if target is None:
                continue
            recent_fail = any(g.kind in ("repeated_failure", "inconsistent") for g in skill_gaps)
            if recent_fail:
                continue  # remediation takes precedence over advancing
            goal_level = goals.get(ctx.skill.id)
            reasons = [f"{level.value.capitalize() if level else 'No'} level demonstrated; next is {target.value}."]
            if goal_level and LEVELS.index(target) > LEVELS.index(goal_level):
                continue  # goal already reached
            offer(Recommendation(f"advance:{ctx.skill.slug}", "advance", ctx.skill,
                                 _activity(ctx, target), 50 + boost(ctx, reasons), reasons))

    # Coding: retry failed challenges; add verified practice once knowledge is shown.
    def challenge_unlocked(c: CodingInfo) -> bool:
        return all(
            not by_slug[p].assessable
            or STATE_RANK[state_of(snaps.get(by_slug[p].skill.id))] >= STATE_RANK[MasteryState.DEVELOPING]
            for p in c.prerequisites if p in by_slug
        )

    for ctx in contexts:
        for c in ctx.challenges:
            if c.slug in coding.failing:
                passed, total, attempts = coding.failing[c.slug]
                reasons = [
                    f"Your last submission of “{c.title}” passed {passed} of {total} hidden tests.",
                    "Failed tests point to a specific misconception; fix it while it's fresh.",
                ]
                if attempts >= 3:
                    reasons.append("After several attempts, use a hint or review the related skill first.")
                offer(Recommendation(f"coding-retry:{c.slug}", "practical_retry", ctx.skill,
                                     Activity("coding", ctx.skill.slug, c.difficulty, challenge_slug=c.slug),
                                     66 + boost(ctx, reasons), reasons))
        snap = snaps.get(ctx.skill.id)
        state = state_of(snap)
        if STATE_RANK[state] < STATE_RANK[MasteryState.DEVELOPING] or not ctx.challenges:
            continue
        level = snap.demonstrated_level if snap else None
        ceiling = _next_level(level) or Difficulty.ADVANCED
        pool = [
            c for c in ctx.challenges
            if c.slug not in coding.solved and c.slug not in coding.failing
            and LEVELS.index(c.difficulty) <= LEVELS.index(ceiling) and challenge_unlocked(c)
        ]
        if pool:
            c = min(pool, key=lambda x: LEVELS.index(x.difficulty))
            reasons = [
                f"You've shown {ctx.skill.title} knowledge; “{c.title}” turns it into verified practice.",
                "Hidden tests run in the sandbox count as verified practical evidence.",
            ]
            offer(Recommendation(f"coding:{c.slug}", "practical", ctx.skill,
                                 Activity("coding", ctx.skill.slug, c.difficulty, challenge_slug=c.slug),
                                 52 + boost(ctx, reasons), reasons))

    # Goals whose path is blocked: recommend the first unmet prerequisite.
    for slug in goal_slugs:
        ctx = by_slug[slug]
        for p_slug in sorted(ancestors(edges, slug), key=lambda s: topo[s]):
            p = by_slug[p_slug]
            if p.assessable and state_of(snaps.get(p.skill.id)) is MasteryState.NOT_STARTED and not unmet_prereqs(p):
                reasons = [f"First unmet step towards your goal: {ctx.skill.title}."]
                offer(Recommendation(f"start:{p.skill.slug}", "start", p.skill,
                                     _activity(p, Difficulty.BEGINNER), 62, reasons))
                break

    ranked = sorted(candidates.values(), key=lambda r: (-r.priority, topo.get(r.skill.slug, 0)))
    return ranked[:limit]


async def goals_for(db: AsyncSession, learner_id: uuid.UUID) -> dict[int, Difficulty]:
    return {
        g.skill_id: g.target_level
        for g in (await db.scalars(select(LearnerGoal).where(LearnerGoal.learner_id == learner_id))).all()
    }


async def coding_progress(db: AsyncSession, learner_id: uuid.UUID) -> CodingProgress:
    """Solved challenges, and unsolved ones whose latest executed submission failed."""
    rows = (
        await db.execute(
            select(CodingSubmission, CodingChallenge.slug)
            .join(CodingChallenge, CodingChallenge.id == CodingSubmission.challenge_id)
            .where(CodingSubmission.learner_id == learner_id, CodingSubmission.executed)
            .order_by(CodingSubmission.created_at)
        )
    ).all()
    progress = CodingProgress()
    attempts: Counter = Counter()
    latest: dict[str, CodingSubmission] = {}
    for sub, slug in rows:
        if sub.all_passed:
            progress.solved.add(slug)
        else:
            attempts[slug] += 1
        latest[slug] = sub
    for slug, sub in latest.items():
        if slug not in progress.solved and not sub.all_passed:
            progress.failing[slug] = (sub.passed, sub.total, attempts[slug])
    return progress
