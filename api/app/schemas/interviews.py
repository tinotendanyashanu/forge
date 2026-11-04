import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.db.enums import (
    ChallengeStatus,
    Difficulty,
    InterviewEvaluationStatus,
    InterviewMode,
    InterviewStatus,
    QuestionFormat,
    TurnKind,
    TurnRole,
)
from app.schemas.assessments import ResourceOut
from app.schemas.content import SkillRef, TopicRef

MAX_ANSWER_CHARS = 10_000

AnswerText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ANSWER_CHARS)
]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterviewCreate(_In):
    skill_slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)
    difficulty: Difficulty
    mode: InterviewMode
    challenge_count: int = Field(default=3, ge=1, le=10)


class ClientAction(_In):
    """Every learner action carries a client-generated id for idempotent retries."""

    client_turn_id: uuid.UUID


class AnswerIn(ClientAction):
    content: AnswerText


# ---------------------------------------------------------------- output


class CriterionOut(BaseModel):
    criterion_id: int
    criterion: str
    score: int
    max_score: int
    evidence: str  # observed | inferred | none
    evidence_quote: str | None
    rationale: str


class MisconceptionOut(BaseModel):
    description: str
    quote: str | None
    observed: bool
    known_misconception: str | None


class EvaluationBrief(BaseModel):
    """Shown while a challenge is open: status only, no rubric material."""

    id: uuid.UUID
    status: InterviewEvaluationStatus
    error_code: str | None
    retryable: bool


class EvaluationFull(EvaluationBrief):
    """Shown once the challenge is complete. Scores only when status is evaluated."""

    total_score: float | None
    model_total_score: float | None
    confidence: float | None
    answer_complete: bool | None
    criteria: list[CriterionOut]
    demonstrated_concepts: list[str]
    missing_concepts: list[str]
    misconceptions: list[MisconceptionOut]
    feedback: str | None
    injection_suspected: bool
    mastery_eligible: bool
    provider: str
    model: str
    prompt_version: str
    created_at: datetime


class TurnOut(BaseModel):
    id: uuid.UUID
    seq: int
    challenge_id: uuid.UUID | None
    role: TurnRole
    kind: TurnKind
    content: str
    hint_level: int | None
    created_at: datetime
    evaluation: EvaluationBrief | EvaluationFull | None = None


class ChallengeQuestion(BaseModel):
    slug: str
    title: str
    prompt: str
    code: str | None
    code_language: str | None
    format: QuestionFormat
    difficulty: Difficulty
    topic: TopicRef
    estimated_minutes: int


class Reveal(BaseModel):
    """Reference material, available only after the challenge is finished."""

    explanation: str
    acceptance_criteria: str | None
    rubric: list[str]
    expected_concepts: list[str]
    known_misconceptions: list[str]
    resources: list[ResourceOut]
    final_evaluation: EvaluationFull | None


class ChallengeOut(BaseModel):
    id: uuid.UUID
    position: int
    status: ChallengeStatus
    difficulty: Difficulty
    question: ChallengeQuestion
    attempts: int
    hints_used: int
    max_hints: int
    follow_ups_asked: int
    can_request_hint: bool
    hint_blocked_reason: str | None
    awaiting_evaluation: bool
    reveal: Reveal | None


class InterviewSessionOut(BaseModel):
    id: uuid.UUID
    skill: SkillRef
    mode: InterviewMode
    status: InterviewStatus
    start_difficulty: Difficulty
    current_difficulty: Difficulty
    target_challenge_count: int
    challenges_finished: int
    provider: str
    model: str
    started_at: datetime
    completed_at: datetime | None


class InterviewState(BaseModel):
    session: InterviewSessionOut
    current_challenge: ChallengeOut | None
    turns: list[TurnOut]
    can_continue: bool


class ChallengeSummary(BaseModel):
    position: int
    status: ChallengeStatus
    question_title: str
    difficulty: Difficulty
    attempts: int
    hints_used: int
    follow_ups_asked: int
    said_dont_know: bool
    final_evaluation: EvaluationFull | None


class InterviewSummary(BaseModel):
    session: InterviewSessionOut
    challenges: list[ChallengeSummary]
    evaluated_count: int
    ungraded_count: int
    misconceptions: list[MisconceptionOut]
    notes: list[str]


class LLMStatus(BaseModel):
    provider: str
    model: str
    configured: bool
    reachable: bool
