import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import CurrentLearner, Db, get_llm, sync_mastery_best_effort
from app.interview import engine
from app.schemas.interviews import (
    AnswerIn,
    ClientAction,
    InterviewCreate,
    InterviewSessionOut,
    InterviewState,
    InterviewSummary,
    LLMStatus,
)

router = APIRouter(tags=["interviews"])
LLM = Annotated[object, Depends(get_llm)]


@router.get("/llm/status", response_model=LLMStatus)
async def llm_status(llm: LLM) -> LLMStatus:
    """Provider name, model and reachability. Never includes credentials."""
    name = getattr(llm, "name", "unknown")
    return LLMStatus(
        provider=name,
        model=getattr(llm, "model", "unknown"),
        configured=name != "disabled",
        reachable=await llm.check(),  # type: ignore[attr-defined]
    )


@router.post("/interviews", response_model=InterviewState, status_code=status.HTTP_201_CREATED)
async def start(payload: InterviewCreate, learner: CurrentLearner, db: Db, llm: LLM) -> InterviewState:
    return await engine.start_interview(db, learner, payload, llm)  # type: ignore[arg-type]


@router.get("/interviews", response_model=list[InterviewSessionOut])
async def list_(
    learner: CurrentLearner, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[InterviewSessionOut]:
    return await engine.list_interviews(db, learner, limit)


@router.get("/interviews/{session_id}", response_model=InterviewState)
async def get(session_id: uuid.UUID, learner: CurrentLearner, db: Db) -> InterviewState:
    return await engine.get_state(db, learner, session_id)


@router.post("/interviews/{session_id}/answers", response_model=InterviewState)
async def answer(
    session_id: uuid.UUID, payload: AnswerIn, learner: CurrentLearner, db: Db, llm: LLM, request: Request
) -> InterviewState:
    """Idempotent on ``client_turn_id``: retries return the existing state."""
    state = await engine.submit_answer(
        db, request.app.state.settings, llm, learner, session_id,  # type: ignore[arg-type]
        payload.client_turn_id, payload.content,
    )
    await sync_mastery_best_effort(request, db, learner)
    return state


@router.post("/interviews/{session_id}/dont-know", response_model=InterviewState)
async def dont_know(
    session_id: uuid.UUID, payload: ClientAction, learner: CurrentLearner, db: Db, request: Request
) -> InterviewState:
    state = await engine.dont_know(db, learner, session_id, payload.client_turn_id)
    await sync_mastery_best_effort(request, db, learner)
    return state


@router.post("/interviews/{session_id}/hints", response_model=InterviewState)
async def hint(
    session_id: uuid.UUID, payload: ClientAction, learner: CurrentLearner, db: Db
) -> InterviewState:
    return await engine.request_hint(db, learner, session_id, payload.client_turn_id)


@router.post(
    "/interviews/{session_id}/evaluations/{evaluation_id}/retry", response_model=InterviewState
)
async def retry(
    session_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    learner: CurrentLearner,
    db: Db,
    llm: LLM,
    request: Request,
) -> InterviewState:
    state = await engine.retry_evaluation(
        db, request.app.state.settings, llm, learner, session_id, evaluation_id  # type: ignore[arg-type]
    )
    await sync_mastery_best_effort(request, db, learner)
    return state


@router.post("/interviews/{session_id}/continue", response_model=InterviewState)
async def continue_(
    session_id: uuid.UUID, payload: ClientAction, learner: CurrentLearner, db: Db
) -> InterviewState:
    """Moves to the next challenge (skipping the current one if unfinished)."""
    return await engine.continue_interview(db, learner, session_id, payload.client_turn_id)


@router.get("/interviews/{session_id}/summary", response_model=InterviewSummary)
async def summary(session_id: uuid.UUID, learner: CurrentLearner, db: Db) -> InterviewSummary:
    return await engine.get_summary(db, learner, session_id)
