from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentLearner, Db
from app.schemas.lessons import LessonDetail, LessonProgressOut, LessonSummary
from app.services import lessons

public = APIRouter(tags=["lessons"])
router = APIRouter(tags=["lessons"])


def _now(request: Request) -> datetime:
    return request.app.state.clock()


Now = Annotated[datetime, Depends(_now)]


@public.get("/lessons", response_model=list[LessonSummary])
async def list_lessons(
    db: Db, skill: Annotated[str | None, Query(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")] = None
) -> list[LessonSummary]:
    return await lessons.list_lessons(db, skill)


@public.get("/lessons/{slug}", response_model=LessonDetail)
async def get_lesson(slug: str, db: Db) -> LessonDetail:
    return await lessons.get_lesson(db, slug)


@router.get("/lesson-progress", response_model=list[LessonProgressOut])
async def lesson_progress(learner: CurrentLearner, db: Db) -> list[LessonProgressOut]:
    return await lessons.progress(db, learner.id)


@router.post("/lessons/{slug}/open", response_model=LessonProgressOut)
async def open_lesson(slug: str, learner: CurrentLearner, db: Db, now: Now) -> LessonProgressOut:
    """Records that the learner opened a lesson. Engagement only, never mastery evidence."""
    return await lessons.mark(db, learner.id, slug, now, completed=False)


@router.post("/lessons/{slug}/complete", response_model=LessonProgressOut)
async def complete_lesson(slug: str, learner: CurrentLearner, db: Db, now: Now) -> LessonProgressOut:
    """Records that the learner finished reading. Engagement only, never mastery evidence."""
    return await lessons.mark(db, learner.id, slug, now, completed=True)
