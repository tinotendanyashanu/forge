"""Interview session engine: the Socratic loop.

Flow per challenge: question → answer → (follow-up → answer)* → feedback + reveal.
Hints and "I don't know" are available according to the mode policy.

Transactions: learner actions are committed before any model call; the model
runs outside a transaction; its result is applied in a second transaction that
re-locks the session. A crash in between leaves a *pending* evaluation that
can be retried; the learner's answer is never lost.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.enums import (
    ChallengeStatus,
    Difficulty,
    InterviewEvaluationStatus,
    InterviewMode,
    InterviewStatus,
    TurnKind,
    TurnRole,
)
from app.db.models import (
    Answer,
    InterviewChallenge,
    InterviewEvaluation,
    InterviewSession,
    InterviewTurn,
    Learner,
    MisconceptionEvent,
    Question,
    Skill,
)
from app.interview.evaluation import (
    PROMPT_VERSION,
    EvaluationOutcome,
    evaluate_answer,
    leaks_reference,
)
from app.llm.base import LLMProvider
from app.schemas.assessments import ResourceOut
from app.schemas.content import SkillRef, TopicRef
from app.schemas.interviews import (
    ChallengeOut,
    ChallengeQuestion,
    ChallengeSummary,
    CriterionOut,
    EvaluationBrief,
    EvaluationFull,
    InterviewCreate,
    InterviewSessionOut,
    InterviewState,
    InterviewSummary,
    MisconceptionOut,
    Reveal,
    TurnOut,
)
from app.services.errors import Conflict, DomainError, NotFound, Unprocessable

MAX_HINTS = 3
STALE_PENDING_AFTER = timedelta(minutes=5)


class InterviewRateLimited(DomainError):
    status_code = 429
DIFFICULTY_ORDER = [Difficulty.BEGINNER, Difficulty.INTERMEDIATE, Difficulty.ADVANCED]
RETRYABLE_ERRORS = {
    "provider_unavailable",
    "provider_timeout",
    "provider_rate_limited",
    "malformed_output",
    "provider_not_configured",
    "provider_rejected",
    "interrupted",
}


@dataclass(frozen=True)
class ModePolicy:
    pass_threshold: Decimal
    max_follow_ups: int
    hints_before_first_attempt: bool
    dont_know_gives_hint: bool


POLICIES: dict[InterviewMode, ModePolicy] = {
    InterviewMode.TUTOR: ModePolicy(Decimal("0.7"), 2, True, True),
    InterviewMode.GRILL: ModePolicy(Decimal("0.8"), 1, False, False),
    InterviewMode.DEBUG: ModePolicy(Decimal("0.7"), 2, True, True),
    InterviewMode.ARCHITECT: ModePolicy(Decimal("0.7"), 2, True, True),
}

GENERIC_FOLLOW_UP = (
    "Your answer isn't complete yet. Before I share the reference explanation: what is the "
    "precise mechanism behind your answer, and what case would break it?"
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- loading


def _question_options():
    return (
        selectinload(InterviewChallenge.question).selectinload(Question.options),
        selectinload(InterviewChallenge.question).selectinload(Question.rubric),
        selectinload(InterviewChallenge.question).selectinload(Question.resources),
        selectinload(InterviewChallenge.question).selectinload(Question.topic),
    )


async def _load_session(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, *, lock: bool = False
) -> InterviewSession:
    stmt = (
        select(InterviewSession)
        .where(InterviewSession.id == session_id, InterviewSession.learner_id == learner.id)
        .options(selectinload(InterviewSession.skill))
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(of=InterviewSession)
    session = await db.scalar(stmt)
    if session is None:
        raise NotFound("Interview not found")
    return session


async def _current_challenge(db: AsyncSession, session_id: uuid.UUID) -> InterviewChallenge | None:
    return await db.scalar(
        select(InterviewChallenge)
        .where(InterviewChallenge.session_id == session_id)
        .options(*_question_options(), selectinload(InterviewChallenge.evaluations))
        .order_by(InterviewChallenge.position.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )


async def _next_seq(db: AsyncSession, session_id: uuid.UUID) -> int:
    current = await db.scalar(
        select(func.max(InterviewTurn.seq)).where(InterviewTurn.session_id == session_id)
    )
    return (current or 0) + 1


async def _add_turn(
    db: AsyncSession,
    session: InterviewSession,
    *,
    role: TurnRole,
    kind: TurnKind,
    content: str,
    challenge: InterviewChallenge | None,
    client_turn_id: uuid.UUID | None = None,
    hint_level: int | None = None,
) -> InterviewTurn:
    turn = InterviewTurn(
        session_id=session.id,
        challenge_id=challenge.id if challenge else None,
        seq=await _next_seq(db, session.id),
        role=role,
        kind=kind,
        content=content[:20_000],
        client_turn_id=client_turn_id,
        hint_level=hint_level,
    )
    db.add(turn)
    await db.flush()
    return turn


async def _seen_client_turn(db: AsyncSession, session_id: uuid.UUID, client_turn_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(InterviewTurn.id).where(
                InterviewTurn.session_id == session_id,
                InterviewTurn.client_turn_id == client_turn_id,
            )
        )
    ) is not None


# ---------------------------------------------------------------- question selection


def _question_turn_text(q: Question) -> str:
    code = f"\n\n```{q.code_language or ''}\n{q.code}\n```" if q.code else ""
    return f"{q.prompt}{code}"


async def _pick_question(
    db: AsyncSession, session: InterviewSession, difficulty: Difficulty
) -> Question | None:
    """Unseen-in-session questions only; then never-seen by this learner first,
    then least recently seen; mode preferences break ties deterministically."""
    in_session = select(InterviewChallenge.question_id).where(
        InterviewChallenge.session_id == session.id
    )
    last_interview = (
        select(InterviewChallenge.question_id, func.max(InterviewChallenge.started_at).label("seen"))
        .join(InterviewSession, InterviewSession.id == InterviewChallenge.session_id)
        .where(InterviewSession.learner_id == session.learner_id)
        .group_by(InterviewChallenge.question_id)
        .subquery()
    )
    last_assessment = (
        select(Answer.question_id, func.max(Answer.submitted_at).label("seen"))
        .where(Answer.learner_id == session.learner_id)
        .group_by(Answer.question_id)
        .subquery()
    )
    last_seen = func.greatest(last_interview.c.seen, last_assessment.c.seen)

    mode_pref = {
        InterviewMode.DEBUG: Question.code.is_(None),  # code-based questions first
        InterviewMode.ARCHITECT: Question.code.is_not(None),  # open design first
    }.get(session.mode)

    order = [last_seen.is_not(None), last_seen.asc().nulls_first()]
    if mode_pref is not None:
        order.append(mode_pref)
    order += [Question.position, Question.id]

    return await db.scalar(
        select(Question)
        .outerjoin(last_interview, last_interview.c.question_id == Question.id)
        .outerjoin(last_assessment, last_assessment.c.question_id == Question.id)
        .where(
            Question.skill_id == session.skill_id,
            Question.difficulty == difficulty,
            Question.is_active,
            Question.id.not_in(in_session),
        )
        .order_by(*order)
        .limit(1)
    )


async def _pick_with_fallback(db: AsyncSession, session: InterviewSession) -> Question | None:
    """Try the current difficulty, then the nearest others."""
    idx = DIFFICULTY_ORDER.index(session.current_difficulty)
    order = sorted(range(len(DIFFICULTY_ORDER)), key=lambda i: (abs(i - idx), i))
    for i in order:
        q = await _pick_question(db, session, DIFFICULTY_ORDER[i])
        if q is not None:
            return q
    return None


def adapt_difficulty(current: Difficulty, recent: list[InterviewChallenge]) -> Difficulty:
    """Adjusts difficulty from the most recent finished challenges, newest first.

    Uses evidence quality, not an average: two consecutive clean passes (no
    hints, no follow-ups, observed score ≥ 0.8) step up; a skip, an "I don't
    know", or a low observed score on the latest challenge steps down.
    Ungraded challenges carry no evidence and don't move difficulty.
    """
    idx = DIFFICULTY_ORDER.index(current)
    if not recent:
        return current
    latest = recent[0]
    latest_eval = _final_evaluation(latest)
    weak = (
        latest.status is ChallengeStatus.SKIPPED
        or (latest.said_dont_know and (latest_eval is None or (latest_eval.total_score or 0) < Decimal("0.5")))
        or (latest_eval is not None and latest_eval.total_score is not None and latest_eval.total_score < Decimal("0.4"))
    )
    if weak:
        return DIFFICULTY_ORDER[max(0, idx - 1)]

    def clean(c: InterviewChallenge) -> bool:
        e = _final_evaluation(c)
        return (
            c.status is ChallengeStatus.COMPLETED
            and e is not None
            and e.total_score is not None
            and e.total_score >= Decimal("0.8")
            and c.hints_used == 0
            and c.follow_ups_asked == 0
            and not c.said_dont_know
        )

    if len(recent) >= 2 and clean(recent[0]) and clean(recent[1]):
        return DIFFICULTY_ORDER[min(len(DIFFICULTY_ORDER) - 1, idx + 1)]
    return current


def _final_evaluation(challenge: InterviewChallenge) -> InterviewEvaluation | None:
    evaluated = [e for e in challenge.evaluations if e.status is InterviewEvaluationStatus.EVALUATED]
    return evaluated[-1] if evaluated else None


async def _serve_next(
    db: AsyncSession, session: InterviewSession, client_turn_id: uuid.UUID | None
) -> InterviewChallenge | None:
    finished = await db.scalar(
        select(func.count()).select_from(InterviewChallenge).where(
            InterviewChallenge.session_id == session.id
        )
    ) or 0
    if finished >= session.target_challenge_count:
        _complete_session(session)
        return None
    question = await _pick_with_fallback(db, session)
    if question is None:
        _complete_session(session)
        return None
    challenge = InterviewChallenge(
        session_id=session.id,
        question_id=question.id,
        position=finished + 1,
        difficulty=question.difficulty,
        status=ChallengeStatus.OPEN,
    )
    db.add(challenge)
    await db.flush()
    await _add_turn(
        db,
        session,
        role=TurnRole.INTERVIEWER,
        kind=TurnKind.QUESTION,
        content=_question_turn_text(question),
        challenge=challenge,
        client_turn_id=client_turn_id,
    )
    return challenge


def _complete_session(session: InterviewSession) -> None:
    session.status = InterviewStatus.COMPLETED
    session.completed_at = _now()


def _finish_challenge(challenge: InterviewChallenge, status: ChallengeStatus) -> None:
    challenge.status = status
    challenge.completed_at = _now()


# ---------------------------------------------------------------- public operations


async def start_interview(
    db: AsyncSession,
    learner: Learner,
    payload: InterviewCreate,
    provider: LLMProvider,
) -> InterviewState:
    skill = await db.scalar(select(Skill).where(Skill.slug == payload.skill_slug))
    if skill is None:
        raise NotFound(f"Skill '{payload.skill_slug}' not found")
    available = await db.scalar(
        select(func.count()).select_from(Question).where(Question.skill_id == skill.id, Question.is_active)
    ) or 0
    if available == 0:
        raise Unprocessable(f"No questions are available for {skill.title} yet")

    session = InterviewSession(
        learner_id=learner.id,
        skill_id=skill.id,
        mode=payload.mode,
        start_difficulty=payload.difficulty,
        current_difficulty=payload.difficulty,
        status=InterviewStatus.ACTIVE,
        target_challenge_count=min(payload.challenge_count, available),
        provider=getattr(provider, "name", "unknown"),
        model=getattr(provider, "model", "unknown"),
    )
    session.skill = skill
    db.add(session)
    await db.flush()
    await _serve_next(db, session, None)
    await db.commit()
    return await get_state(db, learner, session.id)


async def list_interviews(db: AsyncSession, learner: Learner, limit: int) -> list[InterviewSessionOut]:
    sessions = (
        await db.scalars(
            select(InterviewSession)
            .where(InterviewSession.learner_id == learner.id)
            .options(selectinload(InterviewSession.skill), selectinload(InterviewSession.challenges))
            .order_by(InterviewSession.started_at.desc())
            .limit(limit)
        )
    ).all()
    return [_session_out(s, s.challenges) for s in sessions]


async def _check_interview_budget(db: AsyncSession, settings: Settings, learner: Learner) -> None:
    """Per-learner cap on model evaluations (each answer or retry is one model call)."""
    since = _now() - timedelta(hours=1)
    used = await db.scalar(
        select(func.count()).select_from(InterviewEvaluation)
        .join(InterviewChallenge, InterviewChallenge.id == InterviewEvaluation.challenge_id)
        .join(InterviewSession, InterviewSession.id == InterviewChallenge.session_id)
        .where(InterviewSession.learner_id == learner.id,
               or_(InterviewEvaluation.created_at > since, InterviewEvaluation.completed_at > since))
    ) or 0
    if used >= settings.interview_llm_calls_per_hour:
        raise InterviewRateLimited("AI evaluation limit reached for this hour. Try again later.")


async def submit_answer(
    db: AsyncSession,
    settings: Settings,
    provider: LLMProvider,
    learner: Learner,
    session_id: uuid.UUID,
    client_turn_id: uuid.UUID,
    content: str,
) -> InterviewState:
    # Phase 1: persist the answer and a pending evaluation.
    session = await _load_session(db, learner, session_id, lock=True)
    if await _seen_client_turn(db, session.id, client_turn_id):
        await db.commit()
        return await get_state(db, learner, session.id)
    challenge = await _require_open_challenge(db, session)
    await _check_interview_budget(db, settings, learner)

    turn = await _add_turn(
        db, session, role=TurnRole.LEARNER, kind=TurnKind.ANSWER, content=content,
        challenge=challenge, client_turn_id=client_turn_id,
    )
    challenge.attempts += 1
    evaluation = InterviewEvaluation(
        challenge_id=challenge.id,
        answer_turn_id=turn.id,
        status=InterviewEvaluationStatus.PENDING,
        provider=getattr(provider, "name", "unknown"),
        model=getattr(provider, "model", "unknown"),
        prompt_version=PROMPT_VERSION,
    )
    db.add(evaluation)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent duplicate with the same client_turn_id won the race.
        await db.rollback()
        return await get_state(db, learner, session_id)

    await _run_evaluation(db, settings, provider, learner, session_id, evaluation.id)
    return await get_state(db, learner, session_id)


async def retry_evaluation(
    db: AsyncSession,
    settings: Settings,
    provider: LLMProvider,
    learner: Learner,
    session_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> InterviewState:
    session = await _load_session(db, learner, session_id, lock=True)
    evaluation = await db.scalar(
        select(InterviewEvaluation)
        .join(InterviewChallenge, InterviewChallenge.id == InterviewEvaluation.challenge_id)
        .where(InterviewEvaluation.id == evaluation_id, InterviewChallenge.session_id == session.id)
    )
    if evaluation is None:
        raise NotFound("Evaluation not found")
    stale = (
        evaluation.status is InterviewEvaluationStatus.PENDING
        and evaluation.created_at < _now() - STALE_PENDING_AFTER
    )
    if evaluation.status is InterviewEvaluationStatus.EVALUATED:
        await db.commit()
        return await get_state(db, learner, session_id)
    if evaluation.status is InterviewEvaluationStatus.PENDING and not stale:
        raise Conflict("This answer is still being evaluated")
    await _check_interview_budget(db, settings, learner)
    challenge = await db.get(InterviewChallenge, evaluation.challenge_id)
    if challenge is None or challenge.status is not ChallengeStatus.OPEN:
        raise Conflict("This challenge is already finished")
    evaluation.status = InterviewEvaluationStatus.PENDING
    evaluation.error_code = None
    evaluation.provider = getattr(provider, "name", "unknown")
    evaluation.model = getattr(provider, "model", "unknown")
    await db.commit()
    await _run_evaluation(db, settings, provider, learner, session_id, evaluation.id)
    return await get_state(db, learner, session_id)


async def _run_evaluation(
    db: AsyncSession,
    settings: Settings,
    provider: LLMProvider,
    learner: Learner,
    session_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> None:
    # Phase 2: call the model outside any transaction or lock.
    evaluation = await db.get(InterviewEvaluation, evaluation_id, populate_existing=True)
    assert evaluation is not None
    challenge = await db.scalar(
        select(InterviewChallenge)
        .where(InterviewChallenge.id == evaluation.challenge_id)
        .options(*_question_options())
    )
    assert challenge is not None
    session = await db.get(InterviewSession, session_id)
    assert session is not None
    exchanges = await _exchanges(db, challenge.id)
    mode = session.mode
    await db.commit()  # end the read transaction before the slow call

    outcome = await evaluate_answer(
        provider,
        question=challenge.question,
        mode=mode,
        exchanges=exchanges,
        max_repair_attempts=settings.llm_max_repair_attempts,
    )

    # Phase 3: apply the result under the session lock.
    session = await _load_session(db, learner, session_id, lock=True)
    evaluation = await db.get(InterviewEvaluation, evaluation_id, populate_existing=True)
    challenge = await db.scalar(
        select(InterviewChallenge)
        .where(InterviewChallenge.id == evaluation.challenge_id)
        .options(*_question_options(), selectinload(InterviewChallenge.evaluations))
        .execution_options(populate_existing=True)
    )
    if evaluation is None or challenge is None or evaluation.status is not InterviewEvaluationStatus.PENDING:
        await db.commit()
        return
    _apply_outcome(evaluation, outcome)

    if not outcome.graded:
        await _add_turn(
            db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.NOTICE, challenge=challenge,
            content=_ungraded_notice(outcome.error_code),
        )
        await db.commit()
        return

    for m in outcome.misconceptions:
        db.add(
            MisconceptionEvent(
                learner_id=session.learner_id,
                skill_id=session.skill_id,
                question_id=challenge.question_id,
                evaluation_id=evaluation.id,
                description=m.description,
                quote=m.quote,
                observed=m.observed,
                known_misconception=m.known_misconception,
            )
        )

    policy = POLICIES[session.mode]
    passed = bool(outcome.answer_complete) and (outcome.total_score or 0) >= policy.pass_threshold
    if passed or challenge.follow_ups_asked >= policy.max_follow_ups:
        _finish_challenge(challenge, ChallengeStatus.COMPLETED)
        await _add_turn(
            db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.FEEDBACK, challenge=challenge,
            content=outcome.feedback or "Here is how a strong answer approaches this.",
        )
    else:
        follow_up = outcome.suggested_follow_up
        if not follow_up or leaks_reference(follow_up, challenge.question):
            follow_up = GENERIC_FOLLOW_UP
        challenge.follow_ups_asked += 1
        await _add_turn(
            db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.FOLLOW_UP, challenge=challenge,
            content=follow_up,
        )
    await db.commit()


def _apply_outcome(e: InterviewEvaluation, o: EvaluationOutcome) -> None:
    e.status = InterviewEvaluationStatus.EVALUATED if o.graded else InterviewEvaluationStatus.UNGRADED
    e.error_code = o.error_code
    e.total_score = o.total_score
    e.model_total_score = o.model_total_score
    e.confidence = o.confidence
    e.answer_complete = o.answer_complete
    e.criterion_scores = [c.as_json() for c in o.criteria]
    e.demonstrated_concepts = o.demonstrated_concepts
    e.missing_concepts = o.missing_concepts
    e.misconceptions = [m.__dict__ for m in o.misconceptions]
    e.feedback = o.feedback
    e.suggested_follow_up = o.suggested_follow_up
    e.injection_suspected = o.injection_suspected
    e.mastery_eligible = o.mastery_eligible
    if o.provider:
        e.provider, e.model = o.provider, o.model
    e.structured_output = o.structured_output
    e.latency_ms = o.latency_ms
    e.llm_attempts = o.llm_attempts
    e.raw_output = o.raw_output
    e.completed_at = _now()


def _ungraded_notice(code: str | None) -> str:
    reason = {
        "provider_not_configured": "AI evaluation isn't configured on this server",
        "provider_unavailable": "the AI model couldn't be reached",
        "provider_timeout": "the AI model took too long to respond",
        "provider_rate_limited": "the AI model is rate limiting requests",
        "provider_rejected": "the AI model rejected the request",
        "malformed_output": "the AI model returned an invalid evaluation",
    }.get(code or "", "the evaluation failed")
    return (
        f"I couldn't evaluate that answer because {reason}. Your answer is saved and has not "
        "been scored. You can retry the evaluation."
    )


async def _exchanges(db: AsyncSession, challenge_id: uuid.UUID) -> list[tuple[str, str]]:
    """(interviewer prompt, learner answer) pairs for grading, in order."""
    turns = (
        await db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.challenge_id == challenge_id)
            .order_by(InterviewTurn.seq)
        )
    ).all()
    pairs: list[tuple[str, str]] = []
    last_prompt = ""
    for t in turns:
        if t.role is TurnRole.INTERVIEWER and t.kind in (TurnKind.QUESTION, TurnKind.FOLLOW_UP):
            last_prompt = t.content
        elif t.kind is TurnKind.ANSWER:
            pairs.append((last_prompt, t.content))
    return pairs


async def _require_open_challenge(db: AsyncSession, session: InterviewSession) -> InterviewChallenge:
    if session.status is InterviewStatus.COMPLETED:
        raise Conflict("This interview is already complete")
    challenge = await _current_challenge(db, session.id)
    if challenge is None or challenge.status is not ChallengeStatus.OPEN:
        raise Conflict("There is no open challenge. Continue to the next one.")
    if any(e.status is InterviewEvaluationStatus.PENDING for e in challenge.evaluations):
        raise Conflict("Your previous answer is still being evaluated")
    return challenge


def _hint_text(challenge: InterviewChallenge, level: int) -> str:
    q = challenge.question
    if level == 1:
        return q.hint or "Restate precisely what the question asks, then reason one step at a time."
    if level == 2:
        concepts = ", ".join(q.expected_concepts[:2])
        return f"Concepts worth thinking about: {concepts}."
    latest = _final_evaluation(challenge)
    covered = {c["criterion_id"] for c in (latest.criterion_scores if latest else []) if c.get("evidence") == "observed"}
    target = next((c for i, c in enumerate(q.rubric, start=1) if i not in covered), q.rubric[0])
    return f"A strong answer needs to address this: {target.criterion}"


async def _give_hint(db: AsyncSession, session: InterviewSession, challenge: InterviewChallenge) -> None:
    challenge.hints_used += 1
    await _add_turn(
        db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.HINT, challenge=challenge,
        content=_hint_text(challenge, challenge.hints_used), hint_level=challenge.hints_used,
    )


def _hint_block_reason(session: InterviewSession, challenge: InterviewChallenge) -> str | None:
    if challenge.status is not ChallengeStatus.OPEN:
        return "This challenge is finished."
    if challenge.hints_used >= MAX_HINTS:
        return "You've used every hint for this challenge."
    if not POLICIES[session.mode].hints_before_first_attempt and challenge.attempts == 0:
        return "Grill mode: attempt the question before asking for a hint."
    return None


async def request_hint(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, client_turn_id: uuid.UUID
) -> InterviewState:
    session = await _load_session(db, learner, session_id, lock=True)
    if not await _seen_client_turn(db, session.id, client_turn_id):
        challenge = await _require_open_challenge(db, session)
        reason = _hint_block_reason(session, challenge)
        if reason:
            raise Conflict(reason)
        await _add_turn(
            db, session, role=TurnRole.LEARNER, kind=TurnKind.HINT_REQUEST, challenge=challenge,
            content="Could I have a hint?", client_turn_id=client_turn_id,
        )
        await _give_hint(db, session, challenge)
    await db.commit()
    return await get_state(db, learner, session_id)


async def dont_know(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, client_turn_id: uuid.UUID
) -> InterviewState:
    session = await _load_session(db, learner, session_id, lock=True)
    if not await _seen_client_turn(db, session.id, client_turn_id):
        challenge = await _require_open_challenge(db, session)
        await _add_turn(
            db, session, role=TurnRole.LEARNER, kind=TurnKind.DONT_KNOW, challenge=challenge,
            content="I don't know.", client_turn_id=client_turn_id,
        )
        challenge.said_dont_know = True
        challenge.attempts += 1
        policy = POLICIES[session.mode]
        if challenge.hints_used >= MAX_HINTS:
            _finish_challenge(challenge, ChallengeStatus.COMPLETED)
            await _add_turn(
                db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.FEEDBACK, challenge=challenge,
                content="That's fine. Not knowing yet is useful information. Let's walk through the reference explanation.",
            )
        elif policy.dont_know_gives_hint:
            await _give_hint(db, session, challenge)
        else:
            await _add_turn(
                db, session, role=TurnRole.INTERVIEWER, kind=TurnKind.NOTICE, challenge=challenge,
                content="Understood. You can ask for a hint now, give it your best attempt, or move on.",
            )
    await db.commit()
    return await get_state(db, learner, session_id)


async def continue_interview(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, client_turn_id: uuid.UUID
) -> InterviewState:
    session = await _load_session(db, learner, session_id, lock=True)
    if await _seen_client_turn(db, session.id, client_turn_id) or session.status is InterviewStatus.COMPLETED:
        await db.commit()
        return await get_state(db, learner, session_id)
    challenge = await _current_challenge(db, session.id)
    if challenge is not None and challenge.status is ChallengeStatus.OPEN:
        if any(e.status is InterviewEvaluationStatus.PENDING for e in challenge.evaluations):
            raise Conflict("Wait for the current evaluation to finish")
        _finish_challenge(challenge, ChallengeStatus.SKIPPED)

    finished = (
        await db.scalars(
            select(InterviewChallenge)
            .where(InterviewChallenge.session_id == session.id)
            .options(selectinload(InterviewChallenge.evaluations))
            .order_by(InterviewChallenge.position.desc())
            .execution_options(populate_existing=True)
        )
    ).all()
    session.current_difficulty = adapt_difficulty(session.current_difficulty, list(finished[:2]))
    await _serve_next(db, session, client_turn_id)
    await db.commit()
    return await get_state(db, learner, session_id)


# ---------------------------------------------------------------- views


def _session_out(session: InterviewSession, challenges: list[InterviewChallenge]) -> InterviewSessionOut:
    return InterviewSessionOut(
        id=session.id,
        skill=SkillRef(slug=session.skill.slug, title=session.skill.title),
        mode=session.mode,
        status=session.status,
        start_difficulty=session.start_difficulty,
        current_difficulty=session.current_difficulty,
        target_challenge_count=session.target_challenge_count,
        challenges_finished=sum(1 for c in challenges if c.status is not ChallengeStatus.OPEN),
        provider=session.provider,
        model=session.model,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


def _brief(e: InterviewEvaluation) -> EvaluationBrief:
    return EvaluationBrief(
        id=e.id,
        status=e.status,
        error_code=e.error_code,
        retryable=e.status is InterviewEvaluationStatus.UNGRADED and (e.error_code in RETRYABLE_ERRORS),
    )


def _full(e: InterviewEvaluation) -> EvaluationFull:
    evaluated = e.status is InterviewEvaluationStatus.EVALUATED
    return EvaluationFull(
        **_brief(e).model_dump(),
        total_score=float(e.total_score) if evaluated and e.total_score is not None else None,
        model_total_score=float(e.model_total_score) if evaluated and e.model_total_score is not None else None,
        confidence=float(e.confidence) if evaluated and e.confidence is not None else None,
        answer_complete=e.answer_complete if evaluated else None,
        criteria=[CriterionOut(**c) for c in e.criterion_scores] if evaluated else [],
        demonstrated_concepts=list(e.demonstrated_concepts) if evaluated else [],
        missing_concepts=list(e.missing_concepts) if evaluated else [],
        misconceptions=[MisconceptionOut(**m) for m in e.misconceptions] if evaluated else [],
        feedback=e.feedback if evaluated else None,
        injection_suspected=e.injection_suspected,
        mastery_eligible=e.mastery_eligible,
        provider=e.provider,
        model=e.model,
        prompt_version=e.prompt_version,
        created_at=e.created_at,
    )


def _reveal(c: InterviewChallenge) -> Reveal:
    q = c.question
    final = _final_evaluation(c)
    return Reveal(
        explanation=q.explanation,
        acceptance_criteria=q.acceptance_criteria,
        rubric=[r.criterion for r in q.rubric],
        expected_concepts=list(q.expected_concepts),
        known_misconceptions=list(q.misconceptions),
        resources=[ResourceOut(title=r.title, url=r.url) for r in q.resources],
        final_evaluation=_full(final) if final else None,
    )


def _challenge_out(session: InterviewSession, c: InterviewChallenge) -> ChallengeOut:
    q = c.question
    reason = _hint_block_reason(session, c)
    return ChallengeOut(
        id=c.id,
        position=c.position,
        status=c.status,
        difficulty=c.difficulty,
        question=ChallengeQuestion(
            slug=q.slug, title=q.title, prompt=q.prompt, code=q.code, code_language=q.code_language,
            format=q.format, difficulty=q.difficulty, estimated_minutes=q.estimated_minutes,
            topic=TopicRef(slug=q.topic.slug, title=q.topic.title),
        ),
        attempts=c.attempts,
        hints_used=c.hints_used,
        max_hints=MAX_HINTS,
        follow_ups_asked=c.follow_ups_asked,
        can_request_hint=reason is None,
        hint_blocked_reason=reason,
        awaiting_evaluation=any(e.status is InterviewEvaluationStatus.PENDING for e in c.evaluations),
        # Hidden reference material only once the challenge is finished.
        reveal=_reveal(c) if c.status is not ChallengeStatus.OPEN else None,
    )


async def get_state(db: AsyncSession, learner: Learner, session_id: uuid.UUID) -> InterviewState:
    session = await _load_session(db, learner, session_id)
    challenges = (
        await db.scalars(
            select(InterviewChallenge)
            .where(InterviewChallenge.session_id == session.id)
            .options(*_question_options(), selectinload(InterviewChallenge.evaluations))
            .order_by(InterviewChallenge.position)
            .execution_options(populate_existing=True)
        )
    ).all()
    turns = (
        await db.scalars(
            select(InterviewTurn).where(InterviewTurn.session_id == session.id).order_by(InterviewTurn.seq)
        )
    ).all()
    status_by_challenge = {c.id: c.status for c in challenges}
    eval_by_turn = {e.answer_turn_id: e for c in challenges for e in c.evaluations}

    def turn_out(t: InterviewTurn) -> TurnOut:
        e = eval_by_turn.get(t.id)
        open_ = status_by_challenge.get(t.challenge_id) is ChallengeStatus.OPEN
        return TurnOut(
            id=t.id, seq=t.seq, challenge_id=t.challenge_id, role=t.role, kind=t.kind,
            content=t.content, hint_level=t.hint_level, created_at=t.created_at,
            evaluation=None if e is None else (_brief(e) if open_ else _full(e)),
        )

    current = challenges[-1] if challenges else None
    await db.commit()
    return InterviewState(
        session=_session_out(session, list(challenges)),
        current_challenge=_challenge_out(session, current) if current else None,
        turns=[turn_out(t) for t in turns],
        can_continue=session.status is InterviewStatus.ACTIVE
        and not (current and any(e.status is InterviewEvaluationStatus.PENDING for e in current.evaluations)),
    )


async def get_summary(db: AsyncSession, learner: Learner, session_id: uuid.UUID) -> InterviewSummary:
    state = await get_state(db, learner, session_id)
    challenges = (
        await db.scalars(
            select(InterviewChallenge)
            .where(InterviewChallenge.session_id == session_id)
            .options(*_question_options(), selectinload(InterviewChallenge.evaluations))
            .order_by(InterviewChallenge.position)
        )
    ).all()
    out: list[ChallengeSummary] = []
    evaluated = ungraded = 0
    misconceptions: list[MisconceptionOut] = []
    for c in challenges:
        final = _final_evaluation(c)
        evaluated += sum(1 for e in c.evaluations if e.status is InterviewEvaluationStatus.EVALUATED)
        ungraded += sum(1 for e in c.evaluations if e.status is InterviewEvaluationStatus.UNGRADED)
        show = c.status is not ChallengeStatus.OPEN
        if final and show:
            misconceptions += [MisconceptionOut(**m) for m in final.misconceptions]
        out.append(
            ChallengeSummary(
                position=c.position, status=c.status, question_title=c.question.title,
                difficulty=c.difficulty, attempts=c.attempts, hints_used=c.hints_used,
                follow_ups_asked=c.follow_ups_asked, said_dont_know=c.said_dont_know,
                final_evaluation=_full(final) if final and show else None,
            )
        )
    notes = [
        "Scores count only rubric criteria backed by a quote verified in your answer.",
        "A single AI-graded interview does not change mastery on its own.",
    ]
    if ungraded:
        notes.append(f"{ungraded} answer(s) could not be evaluated and carry no score.")
    return InterviewSummary(
        session=state.session, challenges=out, evaluated_count=evaluated,
        ungraded_count=ungraded, misconceptions=misconceptions, notes=notes,
    )
