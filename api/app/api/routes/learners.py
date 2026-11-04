import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentLearner, Db, sync_mastery_best_effort
from app.schemas.assessments import (
    AnswerHistoryItem,
    AnswerSubmit,
    AssessmentCreate,
    AssessmentOut,
    FeedbackOut,
    LearnerOut,
    NextQuestionCompleted,
    NextQuestionOut,
    NextQuestionPending,
    ProgressOut,
)
from app.services import assessments

router = APIRouter()


@router.post(
    "/learners",
    response_model=LearnerOut,
    status_code=status.HTTP_201_CREATED,
    tags=["learners"],
)
async def create_learner(db: Db) -> LearnerOut:
    """Creates an anonymous learner. The id identifies, it does not authenticate."""
    learner = await assessments.create_learner(db)
    return LearnerOut(id=learner.id, created_at=learner.created_at)


@router.get("/learners/me", response_model=LearnerOut, tags=["learners"])
async def get_me(learner: CurrentLearner) -> LearnerOut:
    return LearnerOut(id=learner.id, created_at=learner.created_at)


# ---------------------------------------------------------------- assessments


@router.post(
    "/assessments",
    response_model=AssessmentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["assessments"],
)
async def start_assessment(
    payload: AssessmentCreate, learner: CurrentLearner, db: Db, request: Request
) -> AssessmentOut:
    default_length = request.app.state.settings.default_session_length
    return await assessments.start_session(db, learner, payload, default_length)


@router.get("/assessments", response_model=list[AssessmentOut], tags=["assessments"])
async def list_assessments(
    learner: CurrentLearner, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[AssessmentOut]:
    return await assessments.list_sessions(db, learner, limit)


@router.get("/assessments/{session_id}", response_model=AssessmentOut, tags=["assessments"])
async def get_assessment(session_id: uuid.UUID, learner: CurrentLearner, db: Db) -> AssessmentOut:
    return await assessments.get_session(db, learner, session_id)


@router.post(
    "/assessments/{session_id}/next",
    response_model=NextQuestionOut,
    tags=["assessments"],
)
async def next_question(
    session_id: uuid.UUID, learner: CurrentLearner, db: Db
) -> NextQuestionPending | NextQuestionCompleted:
    """Returns the current unanswered question, serving a new one when needed.

    POST because it may create a session item; repeated calls return the same
    question until it is answered.
    """
    return await assessments.next_question(db, learner, session_id)


@router.post(
    "/assessments/{session_id}/answers",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    tags=["assessments"],
)
async def submit_answer(
    session_id: uuid.UUID, payload: AnswerSubmit, learner: CurrentLearner, db: Db, request: Request
) -> FeedbackOut:
    feedback = await assessments.submit_answer(db, learner, session_id, payload)
    await sync_mastery_best_effort(request, db, learner)
    return feedback


@router.get(
    "/assessments/{session_id}/items/{item_id}/feedback",
    response_model=FeedbackOut,
    tags=["assessments"],
)
async def get_feedback(
    session_id: uuid.UUID, item_id: uuid.UUID, learner: CurrentLearner, db: Db
) -> FeedbackOut:
    return await assessments.get_feedback(db, learner, session_id, item_id)


# ---------------------------------------------------------------- history & progress


@router.get("/answers", response_model=list[AnswerHistoryItem], tags=["progress"])
async def list_answers(
    learner: CurrentLearner,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    skill: Annotated[str | None, Query(max_length=64)] = None,
    session: Annotated[uuid.UUID | None, Query()] = None,
) -> list[AnswerHistoryItem]:
    return await assessments.answer_history(db, learner, limit, skill, session)


@router.get("/progress", response_model=ProgressOut, tags=["progress"])
async def get_progress(learner: CurrentLearner, db: Db) -> ProgressOut:
    return await assessments.get_progress(db, learner)
