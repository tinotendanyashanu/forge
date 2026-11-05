from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.enums import Difficulty, QuestionFormat
from app.schemas.content import SkillRef, TopicRef


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LessonRef(_Out):
    slug: str
    title: str
    difficulty: Difficulty
    estimated_minutes: int


class LessonSummary(LessonRef):
    summary: str
    skill: SkillRef
    topic: TopicRef | None
    status: str


class LessonResourceOut(_Out):
    title: str
    url: str


class LessonCheckOut(_Out):
    slug: str
    title: str
    difficulty: Difficulty
    format: QuestionFormat


class LessonDetail(LessonSummary):
    body: str
    objectives: list[str]
    prerequisites: list[LessonRef]
    misconceptions: list[str]
    resources: list[LessonResourceOut]
    checks: list[LessonCheckOut]
    version: int
    provenance: str
    updated_at: datetime


class LessonProgressOut(BaseModel):
    slug: str
    first_opened_at: datetime
    completed_at: datetime | None


class LessonSuggestion(LessonRef):
    """A lesson to read before (or alongside) a recommended activity."""

    completed: bool
