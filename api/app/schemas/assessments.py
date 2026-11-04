import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.db.enums import (
    Difficulty,
    EvaluationMethod,
    EvaluationStatus,
    QuestionFormat,
    SessionStatus,
)
from app.schemas.content import QuestionPublic, SkillRef, TopicRef

MAX_RESPONSE_CHARS = 10_000


class LearnerOut(BaseModel):
    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------- sessions


class AssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)
    difficulty: Difficulty
    question_count: int | None = Field(default=None, ge=1, le=20)


class AssessmentOut(BaseModel):
    id: uuid.UUID
    skill: SkillRef
    difficulty: Difficulty
    status: SessionStatus
    target_question_count: int
    answered_count: int
    started_at: datetime
    completed_at: datetime | None


class SessionItemOut(BaseModel):
    id: uuid.UUID
    position: int
    question: QuestionPublic


class NextQuestionPending(BaseModel):
    status: Literal["question"] = "question"
    session: AssessmentOut
    item: SessionItemOut


class NextQuestionCompleted(BaseModel):
    status: Literal["completed"] = "completed"
    session: AssessmentOut


NextQuestionOut = Annotated[
    NextQuestionPending | NextQuestionCompleted, Field(discriminator="status")
]


# ---------------------------------------------------------------- answers


ResponseText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_RESPONSE_CHARS)
]


class AnswerSubmit(BaseModel):
    """Exactly one of ``selected_option_key`` or ``response_text``."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    selected_option_key: str | None = Field(default=None, pattern=r"^[a-f]$")
    response_text: ResponseText | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.selected_option_key is None) == (self.response_text is None):
            raise ValueError("Provide exactly one of selected_option_key or response_text")
        return self


class OptionReveal(BaseModel):
    key: str
    text: str
    is_correct: bool


class ResourceOut(BaseModel):
    title: str
    url: str


class EvaluationOut(BaseModel):
    status: EvaluationStatus
    method: EvaluationMethod | None
    # Present only for deterministic grading; never estimated for free text.
    is_correct: bool | None
    score: float | None
    summary: str


class SubmittedAnswerOut(BaseModel):
    selected_option_key: str | None
    response_text: str | None
    submitted_at: datetime


class FeedbackOut(BaseModel):
    """Everything revealed after submission. Only served once an answer exists."""

    session_id: uuid.UUID
    item_id: uuid.UUID
    position: int
    session: AssessmentOut
    question: QuestionPublic
    answer: SubmittedAnswerOut
    evaluation: EvaluationOut
    options: list[OptionReveal]
    explanation: str
    rubric: list[str]
    expected_concepts: list[str]
    misconceptions: list[str]
    resources: list[ResourceOut]


# ---------------------------------------------------------------- history & progress


class AnswerHistoryItem(BaseModel):
    answer_id: uuid.UUID
    session_id: uuid.UUID
    item_id: uuid.UUID
    skill: SkillRef
    topic: TopicRef
    question_slug: str
    question_title: str
    difficulty: Difficulty
    format: QuestionFormat
    evaluation_status: EvaluationStatus
    is_correct: bool | None
    submitted_at: datetime


class SkillProgressOut(BaseModel):
    """Raw activity counts. FORGE does not compute mastery scores yet."""

    skill: SkillRef
    sessions_started: int
    sessions_completed: int
    answers_submitted: int
    objective_graded: int
    objective_correct: int
    pending_ai_evaluation: int
    last_activity_at: datetime | None


class ProgressOut(BaseModel):
    skills: list[SkillProgressOut]
