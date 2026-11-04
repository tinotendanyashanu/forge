"""Assessment sessions: starting, serving questions, submitting and feedback."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import EvaluationStatus, QuestionFormat, SessionStatus
from app.db.models import (
    Answer,
    AssessmentSession,
    EvaluationResult,
    Learner,
    Question,
    Skill,
    SessionItem,
    SkillProgress,
    Topic,
)
from app.schemas.assessments import (
    AnswerHistoryItem,
    AnswerSubmit,
    AssessmentCreate,
    AssessmentOut,
    EvaluationOut,
    FeedbackOut,
    NextQuestionCompleted,
    NextQuestionPending,
    OptionReveal,
    ProgressOut,
    ResourceOut,
    SessionItemOut,
    SkillProgressOut,
    SubmittedAnswerOut,
)
from app.schemas.content import SkillRef, TopicRef
from app.services.content import public_question
from app.services.errors import Conflict, InvalidAnswer, NotFound, Unprocessable
from app.services.grading import Evaluation, evaluate, summarise


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- learners


async def create_learner(db: AsyncSession) -> Learner:
    learner = Learner()
    db.add(learner)
    await db.commit()
    return learner


async def get_learner(db: AsyncSession, learner_id: uuid.UUID) -> Learner | None:
    return await db.get(Learner, learner_id)


# ---------------------------------------------------------------- progress counters


async def _record_session_start(db: AsyncSession, learner_id: uuid.UUID, skill_id: int) -> None:
    """Creates the progress row on first use, or increments sessions_started."""
    stmt = pg_insert(SkillProgress).values(
        learner_id=learner_id, skill_id=skill_id, sessions_started=1, last_activity_at=func.now()
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[SkillProgress.learner_id, SkillProgress.skill_id],
        set_={
            "sessions_started": SkillProgress.sessions_started + 1,
            "last_activity_at": func.now(),
        },
    )
    await db.execute(stmt)


async def _bump_progress(
    db: AsyncSession, learner_id: uuid.UUID, skill_id: int, **deltas: int
) -> None:
    """Atomically increments counters on the row created at session start.

    A plain UPDATE (not an upsert): PostgreSQL checks constraints against the
    proposed INSERT row before ON CONFLICT applies, and an increment-only row
    would violate them.
    """
    cols = {k: getattr(SkillProgress, k) + v for k, v in deltas.items() if v}
    result = await db.execute(
        update(SkillProgress)
        .where(SkillProgress.learner_id == learner_id, SkillProgress.skill_id == skill_id)
        .values(**cols, last_activity_at=func.now())
    )
    if result.rowcount != 1:
        raise RuntimeError("Progress row missing; it is created when a session starts")


# ---------------------------------------------------------------- sessions


def _answered_count_subquery():
    return (
        select(func.count(Answer.id))
        .join(SessionItem, SessionItem.id == Answer.session_item_id)
        .where(SessionItem.session_id == AssessmentSession.id)
        .correlate(AssessmentSession)
        .scalar_subquery()
    )


def _session_out(session: AssessmentSession, answered_count: int) -> AssessmentOut:
    return AssessmentOut(
        id=session.id,
        skill=SkillRef(slug=session.skill.slug, title=session.skill.title),
        difficulty=session.difficulty,
        status=session.status,
        target_question_count=session.target_question_count,
        answered_count=answered_count,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


async def _answered_count(db: AsyncSession, session_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count(Answer.id))
        .join(SessionItem, SessionItem.id == Answer.session_item_id)
        .where(SessionItem.session_id == session_id)
    ) or 0


async def _load_session(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, *, lock: bool = False
) -> AssessmentSession:
    stmt = (
        select(AssessmentSession)
        .where(AssessmentSession.id == session_id, AssessmentSession.learner_id == learner.id)
        .options(selectinload(AssessmentSession.skill))
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(of=AssessmentSession)
    session = await db.scalar(stmt)
    if session is None:
        # Same response for "doesn't exist" and "belongs to someone else".
        raise NotFound("Assessment not found")
    return session


async def start_session(
    db: AsyncSession, learner: Learner, payload: AssessmentCreate, default_length: int
) -> AssessmentOut:
    skill = await db.scalar(select(Skill).where(Skill.slug == payload.skill_slug))
    if skill is None:
        raise NotFound(f"Skill '{payload.skill_slug}' not found")

    available = await db.scalar(
        select(func.count())
        .select_from(Question)
        .where(
            Question.skill_id == skill.id,
            Question.difficulty == payload.difficulty,
            Question.is_active,
        )
    ) or 0
    if available == 0:
        raise Unprocessable(
            f"No {payload.difficulty.value} questions are available for {skill.title} yet"
        )

    session = AssessmentSession(
        learner_id=learner.id,
        skill_id=skill.id,
        difficulty=payload.difficulty,
        status=SessionStatus.ACTIVE,
        target_question_count=min(payload.question_count or default_length, available),
    )
    session.skill = skill
    db.add(session)
    await db.flush()
    await _record_session_start(db, learner.id, skill.id)
    await db.commit()
    return _session_out(session, 0)


async def get_session(db: AsyncSession, learner: Learner, session_id: uuid.UUID) -> AssessmentOut:
    session = await _load_session(db, learner, session_id)
    return _session_out(session, await _answered_count(db, session.id))


async def list_sessions(db: AsyncSession, learner: Learner, limit: int) -> list[AssessmentOut]:
    answered = _answered_count_subquery()
    rows = await db.execute(
        select(AssessmentSession, answered)
        .where(AssessmentSession.learner_id == learner.id)
        .options(selectinload(AssessmentSession.skill))
        .order_by(AssessmentSession.started_at.desc(), AssessmentSession.id)
        .limit(limit)
    )
    return [_session_out(s, n) for s, n in rows]


def _item_query():
    return select(SessionItem).options(
        selectinload(SessionItem.question).selectinload(Question.options),
        selectinload(SessionItem.question).selectinload(Question.topic),
    )


def _complete(session: AssessmentSession) -> None:
    session.status = SessionStatus.COMPLETED
    session.completed_at = _now()


async def next_question(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID
) -> NextQuestionPending | NextQuestionCompleted:
    """Returns the current unanswered question, serving a new one if needed.

    Idempotent until the served question is answered, so refreshing the page
    shows the same question rather than skipping ahead.
    """
    session = await _load_session(db, learner, session_id, lock=True)

    current = await db.scalar(
        _item_query()
        .outerjoin(Answer, Answer.session_item_id == SessionItem.id)
        .where(SessionItem.session_id == session.id, Answer.id.is_(None))
        .order_by(SessionItem.position)
        .limit(1)
    )
    if current is not None:
        answered = await _answered_count(db, session.id)
        await db.commit()
        return _pending(session, answered, current)

    answered = await _answered_count(db, session.id)
    if session.status is SessionStatus.COMPLETED:
        await db.commit()
        return NextQuestionCompleted(session=_session_out(session, answered))

    if answered < session.target_question_count:
        answered_by_learner = select(Answer.question_id).where(Answer.learner_id == learner.id)
        already_in_session = select(SessionItem.question_id).where(
            SessionItem.session_id == session.id
        )
        # Deterministic order: questions this learner hasn't answered before come
        # first, then authored order. This is not adaptive difficulty.
        question_id = await db.scalar(
            select(Question.id)
            .where(
                Question.skill_id == session.skill_id,
                Question.difficulty == session.difficulty,
                Question.is_active,
                Question.id.not_in(already_in_session),
            )
            .order_by(Question.id.in_(answered_by_learner), Question.position, Question.id)
            .limit(1)
        )
        if question_id is not None:
            item = SessionItem(
                session_id=session.id, question_id=question_id, position=answered + 1
            )
            db.add(item)
            await db.flush()
            item = await db.scalar(_item_query().where(SessionItem.id == item.id))
            await db.commit()
            assert item is not None
            return _pending(session, answered, item)

    # Target reached, or the question pool shrank since the session started.
    _complete(session)
    await _bump_progress(db, learner.id, session.skill_id, sessions_completed=1)
    await db.commit()
    return NextQuestionCompleted(session=_session_out(session, answered))


def _pending(session: AssessmentSession, answered: int, item: SessionItem) -> NextQuestionPending:
    return NextQuestionPending(
        session=_session_out(session, answered),
        item=SessionItemOut(
            id=item.id,
            position=item.position,
            question=public_question(item.question, item.question.topic),
        ),
    )


# ---------------------------------------------------------------- answers


async def submit_answer(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, payload: AnswerSubmit
) -> FeedbackOut:
    session = await _load_session(db, learner, session_id, lock=True)
    item = await db.scalar(
        _item_query()
        .options(selectinload(SessionItem.answer))
        .where(SessionItem.id == payload.item_id, SessionItem.session_id == session.id)
    )
    if item is None:
        raise NotFound("That question is not part of this assessment")
    if item.answer is not None:
        raise Conflict("This question has already been answered")

    question = item.question
    option = None
    if question.format is QuestionFormat.SINGLE_CHOICE:
        if payload.selected_option_key is None:
            raise InvalidAnswer("This question expects selected_option_key")
        option = next((o for o in question.options if o.key == payload.selected_option_key), None)
        if option is None:
            raise InvalidAnswer(
                f"Option '{payload.selected_option_key}' does not exist for this question"
            )
    elif payload.response_text is None:
        raise InvalidAnswer("This question expects response_text")

    result = evaluate(
        question.format, selected_option=option, response_text=payload.response_text
    )
    answer = Answer(
        session_item_id=item.id,
        question_id=question.id,
        learner_id=learner.id,
        selected_option_id=option.id if option else None,
        response_text=payload.response_text,
    )
    db.add(answer)
    await db.flush()
    db.add(
        EvaluationResult(
            answer_id=answer.id,
            status=result.status,
            method=result.method,
            is_correct=result.is_correct,
            score=result.score,
            evaluated_at=_now() if result.status is EvaluationStatus.GRADED else None,
        )
    )

    answered = await _answered_count(db, session.id)
    completed = answered >= session.target_question_count
    if completed:
        _complete(session)
    graded = result.status is EvaluationStatus.GRADED
    await _bump_progress(
        db,
        learner.id,
        session.skill_id,
        answers_submitted=1,
        objective_graded=int(graded),
        objective_correct=int(bool(result.is_correct)),
        pending_ai_evaluation=int(not graded),
        sessions_completed=int(completed),
    )
    try:
        await db.commit()
    except IntegrityError as exc:  # pragma: no cover - guarded by the row lock above
        await db.rollback()
        raise Conflict("This question has already been answered") from exc

    return await get_feedback(db, learner, session_id, item.id)


async def get_feedback(
    db: AsyncSession, learner: Learner, session_id: uuid.UUID, item_id: uuid.UUID
) -> FeedbackOut:
    session = await _load_session(db, learner, session_id)
    item = await db.scalar(
        select(SessionItem)
        .where(SessionItem.id == item_id, SessionItem.session_id == session.id)
        .options(
            selectinload(SessionItem.question).selectinload(Question.options),
            selectinload(SessionItem.question).selectinload(Question.topic),
            selectinload(SessionItem.question).selectinload(Question.rubric),
            selectinload(SessionItem.question).selectinload(Question.resources),
            selectinload(SessionItem.answer).selectinload(Answer.evaluation),
            selectinload(SessionItem.answer).selectinload(Answer.selected_option),
        )
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise NotFound("That question is not part of this assessment")
    if item.answer is None:
        # Answer material is only revealed after submission.
        raise NotFound("Feedback is available after you submit an answer")

    q, answer, ev = item.question, item.answer, item.answer.evaluation
    correct_key = next((o.key for o in q.options if o.is_correct), None)
    summary = summarise(
        Evaluation(
            status=ev.status,
            method=ev.method,
            is_correct=ev.is_correct,
            score=ev.score,
        ),
        correct_key,
    )
    return FeedbackOut(
        session_id=session.id,
        item_id=item.id,
        position=item.position,
        session=_session_out(session, await _answered_count(db, session.id)),
        question=public_question(q, q.topic),
        answer=SubmittedAnswerOut(
            selected_option_key=answer.selected_option.key if answer.selected_option else None,
            response_text=answer.response_text,
            submitted_at=answer.submitted_at,
        ),
        evaluation=EvaluationOut(
            status=ev.status,
            method=ev.method,
            is_correct=ev.is_correct,
            score=float(ev.score) if ev.score is not None else None,
            summary=summary,
        ),
        options=[OptionReveal(key=o.key, text=o.text, is_correct=o.is_correct) for o in q.options],
        explanation=q.explanation,
        rubric=[r.criterion for r in q.rubric],
        expected_concepts=list(q.expected_concepts),
        misconceptions=list(q.misconceptions),
        resources=[ResourceOut(title=r.title, url=r.url) for r in q.resources],
    )


# ---------------------------------------------------------------- history & progress


async def answer_history(
    db: AsyncSession,
    learner: Learner,
    limit: int,
    skill_slug: str | None = None,
    session_id: uuid.UUID | None = None,
) -> list[AnswerHistoryItem]:
    stmt = (
        select(Answer, SessionItem, Question, Skill, Topic, EvaluationResult)
        .join(SessionItem, SessionItem.id == Answer.session_item_id)
        .join(Question, Question.id == Answer.question_id)
        .join(Skill, Skill.id == Question.skill_id)
        .join(Topic, Topic.id == Question.topic_id)
        .join(EvaluationResult, EvaluationResult.answer_id == Answer.id)
        .where(Answer.learner_id == learner.id)
        .order_by(Answer.submitted_at.desc(), Answer.id)
        .limit(limit)
    )
    if skill_slug is not None:
        stmt = stmt.where(Skill.slug == skill_slug)
    if session_id is not None:
        stmt = stmt.where(SessionItem.session_id == session_id)
    rows = await db.execute(stmt)
    return [
        AnswerHistoryItem(
            answer_id=a.id,
            session_id=item.session_id,
            item_id=item.id,
            skill=SkillRef(slug=s.slug, title=s.title),
            topic=TopicRef(slug=t.slug, title=t.title),
            question_slug=q.slug,
            question_title=q.title,
            difficulty=q.difficulty,
            format=q.format,
            evaluation_status=ev.status,
            is_correct=ev.is_correct,
            submitted_at=a.submitted_at,
        )
        for a, item, q, s, t, ev in rows
    ]


async def get_progress(db: AsyncSession, learner: Learner) -> ProgressOut:
    rows = await db.execute(
        select(Skill, SkillProgress)
        .outerjoin(
            SkillProgress,
            (SkillProgress.skill_id == Skill.id) & (SkillProgress.learner_id == learner.id),
        )
        .order_by(Skill.position)
    )
    skills = []
    for skill, p in rows:
        skills.append(
            SkillProgressOut(
                skill=SkillRef(slug=skill.slug, title=skill.title),
                sessions_started=p.sessions_started if p else 0,
                sessions_completed=p.sessions_completed if p else 0,
                answers_submitted=p.answers_submitted if p else 0,
                objective_graded=p.objective_graded if p else 0,
                objective_correct=p.objective_correct if p else 0,
                pending_ai_evaluation=p.pending_ai_evaluation if p else 0,
                last_activity_at=p.last_activity_at if p else None,
            )
        )
    return ProgressOut(skills=skills)
