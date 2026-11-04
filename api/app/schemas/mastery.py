from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.enums import (
    Difficulty,
    EvidenceDimension,
    EvidenceSource,
    InterviewMode,
    MasteryState,
)
from app.schemas.content import SkillRef


class LevelSpecOut(BaseModel):
    difficulty: Difficulty
    objective: str
    competency: str
    question_count: int
    verifiable: bool  # objectively gradable questions exist at this level


class SubskillOut(BaseModel):
    slug: str
    title: str
    question_count: int


class CurriculumSkill(BaseModel):
    slug: str
    title: str
    category: str | None
    summary: str
    position: int
    depth: int  # longest prerequisite chain length
    assessable: bool
    prerequisites: list[str]
    dependants: list[str]
    learning_objectives: list[str]
    subskills: list[SubskillOut]
    levels: list[LevelSpecOut]


class CurriculumOut(BaseModel):
    version: str | None
    checksum: str | None
    skills: list[CurriculumSkill]


class SkillMasteryOut(BaseModel):
    """Values are null when no evidence of that kind exists. Never estimated."""

    model_config = ConfigDict(from_attributes=True)

    skill: SkillRef
    state: MasteryState
    demonstrated_level: Difficulty | None
    unverified_only: bool
    knowledge_accuracy: float | None  # verified, objective
    reasoning_score: float | None  # unverified AI evaluations
    debugging_score: float | None  # unverified AI evaluations (debug mode)
    practical_score: float | None  # always null: no verified practical tests yet
    retention_score: float | None
    uncertainty: float | None
    # Mean grader confidence across AI-interview evidence (null without any).
    ai_confidence: float | None = None
    inconsistent: bool
    evidence_count: int
    verified_count: int
    distinct_questions: int
    distinct_sessions: int
    successful_attempts: int
    last_evidence_at: datetime | None
    last_success_at: datetime | None
    reasons: list[str]
    review_due_at: datetime | None
    prerequisites_met: bool
    assessable: bool


class MasteryOverview(BaseModel):
    algorithm_version: str
    skills: list[SkillMasteryOut]


class LevelReportOut(BaseModel):
    level: Difficulty
    attempts: int
    successes: int
    verified_successes: int
    distinct_success_sessions: int
    distinct_success_questions: int
    recent_accuracy: float | None
    verifiable: bool
    demonstrated: bool
    unverified_only: bool
    missing: list[str]


class EvidenceOut(BaseModel):
    id: str
    source: EvidenceSource
    dimension: EvidenceDimension
    verified: bool
    difficulty: Difficulty
    question_title: str
    score: float
    success: bool
    hints_used: int
    said_dont_know: bool
    observed_at: datetime


class ReviewCardOut(BaseModel):
    skill: SkillRef
    due_at: datetime
    interval_days: int
    repetitions: int
    ease: float
    lapses: int
    consecutive_lapses: int
    missed_reviews: int
    last_quality: int | None
    last_reviewed_at: datetime | None
    overdue_days: int
    needs_relearning: bool


class MasteryEventOut(BaseModel):
    skill: SkillRef
    from_state: MasteryState | None
    to_state: MasteryState
    from_level: Difficulty | None
    to_level: Difficulty | None
    reason: str
    occurred_at: datetime


class MisconceptionHistoryOut(BaseModel):
    description: str
    known_misconception: str | None
    quote: str | None
    observed: bool
    question_title: str
    created_at: datetime


class SkillMasteryDetail(BaseModel):
    curriculum: CurriculumSkill
    mastery: SkillMasteryOut
    levels: list[LevelReportOut]
    evidence: list[EvidenceOut]
    review: ReviewCardOut | None
    history: list[MasteryEventOut]
    misconceptions: list[MisconceptionHistoryOut]
    prerequisite_states: dict[str, MasteryState]


class ActivityOut(BaseModel):
    type: str  # assessment | interview | coding
    skill_slug: str
    difficulty: Difficulty
    mode: InterviewMode | None
    challenge_slug: str | None = None


class RecommendationOut(BaseModel):
    key: str
    kind: str
    skill: SkillRef
    activity: ActivityOut
    # Same target through the AI interviewer (unverified evidence).
    interview_alternative: ActivityOut | None = None
    priority: float
    reasons: list[str]


class ReviewQueueOut(BaseModel):
    daily_limit: int
    total_due: int
    due: list[ReviewCardOut]
    upcoming: list[ReviewCardOut]


class GapOut(BaseModel):
    kind: str
    skill: SkillRef
    title: str
    detail: str
    occurrences: int
    last_seen: datetime | None
    related_skill: SkillRef | None
    evidence: list[str]


class SyncOut(BaseModel):
    new_evidence: int
    skills_recomputed: int
    events_created: int


class GoalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_level: Difficulty


class GoalOut(BaseModel):
    skill: SkillRef
    target_level: Difficulty
    created_at: datetime
