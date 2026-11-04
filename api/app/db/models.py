"""ORM models. Schema changes must go through an Alembic migration."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import (
    ChallengeStatus,
    DesignLevel,
    DesignReviewMode,
    Difficulty,
    EvidenceDimension,
    EvidenceSource,
    JobKind,
    JobStatus,
    ReviewStatus,
    TestOutcome,
    TestVisibility,
    MasteryState,
    EvaluationMethod,
    EvaluationStatus,
    InterviewEvaluationStatus,
    InterviewMode,
    InterviewStatus,
    QuestionFormat,
    SessionStatus,
    TurnKind,
    TurnRole,
)


def _enum(cls: type, name: str) -> Enum:
    # VARCHAR + CHECK rather than native PG enums: simpler to evolve in migrations.
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


SLUG_CHECK = "{col} ~ '^[a-z0-9]+(-[a-z0-9]+)*$'"


# --------------------------------------------------------------------------- content


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger, unique=True)
    category: Mapped[str | None] = mapped_column(String(64))
    learning_objectives: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = _created_at()

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="skill", order_by="Topic.position"
    )


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("skill_id", "slug"),
        UniqueConstraint("skill_id", "position"),
        # Target for the composite FK that keeps question.skill_id consistent.
        UniqueConstraint("id", "skill_id", name="uq_topics_id_skill_id"),
        CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(SmallInteger)

    skill: Mapped[Skill] = relationship(back_populates="topics")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["topic_id", "skill_id"],
            ["topics.id", "topics.skill_id"],
            name="fk_questions_topic_skill",
        ),
        UniqueConstraint("id", "skill_id", name="uq_questions_id_skill_id"),
        CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),
        CheckConstraint("estimated_minutes BETWEEN 1 AND 120", name="estimated_minutes_range"),
        CheckConstraint("cardinality(expected_concepts) >= 1", name="has_expected_concepts"),
        CheckConstraint("cardinality(misconceptions) >= 1", name="has_misconceptions"),
        CheckConstraint("code IS NOT NULL OR code_language IS NULL", name="code_language_needs_code"),
        Index(
            "ix_questions_selection",
            "skill_id",
            "difficulty",
            "position",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    topic_id: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    format: Mapped[QuestionFormat] = mapped_column(_enum(QuestionFormat, "question_format"))
    title: Mapped[str] = mapped_column(String(160))
    prompt: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    code_language: Mapped[str | None] = mapped_column(String(32))
    hint: Mapped[str | None] = mapped_column(Text)
    # Revealed only after an answer is submitted.
    explanation: Mapped[str] = mapped_column(Text)
    # What a complete answer must establish. Hidden from learners; used by graders.
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    expected_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    misconceptions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    estimated_minutes: Mapped[int] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    skill: Mapped[Skill] = relationship()
    topic: Mapped[Topic] = relationship(
        primaryjoin="Question.topic_id == Topic.id", foreign_keys=[topic_id], viewonly=True
    )
    options: Mapped[list["QuestionOption"]] = relationship(
        order_by="QuestionOption.key", cascade="all, delete-orphan"
    )
    rubric: Mapped[list["RubricCriterion"]] = relationship(
        order_by="RubricCriterion.position", cascade="all, delete-orphan"
    )
    resources: Mapped[list["LearningResource"]] = relationship(
        order_by="LearningResource.position", cascade="all, delete-orphan"
    )


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "key"),
        UniqueConstraint("id", "question_id", name="uq_question_options_id_question_id"),
        CheckConstraint("key ~ '^[a-f]$'", name="key_format"),
        # At most one correct option per question (exactly-one is checked by the seed loader).
        Index(
            "uq_question_options_one_correct",
            "question_id",
            unique=True,
            postgresql_where=text("is_correct"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(1))
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("question_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    criterion: Mapped[str] = mapped_column(Text)


class LearningResource(Base):
    __tablename__ = "learning_resources"
    __table_args__ = (
        UniqueConstraint("question_id", "position"),
        CheckConstraint("url ~ '^https://'", name="https_url"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))


# --------------------------------------------------------------------------- learners


class Learner(Base):
    """Anonymous learner. An opaque id, not an authenticated account."""

    __tablename__ = "learners"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created_at()


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        CheckConstraint("target_question_count BETWEEN 1 AND 20", name="target_count_range"),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at_matches_status"
        ),
        Index("ix_assessment_sessions_learner_started", "learner_id", text("started_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE")
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus, "session_status"), server_default=SessionStatus.ACTIVE.value
    )
    target_question_count: Mapped[int] = mapped_column(SmallInteger)
    started_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    skill: Mapped[Skill] = relationship()
    items: Mapped[list["SessionItem"]] = relationship(
        back_populates="session", order_by="SessionItem.position"
    )


class SessionItem(Base):
    """A question served within a session, in order."""

    __tablename__ = "session_items"
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        UniqueConstraint("session_id", "question_id"),
        UniqueConstraint("id", "question_id", name="uq_session_items_id_question_id"),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_sessions.id", ondelete="CASCADE")
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    served_at: Mapped[datetime] = _created_at()

    session: Mapped[AssessmentSession] = relationship(back_populates="items")
    question: Mapped[Question] = relationship()
    answer: Mapped["Answer | None"] = relationship(back_populates="item", uselist=False)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        # The answer's question must be the item's question...
        ForeignKeyConstraint(
            ["session_item_id", "question_id"],
            ["session_items.id", "session_items.question_id"],
            ondelete="CASCADE",
            name="fk_answers_item_question",
        ),
        # ...and a selected option must belong to that same question.
        ForeignKeyConstraint(
            ["selected_option_id", "question_id"],
            ["question_options.id", "question_options.question_id"],
            name="fk_answers_option_question",
        ),
        CheckConstraint(
            "(selected_option_id IS NULL) <> (response_text IS NULL)",
            name="exactly_one_response",
        ),
        CheckConstraint(
            "response_text IS NULL OR char_length(btrim(response_text)) BETWEEN 1 AND 10000",
            name="response_text_length",
        ),
        Index("ix_answers_learner_submitted", "learner_id", text("submitted_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    question_id: Mapped[int] = mapped_column(Integer)
    learner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE")
    )
    selected_option_id: Mapped[int | None] = mapped_column(Integer)
    response_text: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = _created_at()

    item: Mapped[SessionItem] = relationship(back_populates="answer")
    selected_option: Mapped[QuestionOption | None] = relationship(
        primaryjoin="Answer.selected_option_id == QuestionOption.id",
        foreign_keys=[selected_option_id],
        viewonly=True,
    )
    evaluation: Mapped["EvaluationResult"] = relationship(back_populates="answer", uselist=False)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        CheckConstraint(
            "status <> 'graded' OR (is_correct IS NOT NULL AND score IS NOT NULL "
            "AND method IS NOT NULL AND evaluated_at IS NOT NULL)",
            name="graded_is_complete",
        ),
        CheckConstraint(
            "status <> 'pending_ai_evaluation' OR (is_correct IS NULL AND score IS NULL "
            "AND method IS NULL AND evaluated_at IS NULL)",
            name="pending_has_no_result",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[EvaluationStatus] = mapped_column(_enum(EvaluationStatus, "evaluation_status"))
    method: Mapped[EvaluationMethod | None] = mapped_column(
        _enum(EvaluationMethod, "evaluation_method")
    )
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    answer: Mapped[Answer] = relationship(back_populates="evaluation")


class SkillProgress(Base):
    """Raw per-skill activity counts. Deliberately not a mastery estimate."""

    __tablename__ = "skill_progress"
    __table_args__ = (
        CheckConstraint(
            "sessions_started >= 0 AND sessions_completed >= 0 AND answers_submitted >= 0 "
            "AND objective_graded >= 0 AND objective_correct >= 0 AND pending_ai_evaluation >= 0",
            name="non_negative",
        ),
        CheckConstraint("sessions_completed <= sessions_started", name="completed_le_started"),
        CheckConstraint("objective_correct <= objective_graded", name="correct_le_graded"),
        CheckConstraint(
            "objective_graded + pending_ai_evaluation <= answers_submitted",
            name="evaluated_le_submitted",
        ),
    )

    learner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    sessions_started: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    sessions_completed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    answers_submitted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    objective_graded: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    objective_correct: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    pending_ai_evaluation: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_activity_at: Mapped[datetime] = _created_at()

    skill: Mapped[Skill] = relationship()


# --------------------------------------------------------------------------- interviews


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint("target_challenge_count BETWEEN 1 AND 20", name="target_count_range"),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at_matches_status"
        ),
        Index("ix_interview_sessions_learner_started", "learner_id", text("started_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    mode: Mapped[InterviewMode] = mapped_column(_enum(InterviewMode, "interview_mode"))
    start_difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "start_difficulty"))
    current_difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "current_difficulty"))
    status: Mapped[InterviewStatus] = mapped_column(
        _enum(InterviewStatus, "interview_status"), server_default=InterviewStatus.ACTIVE.value
    )
    target_challenge_count: Mapped[int] = mapped_column(SmallInteger)
    # Model metadata at session start (each evaluation also records its own).
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    skill: Mapped[Skill] = relationship()
    challenges: Mapped[list["InterviewChallenge"]] = relationship(
        back_populates="session", order_by="InterviewChallenge.position"
    )


class InterviewChallenge(Base):
    """One question worked through inside an interview, possibly over several turns."""

    __tablename__ = "interview_challenges"
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        UniqueConstraint("session_id", "question_id"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint("hints_used BETWEEN 0 AND 3", name="hints_range"),
        CheckConstraint("follow_ups_asked >= 0 AND attempts >= 0", name="counters_non_negative"),
        CheckConstraint(
            "(status = 'open') = (completed_at IS NULL)", name="completed_at_matches_status"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    status: Mapped[ChallengeStatus] = mapped_column(
        _enum(ChallengeStatus, "challenge_status"), server_default=ChallengeStatus.OPEN.value
    )
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    follow_ups_asked: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    said_dont_know: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    started_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[InterviewSession] = relationship(back_populates="challenges")
    question: Mapped[Question] = relationship()
    evaluations: Mapped[list["InterviewEvaluation"]] = relationship(
        back_populates="challenge", order_by="InterviewEvaluation.created_at"
    )


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        # Idempotency: a client-generated id can only ever create one turn.
        UniqueConstraint("session_id", "client_turn_id"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="content_length"),
        CheckConstraint("hint_level IS NULL OR hint_level BETWEEN 1 AND 3", name="hint_level_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_challenges.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[TurnRole] = mapped_column(_enum(TurnRole, "turn_role"))
    kind: Mapped[TurnKind] = mapped_column(_enum(TurnKind, "turn_kind"))
    content: Mapped[str] = mapped_column(Text)
    client_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    hint_level: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = _created_at()


class InterviewEvaluation(Base):
    """One grading attempt for one learner answer, with full model metadata."""

    __tablename__ = "interview_evaluations"
    __table_args__ = (
        CheckConstraint(
            "status <> 'evaluated' OR (total_score IS NOT NULL AND confidence IS NOT NULL)",
            name="evaluated_has_scores",
        ),
        CheckConstraint(
            "status = 'evaluated' OR (total_score IS NULL AND model_total_score IS NULL "
            "AND mastery_eligible = false)",
            name="unevaluated_has_no_scores",
        ),
        CheckConstraint("status <> 'ungraded' OR error_code IS NOT NULL", name="ungraded_has_reason"),
        CheckConstraint("total_score IS NULL OR total_score BETWEEN 0 AND 1", name="total_range"),
        CheckConstraint(
            "model_total_score IS NULL OR model_total_score BETWEEN 0 AND 1",
            name="model_total_range",
        ),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_challenges.id", ondelete="CASCADE"), index=True
    )
    answer_turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_turns.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[InterviewEvaluationStatus] = mapped_column(
        _enum(InterviewEvaluationStatus, "interview_evaluation_status")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Score counted only from criteria backed by a quote verified in the answer.
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    # The model's unverified total, kept for transparency; never used for mastery.
    model_total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    answer_complete: Mapped[bool | None] = mapped_column(Boolean)
    criterion_scores: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    demonstrated_concepts: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    missing_concepts: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    misconceptions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    feedback: Mapped[str | None] = mapped_column(Text)
    suggested_follow_up: Mapped[str | None] = mapped_column(Text)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mastery_eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    structured_output: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    raw_output: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    challenge: Mapped[InterviewChallenge] = relationship(back_populates="evaluations")


class MisconceptionEvent(Base):
    """A misconception the learner expressed, as identified in an evaluation."""

    __tablename__ = "misconception_events"
    __table_args__ = (
        Index("ix_misconception_events_learner_skill", "learner_id", "skill_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_evaluations.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    # The learner's own words, verified to appear in the answer (observed),
    # or null when the model inferred it without a verifiable quote.
    quote: Mapped[str | None] = mapped_column(Text)
    observed: Mapped[bool] = mapped_column(Boolean)
    # The persisted known misconception it matched, if any.
    known_misconception: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


# --------------------------------------------------------------------------- curriculum


class CurriculumVersion(Base):
    __tablename__ = "curriculum_versions"
    __table_args__ = (
        Index("uq_curriculum_versions_current", "is_current", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    checksum: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    loaded_at: Mapped[datetime] = _created_at()


class SkillPrerequisite(Base):
    """Directed edge: ``skill`` requires ``prerequisite``. Acyclic (checked on load)."""

    __tablename__ = "skill_prerequisites"
    __table_args__ = (CheckConstraint("skill_id <> prerequisite_id", name="no_self_loop"),)

    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    curriculum_version_id: Mapped[int] = mapped_column(ForeignKey("curriculum_versions.id"))


class SkillLevel(Base):
    __tablename__ = "skill_levels"

    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), primary_key=True)
    objective: Mapped[str] = mapped_column(Text)
    competency: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------- mastery


class MasteryEvidence(Base):
    """One scored attempt, normalised from an assessment answer or interview.

    ``(source, source_id)`` is unique, so re-ingesting is a no-op.
    """

    __tablename__ = "mastery_evidence"
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        # Only deterministic grading is verified: objective answers and sandboxed tests.
        CheckConstraint(
            "verified = (source IN ('objective_assessment', 'coding_submission', 'incident_simulation', 'engineering_task'))",
            name="verified_matches_source",
        ),
        CheckConstraint(
            "num_nonnulls(question_id, coding_challenge_id, design_challenge_id, incident_scenario_id, engineering_project_id) = 1",
            name="exactly_one_subject",
        ),
        CheckConstraint(
            "(source IN ('incident_simulation', 'incident_review')) = (incident_scenario_id IS NOT NULL)",
            name="incident_subject_matches_source",
        ),
        CheckConstraint(
            "(source = 'coding_submission') = (coding_challenge_id IS NOT NULL)",
            name="coding_subject_matches_source",
        ),
        CheckConstraint(
            "(source IN ('design_evaluation', 'failure_scenario')) = (design_challenge_id IS NOT NULL)",
            name="design_subject_matches_source",
        ),
        CheckConstraint(
            "(source = 'engineering_task') = (engineering_project_id IS NOT NULL)",
            name="engineering_subject_matches_source",
        ),
        Index("ix_mastery_evidence_learner_skill", "learner_id", "skill_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    coding_challenge_id: Mapped[int | None] = mapped_column(
        ForeignKey("coding_challenges.id", ondelete="CASCADE")
    )
    design_challenge_id: Mapped[int | None] = mapped_column(
        ForeignKey("design_challenges.id", ondelete="CASCADE")
    )
    incident_scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("incident_scenarios.id", ondelete="CASCADE")
    )
    engineering_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("eng_projects.id", ondelete="CASCADE")
    )
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    source: Mapped[EvidenceSource] = mapped_column(_enum(EvidenceSource, "evidence_source"))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # Session the attempt belonged to: independence is counted by session.
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    verified: Mapped[bool] = mapped_column(Boolean)
    dimension: Mapped[EvidenceDimension] = mapped_column(_enum(EvidenceDimension, "evidence_dimension"))
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    success: Mapped[bool] = mapped_column(Boolean)
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    said_dont_know: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class SkillMastery(Base):
    """Latest computed mastery per learner and skill (derived; safe to recompute)."""

    __tablename__ = "skill_mastery"
    __table_args__ = (
        CheckConstraint(
            "distinct_questions <= evidence_count AND verified_count <= evidence_count "
            "AND successful_attempts <= evidence_count",
            name="counts_consistent",
        ),
    )

    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[MasteryState] = mapped_column(_enum(MasteryState, "mastery_state"))
    demonstrated_level: Mapped[Difficulty | None] = mapped_column(_enum(Difficulty, "demonstrated_level"))
    # True when the demonstrated level rests on AI judgments without verified evidence.
    unverified_only: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    knowledge_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reasoning_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    debugging_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    practical_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    retention_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    uncertainty: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    inconsistent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    evidence_count: Mapped[int] = mapped_column(Integer)
    verified_count: Mapped[int] = mapped_column(Integer)
    distinct_questions: Mapped[int] = mapped_column(Integer)
    distinct_sessions: Mapped[int] = mapped_column(Integer)
    successful_attempts: Mapped[int] = mapped_column(Integer)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reasons: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MasteryEvent(Base):
    """Progress history: a change in mastery state or level. Never duplicated."""

    __tablename__ = "mastery_events"
    __table_args__ = (
        UniqueConstraint("learner_id", "skill_id", "evidence_hash"),
        Index("ix_mastery_events_learner_created", "learner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    from_state: Mapped[MasteryState | None] = mapped_column(_enum(MasteryState, "from_state"))
    to_state: Mapped[MasteryState] = mapped_column(_enum(MasteryState, "to_state"))
    from_level: Mapped[Difficulty | None] = mapped_column(_enum(Difficulty, "from_level"))
    to_level: Mapped[Difficulty | None] = mapped_column(_enum(Difficulty, "to_level"))
    reason: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class ReviewCard(Base):
    """SM-2 spaced-repetition state per learner and skill."""

    __tablename__ = "review_cards"
    __table_args__ = (
        CheckConstraint("ease >= 1.3", name="ease_floor"),
        CheckConstraint("interval_days >= 1", name="interval_positive"),
        CheckConstraint("repetitions >= 0 AND lapses >= 0 AND missed_reviews >= 0", name="counters_non_negative"),
        Index("ix_review_cards_learner_due", "learner_id", "due_at"),
    )

    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    repetitions: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    interval_days: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    ease: Mapped[Decimal] = mapped_column(Numeric(4, 2), server_default=text("2.5"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lapses: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    consecutive_lapses: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    missed_reviews: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_quality: Mapped[int | None] = mapped_column(SmallInteger)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (
        CheckConstraint("quality BETWEEN 0 AND 5", name="quality_range"),
        Index("ix_review_events_learner_skill", "learner_id", "skill_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    # One review event per piece of evidence: replaying evidence is a no-op.
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mastery_evidence.id", ondelete="CASCADE"), unique=True
    )
    quality: Mapped[int] = mapped_column(SmallInteger)
    was_due: Mapped[bool] = mapped_column(Boolean)
    overdue_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    interval_before: Mapped[int] = mapped_column(Integer)
    interval_after: Mapped[int] = mapped_column(Integer)
    due_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LearnerGoal(Base):
    __tablename__ = "learner_goals"

    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    target_level: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "target_level"))
    created_at: Mapped[datetime] = _created_at()


# --------------------------------------------------------------------------- coding lab


class CodingChallenge(Base):
    __tablename__ = "coding_challenges"
    __table_args__ = (CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    area: Mapped[str] = mapped_column(String(64), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    position: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("coding_challenge_versions.id", use_alter=True, name="fk_coding_challenges_current_version")
    )
    created_at: Mapped[datetime] = _created_at()

    skill: Mapped[Skill] = relationship()
    current_version: Mapped["CodingChallengeVersion | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )


class CodingChallengeVersion(Base):
    """Immutable snapshot of a challenge. New content means a new version."""

    __tablename__ = "coding_challenge_versions"
    __table_args__ = (
        UniqueConstraint("challenge_id", "number"),
        UniqueConstraint("challenge_id", "content_hash"),
        CheckConstraint("time_limit_ms BETWEEN 100 AND 60000", name="time_limit_range"),
        CheckConstraint("memory_limit_mb BETWEEN 32 AND 1024", name="memory_limit_range"),
        CheckConstraint("cardinality(rubric) >= 1", name="has_rubric"),
        CheckConstraint("cardinality(misconceptions) >= 1", name="has_misconceptions"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("coding_challenges.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    constraints: Mapped[list[str]] = mapped_column(ARRAY(Text))
    prerequisites: Mapped[list[str]] = mapped_column(ARRAY(Text))  # curriculum skill slugs
    entrypoint: Mapped[str] = mapped_column(String(64))
    time_limit_ms: Mapped[int] = mapped_column(Integer)
    memory_limit_mb: Mapped[int] = mapped_column(Integer)
    rubric: Mapped[list[str]] = mapped_column(ARRAY(Text))
    misconceptions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    hints: Mapped[list[str]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = _created_at()

    challenge: Mapped[CodingChallenge] = relationship(foreign_keys=[challenge_id])
    files: Mapped[list["CodingFile"]] = relationship(order_by="CodingFile.id", cascade="all, delete-orphan")
    tests: Mapped[list["CodingTestCase"]] = relationship(
        order_by="CodingTestCase.position", cascade="all, delete-orphan"
    )


class CodingFile(Base):
    """Starter code, reference solution and optional trusted test driver, per language."""

    __tablename__ = "coding_files"
    __table_args__ = (
        UniqueConstraint("version_id", "language", "role"),
        CheckConstraint("language IN ('python', 'javascript', 'typescript')", name="language_supported"),
        CheckConstraint("role IN ('starter', 'reference', 'driver')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("coding_challenge_versions.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)


class CodingTestCase(Base):
    __tablename__ = "coding_test_cases"
    __table_args__ = (
        UniqueConstraint("version_id", "name"),
        UniqueConstraint("version_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("coding_challenge_versions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(160))
    visibility: Mapped[TestVisibility] = mapped_column(_enum(TestVisibility, "test_visibility"))
    # Target called in the sandbox: the entrypoint, or "driver:<fn>".
    call: Mapped[str] = mapped_column(String(96))
    args: Mapped[list] = mapped_column(JSONB)
    # Expected outcome never enters the sandbox; compared by the trusted worker.
    expected: Mapped[dict] = mapped_column(JSONB)  # {"value": ...} or {"raises": "Name"}


class CodingDraft(Base):
    __tablename__ = "coding_drafts"
    __table_args__ = (CheckConstraint("octet_length(code) <= 262144", name="code_size"),)

    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("coding_challenges.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(16), primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    updated_at: Mapped[datetime] = _created_at()


class CodingJob(Base):
    """A queued execution request. Only the worker executes jobs."""

    __tablename__ = "coding_jobs"
    __table_args__ = (
        UniqueConstraint("learner_id", "idempotency_key"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("octet_length(code) <= 262144", name="code_size"),
        Index("ix_coding_jobs_queue", "status", "created_at"),
        Index("ix_coding_jobs_learner_created", "learner_id", text("created_at DESC")),
        Index("ix_coding_jobs_dedupe", "learner_id", "version_id", "kind", "language", "code_sha256"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("coding_challenge_versions.id", ondelete="RESTRICT"))
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind, "job_kind"))
    language: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(Text)
    code_sha256: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), server_default=JobStatus.QUEUED.value)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backend: Mapped[str | None] = mapped_column(String(16))
    sandbox_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[CodingChallengeVersion] = relationship()
    results: Mapped[list["CodingTestResult"]] = relationship(order_by="CodingTestResult.position")


class CodingTestResult(Base):
    __tablename__ = "coding_test_results"
    __table_args__ = (UniqueConstraint("job_id", "test_case_id"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_jobs.id", ondelete="CASCADE"))
    test_case_id: Mapped[int] = mapped_column(ForeignKey("coding_test_cases.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    outcome: Mapped[TestOutcome] = mapped_column(_enum(TestOutcome, "test_outcome"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # Sanitised; for hidden tests never contains inputs, outputs or expected values.
    message: Mapped[str | None] = mapped_column(Text)
    actual: Mapped[str | None] = mapped_column(Text)  # public tests only, truncated


class CodingSubmission(Base):
    """The graded outcome of a submit job."""

    __tablename__ = "coding_submissions"
    __table_args__ = (
        CheckConstraint("passed BETWEEN 0 AND total", name="passed_range"),
        CheckConstraint("NOT verified OR executed", name="verified_requires_execution"),
        Index("ix_coding_submissions_learner_created", "learner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_jobs.id", ondelete="CASCADE"), unique=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    challenge_id: Mapped[int] = mapped_column(ForeignKey("coding_challenges.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("coding_challenge_versions.id", ondelete="RESTRICT"))
    language: Mapped[str] = mapped_column(String(16))
    passed: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    all_passed: Mapped[bool] = mapped_column(Boolean)
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    executed: Mapped[bool] = mapped_column(Boolean)  # false for the mock runner
    # True only when executed by a backend whose self-verification passed.
    verified: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _created_at()

    job: Mapped[CodingJob] = relationship()


class CodingReview(Base):
    """AI code review. Subjective: never used as mastery evidence."""

    __tablename__ = "coding_reviews"
    __table_args__ = (
        CheckConstraint("status <> 'ungraded' OR error_code IS NOT NULL", name="ungraded_has_reason"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coding_submissions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus, "review_status"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    review: Mapped[dict | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    llm_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    leak_blocked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class WorkerHeartbeat(Base):
    """Execution workers report liveness and their sandbox self-verification."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    backend: Mapped[str] = mapped_column(String(16))
    verified: Mapped[bool] = mapped_column(Boolean)
    report: Mapped[dict] = mapped_column(JSONB)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- system design lab


class DesignChallenge(Base):
    __tablename__ = "design_challenges"
    __table_args__ = (CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    level: Mapped[DesignLevel] = mapped_column(_enum(DesignLevel, "design_level"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("design_challenge_versions.id", use_alter=True, name="fk_design_challenges_current_version")
    )
    created_at: Mapped[datetime] = _created_at()

    current_version: Mapped["DesignChallengeVersion | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )


class DesignChallengeVersion(Base):
    """Immutable challenge content. ``content`` is validated by app.design.challenges."""

    __tablename__ = "design_challenge_versions"
    __table_args__ = (
        UniqueConstraint("challenge_id", "number"),
        UniqueConstraint("challenge_id", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("design_challenges.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    rubric_version: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class ArchitectureProject(Base):
    __tablename__ = "architecture_projects"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("char_length(explanation) <= 20000", name="explanation_length"),
        Index("ix_architecture_projects_learner_updated", "learner_id", text("updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    challenge_id: Mapped[int] = mapped_column(ForeignKey("design_challenges.id", ondelete="RESTRICT"))
    challenge_version_id: Mapped[int] = mapped_column(ForeignKey("design_challenge_versions.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(160))
    graph: Mapped[dict] = mapped_column(JSONB)  # validated GraphDocument
    explanation: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # Optimistic concurrency: every save must name the revision it was based on.
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    challenge: Mapped[DesignChallenge] = relationship()
    challenge_version: Mapped[DesignChallengeVersion] = relationship()


class ArchitectureVersion(Base):
    """Immutable snapshot of a project's graph and explanation."""

    __tablename__ = "architecture_versions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_projects.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    graph: Mapped[dict] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    source_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class ArchitectureDecision(Base):
    """ADR. Every edit is kept in ``adr_revisions``."""

    __tablename__ = "architecture_decisions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_projects.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'proposed'"))
    content: Mapped[dict] = mapped_column(JSONB)  # validated AdrContent
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class AdrRevision(Base):
    __tablename__ = "adr_revisions"
    __table_args__ = (UniqueConstraint("decision_id", "revision"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_decisions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class DesignReview(Base):
    __tablename__ = "design_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_projects.id", ondelete="CASCADE"), index=True)
    mode: Mapped[DesignReviewMode] = mapped_column(_enum(DesignReviewMode, "design_review_mode"))
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    # Probing depth 1-3, adjusted from demonstrated reasoning.
    depth: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class DesignReviewMessage(Base):
    __tablename__ = "design_review_messages"
    __table_args__ = (
        UniqueConstraint("review_id", "seq"),
        UniqueConstraint("review_id", "client_message_id"),
        CheckConstraint("role IN ('learner', 'interviewer', 'system')", name="role_valid"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="content_length"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("design_reviews.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24))  # message | question | hint | notice | evaluation
    content: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    architecture_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("architecture_versions.id", ondelete="SET NULL")
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class DesignEvaluation(Base):
    """Rubric evaluation of one architecture version. AI judgment: unverified."""

    __tablename__ = "design_evaluations"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'evaluated', 'ungraded')", name="status_valid"),
        CheckConstraint("status <> 'evaluated' OR total_score IS NOT NULL", name="evaluated_has_score"),
        CheckConstraint("status = 'evaluated' OR total_score IS NULL", name="unevaluated_has_no_score"),
        CheckConstraint("status <> 'ungraded' OR error_code IS NOT NULL", name="ungraded_has_reason"),
        CheckConstraint("total_score IS NULL OR total_score BETWEEN 0 AND 1", name="total_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("design_reviews.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_projects.id", ondelete="CASCADE"), index=True)
    architecture_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_versions.id", ondelete="RESTRICT"))
    challenge_version_id: Mapped[int] = mapped_column(ForeignKey("design_challenge_versions.id", ondelete="RESTRICT"))
    rubric_version: Mapped[str] = mapped_column(String(32))
    evaluation_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    result: Mapped[dict | None] = mapped_column(JSONB)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mastery_eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FailureAttempt(Base):
    """An educational failure-scenario exercise. Not an infrastructure simulator."""

    __tablename__ = "failure_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'evaluated', 'ungraded')", name="status_valid"),
        CheckConstraint("status <> 'evaluated' OR score IS NOT NULL", name="evaluated_has_score"),
        CheckConstraint("status = 'evaluated' OR score IS NULL", name="unevaluated_has_no_score"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_projects.id", ondelete="CASCADE"), index=True)
    architecture_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("architecture_versions.id", ondelete="RESTRICT"))
    scenario_slug: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'open'"))
    impact: Mapped[str | None] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    result: Mapped[dict | None] = mapped_column(JSONB)
    mastery_eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- FORGE OPS (Milestone 7)

OPS_LEVEL_CHECK = "level IN ('beginner', 'intermediate', 'advanced', 'senior')"


class IncidentScenario(Base):
    __tablename__ = "incident_scenarios"
    __table_args__ = (
        CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),
        CheckConstraint(OPS_LEVEL_CHECK, name="level_valid"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("incident_scenario_versions.id", use_alter=True, name="fk_incident_scenarios_current_version")
    )
    created_at: Mapped[datetime] = _created_at()


class IncidentScenarioVersion(Base):
    """Immutable scenario content, validated by app.ops.scenario. Includes hidden fields."""
    __tablename__ = "incident_scenario_versions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "number"),
        UniqueConstraint("scenario_id", "content_hash"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("incident_scenarios.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    rubric_version: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class IncidentSession(Base):
    """One attempt at a scenario. ``state`` is the engine's SimState (server-authoritative)."""
    __tablename__ = "incident_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'investigating', 'mitigating', 'monitoring', 'resolved', 'postmortem', 'abandoned')",
            name="status_valid",
        ),
        CheckConstraint("mode IN ('guided', 'interview', 'commander', 'postmortem')", name="mode_valid"),
        CheckConstraint("char_length(notes) <= 20000", name="notes_length"),
        CheckConstraint("outcome_score IS NULL OR outcome_score BETWEEN 0 AND 1", name="outcome_range"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_incident_sessions_learner_updated", "learner_id", text("updated_at DESC")),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    scenario_id: Mapped[int] = mapped_column(ForeignKey("incident_scenarios.id", ondelete="RESTRICT"))
    version_id: Mapped[int] = mapped_column(ForeignKey("incident_scenario_versions.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16), server_default=text("'commander'"))
    state: Mapped[dict] = mapped_column(JSONB)
    notes: Mapped[str] = mapped_column(Text, server_default=text("''"))
    outcome: Mapped[dict | None] = mapped_column(JSONB)  # verified, deterministic
    outcome_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    success: Mapped[bool | None] = mapped_column(Boolean)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IncidentAction(Base):
    """Chronological audit log: every action, query, rejection and decision."""
    __tablename__ = "incident_actions"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        UniqueConstraint("session_id", "client_action_id"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    client_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(16))  # action | command | pin | unpin | hypothesis | resolve | abandon | note
    action_id: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    accepted: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status_before: Mapped[str] = mapped_column(String(16))
    status_after: Mapped[str] = mapped_column(String(16))
    condition_before: Mapped[str] = mapped_column(String(64))
    condition_after: Mapped[str] = mapped_column(String(64))
    minute_before: Mapped[int] = mapped_column(Integer)
    minute_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class IncidentSnapshot(Base):
    """Full simulation state after each state-changing action (for replay)."""
    __tablename__ = "incident_snapshots"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)  # the audit entry that produced it
    state: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class IncidentEvidence(Base):
    """Evidence the learner pinned to the investigation."""
    __tablename__ = "incident_evidence"
    __table_args__ = (CheckConstraint("char_length(note) <= 1000", name="note_length"),)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    note: Mapped[str] = mapped_column(Text, server_default=text("''"))
    pinned_at: Mapped[datetime] = _created_at()


class IncidentHypothesis(Base):
    __tablename__ = "incident_hypotheses"
    __table_args__ = (
        UniqueConstraint("session_id", "number"),
        CheckConstraint("status IN ('open', 'supported', 'rejected')", name="status_valid"),
        CheckConstraint("char_length(statement) BETWEEN 1 AND 2000", name="statement_length"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'open'"))
    evidence_ids: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class IncidentMessage(Base):
    __tablename__ = "incident_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        UniqueConstraint("session_id", "client_message_id"),
        CheckConstraint("role IN ('learner', 'commander', 'system')", name="role_valid"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="content_length"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24))  # message | question | notice | review
    mode: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cited_evidence: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class IncidentRca(Base):
    """Root-cause analysis submitted at resolution (learner text: untrusted)."""
    __tablename__ = "incident_rcas"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"), primary_key=True)
    root_cause_choice: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class IncidentEvaluation(Base):
    """AI review of an RCA or postmortem. Advisory; separate from the verified outcome."""
    __tablename__ = "incident_evaluations"
    __table_args__ = (
        CheckConstraint("kind IN ('rca', 'postmortem')", name="kind_valid"),
        CheckConstraint("status IN ('pending', 'evaluated', 'ungraded')", name="status_valid"),
        CheckConstraint("status <> 'evaluated' OR (kind = 'postmortem' OR total_score IS NOT NULL)", name="evaluated_has_score"),
        CheckConstraint("status = 'evaluated' OR total_score IS NULL", name="unevaluated_has_no_score"),
        CheckConstraint("status <> 'ungraded' OR error_code IS NOT NULL", name="ungraded_has_reason"),
        CheckConstraint("total_score IS NULL OR total_score BETWEEN 0 AND 1", name="total_range"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    result: Mapped[dict | None] = mapped_column(JSONB)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mastery_eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    rubric_version: Mapped[str] = mapped_column(String(32))
    evaluation_version: Mapped[str] = mapped_column(String(32))
    scenario_version_id: Mapped[int] = mapped_column(ForeignKey("incident_scenario_versions.id", ondelete="RESTRICT"))
    postmortem_revision: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Postmortem(Base):
    __tablename__ = "postmortems"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_sessions.id", ondelete="CASCADE"), unique=True)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class PostmortemRevision(Base):
    __tablename__ = "postmortem_revisions"
    __table_args__ = (UniqueConstraint("postmortem_id", "revision"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    postmortem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("postmortems.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


# ---------------------------------------------------------------- FORGE Career (Milestone 8)

CAREER_LEVEL_CHECK = "{col} IN ('foundation', 'junior', 'mid', 'senior')"
CAREER_TRACK_CHECK = "{col} IN ('fullstack', 'backend', 'frontend')"


class CareerProfile(Base):
    """Track, target and self-reported experience. Self-reports are context only."""
    __tablename__ = "career_profiles"
    __table_args__ = (
        CheckConstraint(CAREER_TRACK_CHECK.format(col="track"), name="track_valid"),
        CheckConstraint(CAREER_LEVEL_CHECK.format(col="target_level"), name="target_valid"),
        CheckConstraint("char_length(goal) <= 500", name="goal_length"),
    )
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    track: Mapped[str] = mapped_column(String(16))
    target_level: Mapped[str] = mapped_column(String(16))
    goal: Mapped[str] = mapped_column(Text, server_default=text("''"))
    experience: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = _created_at()


class CareerContentVersion(Base):
    """Immutable versions of the framework, templates, judgment scenarios and projects."""
    __tablename__ = "career_content_versions"
    __table_args__ = (
        UniqueConstraint("kind", "key", "number"),
        UniqueConstraint("kind", "key", "content_hash"),
        CheckConstraint("kind IN ('framework', 'template', 'judgment', 'project')", name="kind_valid"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    key: Mapped[str] = mapped_column(String(96))
    number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _created_at()


class CareerAttempt(Base):
    __tablename__ = "career_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('created', 'in_progress', 'finalized', 'expired', 'abandoned')", name="status_valid"),
        CheckConstraint("purpose IN ('formal', 'practice', 'diagnostic')", name="purpose_valid"),
        CheckConstraint(CAREER_TRACK_CHECK.format(col="track"), name="track_valid"),
        CheckConstraint(CAREER_LEVEL_CHECK.format(col="level"), name="level_valid"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_career_attempts_learner_created", "learner_id", text("created_at DESC")),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    template_version_id: Mapped[int] = mapped_column(ForeignKey("career_content_versions.id", ondelete="RESTRICT"))
    framework_version_id: Mapped[int] = mapped_column(ForeignKey("career_content_versions.id", ondelete="RESTRICT"))
    template_slug: Mapped[str] = mapped_column(String(96))
    title: Mapped[str] = mapped_column(String(200))
    track: Mapped[str] = mapped_column(String(16))
    level: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'created'"))
    time_limit_minutes: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # server-authoritative
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class CareerSection(Base):
    __tablename__ = "career_sections"
    __table_args__ = (
        UniqueConstraint("attempt_id", "key"),
        UniqueConstraint("attempt_id", "position"),
        CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'unavailable', 'skipped')", name="status_valid"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("career_attempts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    link: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))  # linked module activity
    result: Mapped[dict | None] = mapped_column(JSONB)  # snapshot at completion


class CareerResponse(Base):
    """A written answer to a judgment scenario or take-home project, with its AI review (advisory)."""
    __tablename__ = "career_responses"
    __table_args__ = (
        UniqueConstraint("section_id", "item_slug"),
        UniqueConstraint("learner_id", "client_id"),
        CheckConstraint("kind IN ('judgment', 'take_home')", name="kind_valid"),
        CheckConstraint("status IN ('pending', 'evaluated', 'ungraded')", name="status_valid"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="content_length"),
        CheckConstraint("status <> 'evaluated' OR score IS NOT NULL", name="evaluated_has_score"),
        CheckConstraint("status = 'evaluated' OR score IS NULL", name="unevaluated_has_no_score"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("career_sections.id", ondelete="CASCADE"))
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    item_slug: Mapped[str] = mapped_column(String(96))
    item_version_id: Mapped[int] = mapped_column(ForeignKey("career_content_versions.id", ondelete="RESTRICT"))
    content: Mapped[str] = mapped_column(Text)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    result: Mapped[dict | None] = mapped_column(JSONB)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    evaluation_version: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CareerReport(Base):
    """Immutable readiness report snapshot: framework version, evidence and results as evaluated."""
    __tablename__ = "career_reports"
    __table_args__ = (
        CheckConstraint("kind IN ('assessment', 'snapshot')", name="kind_valid"),
        CheckConstraint(CAREER_TRACK_CHECK.format(col="track"), name="track_valid"),
        CheckConstraint(CAREER_LEVEL_CHECK.format(col="target_level"), name="target_valid"),
        Index("ix_career_reports_learner_created", "learner_id", text("created_at DESC")),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("career_attempts.id", ondelete="CASCADE"), unique=True)
    framework_version_id: Mapped[int] = mapped_column(ForeignKey("career_content_versions.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16))
    track: Mapped[str] = mapped_column(String(16))
    target_level: Mapped[str] = mapped_column(String(16))
    demonstrated_level: Mapped[str | None] = mapped_column(String(16))
    target_status: Mapped[str] = mapped_column(String(32))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class CareerJob(Base):
    """A pasted job description (untrusted input) and its mapping to the framework."""
    __tablename__ = "career_jobs"
    __table_args__ = (
        CheckConstraint("char_length(description) BETWEEN 50 AND 20000", name="description_length"),
        Index("ix_career_jobs_learner_created", "learner_id", text("created_at DESC")),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    extraction: Mapped[dict] = mapped_column(JSONB)
    mapping: Mapped[dict] = mapped_column(JSONB)
    extraction_method: Mapped[str] = mapped_column(String(32))  # keyword | keyword+ai
    ai_error: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    template_version_id: Mapped[int | None] = mapped_column(ForeignKey("career_content_versions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()


class CareerRoadmap(Base):
    __tablename__ = "career_roadmaps"
    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("career_reports.id", ondelete="CASCADE"))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


# --------------------------------------------------------------------------- FORGE Workspace (Milestone 9)

ENG_LEVEL_CHECK = "{col} IN ('beginner', 'junior', 'mid', 'senior')"


class EngProject(Base):
    """An engineering project (one ticket on a multi-file codebase)."""

    __tablename__ = "eng_projects"
    __table_args__ = (
        CheckConstraint(SLUG_CHECK.format(col="slug"), name="slug_format"),
        CheckConstraint(ENG_LEVEL_CHECK.format(col="level"), name="level_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    level: Mapped[str] = mapped_column(String(16))
    task_type: Mapped[str] = mapped_column(String(32))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"))
    position: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("eng_project_versions.id", use_alter=True, name="fk_eng_projects_current_version")
    )
    created_at: Mapped[datetime] = _created_at()

    skill: Mapped[Skill] = relationship()
    current_version: Mapped["EngProjectVersion | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )


class EngProjectVersion(Base):
    """Immutable, content-hashed snapshot of a project template."""

    __tablename__ = "eng_project_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "number"),
        UniqueConstraint("project_id", "content_hash"),
        CheckConstraint("time_limit_ms BETWEEN 500 AND 10000", name="time_limit_range"),
        CheckConstraint("memory_limit_mb BETWEEN 64 AND 512", name="memory_limit_range"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("eng_projects.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    # Descriptive content: description, architecture, setup, ticket, stack, rubric, hints, exercises...
    content: Mapped[dict] = mapped_column(JSONB)
    rubric_version: Mapped[str] = mapped_column(String(48))
    suites: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    time_limit_ms: Mapped[int] = mapped_column(Integer)
    memory_limit_mb: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()

    project: Mapped[EngProject] = relationship(foreign_keys=[project_id])
    files: Mapped[list["EngProjectFile"]] = relationship(order_by="EngProjectFile.path", cascade="all, delete-orphan")
    tests: Mapped[list["EngProjectTest"]] = relationship(order_by="EngProjectTest.position", cascade="all, delete-orphan")


class EngProjectFile(Base):
    """Starter files, reference overrides and trusted checks ("<suite>:<visibility>")."""

    __tablename__ = "eng_project_files"
    __table_args__ = (
        UniqueConstraint("version_id", "role", "path"),
        CheckConstraint("role IN ('starter', 'reference', 'check')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)


class EngProjectTest(Base):
    __tablename__ = "eng_project_tests"
    __table_args__ = (
        UniqueConstraint("version_id", "name"),
        UniqueConstraint("version_id", "position"),
        CheckConstraint("suite IN ('python', 'node')", name="suite_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(160))
    visibility: Mapped[TestVisibility] = mapped_column(_enum(TestVisibility, "test_visibility"))
    suite: Mapped[str] = mapped_column(String(16))
    call: Mapped[str] = mapped_column(String(96))
    competency: Mapped[str] = mapped_column(String(48))
    args: Mapped[list] = mapped_column(JSONB)
    # Never enters the sandbox; compared by the trusted worker.
    expected: Mapped[dict] = mapped_column(JSONB)


class EngWorkspace(Base):
    """A learner's isolated copy of a project. Files live in eng_workspace_files."""

    __tablename__ = "eng_workspaces"
    __table_args__ = (
        UniqueConstraint("learner_id", "project_id"),
        CheckConstraint("status IN ('active', 'completed')", name="status_valid"),
        CheckConstraint("revision >= 1", name="revision_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("eng_projects.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'active'"))
    # Bumped by every file change; clients send it back to detect stale views.
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    resets: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[EngProject] = relationship()
    version: Mapped[EngProjectVersion] = relationship()
    files: Mapped[list["EngWorkspaceFile"]] = relationship(order_by="EngWorkspaceFile.path", cascade="all, delete-orphan")


class EngWorkspaceFile(Base):
    __tablename__ = "eng_workspace_files"
    __table_args__ = (
        CheckConstraint("octet_length(content) <= 65536", name="content_size"),
        CheckConstraint("revision >= 1", name="revision_positive"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(String(200), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    # Per-file optimistic concurrency: writes must name the revision they edited.
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime] = _created_at()


class EngSnapshot(Base):
    """Immutable copy of every workspace file at one moment."""

    __tablename__ = "eng_snapshots"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number"),
        CheckConstraint("kind IN ('manual', 'run', 'submission', 'pull_request')", name="kind_valid"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(120))
    files: Mapped[dict] = mapped_column(JSONB)  # {path: content}
    digest: Mapped[str] = mapped_column(String(64))
    workspace_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class EngJob(Base):
    """A queued execution of a snapshot. Only the worker executes jobs."""

    __tablename__ = "eng_jobs"
    __table_args__ = (
        UniqueConstraint("learner_id", "idempotency_key"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_eng_jobs_queue", "status", "created_at"),
        Index("ix_eng_jobs_learner_created", "learner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_snapshots.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="RESTRICT"))
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind, "job_kind"))
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), server_default=JobStatus.QUEUED.value)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backend: Mapped[str | None] = mapped_column(String(16))
    sandbox_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[EngProjectVersion] = relationship()
    snapshot: Mapped[EngSnapshot] = relationship()
    results: Mapped[list["EngTestResult"]] = relationship(order_by="EngTestResult.position")


class EngTestResult(Base):
    __tablename__ = "eng_test_results"
    __table_args__ = (UniqueConstraint("job_id", "test_id"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_jobs.id", ondelete="CASCADE"))
    test_id: Mapped[int] = mapped_column(ForeignKey("eng_project_tests.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    outcome: Mapped[TestOutcome] = mapped_column(_enum(TestOutcome, "test_outcome"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)  # hidden: redacted
    actual: Mapped[str | None] = mapped_column(Text)  # public tests only


class EngSubmission(Base):
    """The graded outcome of a submit job (all public and hidden tests)."""

    __tablename__ = "eng_submissions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number"),
        CheckConstraint("passed BETWEEN 0 AND total", name="passed_range"),
        CheckConstraint("hidden_passed BETWEEN 0 AND hidden_total", name="hidden_passed_range"),
        CheckConstraint("NOT verified OR executed", name="verified_requires_execution"),
        Index("ix_eng_submissions_learner_created", "learner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_jobs.id", ondelete="CASCADE"), unique=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_snapshots.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("eng_projects.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column(Integer)  # attempt number within the workspace
    passed: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    hidden_passed: Mapped[int] = mapped_column(Integer)
    hidden_total: Mapped[int] = mapped_column(Integer)
    all_passed: Mapped[bool] = mapped_column(Boolean)
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    executed: Mapped[bool] = mapped_column(Boolean)  # false for the mock runner
    verified: Mapped[bool] = mapped_column(Boolean)  # executed by a self-verified sandbox
    created_at: Mapped[datetime] = _created_at()

    job: Mapped[EngJob] = relationship()
    snapshot: Mapped[EngSnapshot] = relationship()


class EngReview(Base):
    """AI senior-engineer review of a submission. Advisory: never decides correctness."""

    __tablename__ = "eng_reviews"
    __table_args__ = (
        UniqueConstraint("submission_id", "mode"),
        CheckConstraint("mode IN ('guided', 'strict', 'senior', 'tech_lead')", name="mode_valid"),
        CheckConstraint("status <> 'ungraded' OR error_code IS NOT NULL", name="ungraded_has_reason"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_submissions.id", ondelete="CASCADE"))
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus, "review_status"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    review: Mapped[dict | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    rubric_version: Mapped[str] = mapped_column(String(48))
    llm_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    leak_blocked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class EngPullRequest(Base):
    """Simulated, internal pull request. Never pushed anywhere."""

    __tablename__ = "eng_pull_requests"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'changes_requested', 'approved', 'closed')", name="status_valid"),
        CheckConstraint("char_length(title) BETWEEN 5 AND 160", name="title_length"),
        CheckConstraint("char_length(description) BETWEEN 20 AND 8000", name="description_length"),
        # One open PR per workspace.
        Index("uq_eng_pull_requests_open_workspace", "workspace_id", unique=True,
              postgresql_where=text("status IN ('open', 'changes_requested')")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), server_default=text("'open'"))
    decision: Mapped[dict | None] = mapped_column(JSONB)  # last criteria evaluation
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[EngWorkspace] = relationship()
    revisions: Mapped[list["EngPrRevision"]] = relationship(order_by="EngPrRevision.number")


class EngPrRevision(Base):
    __tablename__ = "eng_pr_revisions"
    __table_args__ = (UniqueConstraint("pr_id", "number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    pr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_pull_requests.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_snapshots.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_jobs.id", ondelete="CASCADE"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    snapshot: Mapped[EngSnapshot] = relationship()
    job: Mapped[EngJob] = relationship()


class EngPrComment(Base):
    __tablename__ = "eng_pr_comments"
    __table_args__ = (
        UniqueConstraint("pr_id", "client_id"),
        CheckConstraint("author IN ('learner', 'reviewer', 'system')", name="author_valid"),
        CheckConstraint("kind IN ('comment', 'change_request', 'response')", name="kind_valid"),
        CheckConstraint(
            "category IS NULL OR category IN ('proven_failure', 'potential_concern', 'suggestion')",
            name="category_valid",
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="body_length"),
        CheckConstraint("kind <> 'response' OR parent_id IS NOT NULL", name="response_has_parent"),
        Index("ix_eng_pr_comments_pr_created", "pr_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    pr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_pull_requests.id", ondelete="CASCADE"))
    revision_number: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eng_pr_comments.id", ondelete="CASCADE"))
    review_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eng_reviews.id", ondelete="SET NULL"))
    author: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str | None] = mapped_column(String(200))
    line: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(24))
    severity: Mapped[str | None] = mapped_column(String(16))
    resolved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class EngExerciseResponse(Base):
    """Written collaboration exercise (requirement change, stakeholder update, plan...). AI-reviewed, unverified."""

    __tablename__ = "eng_exercise_responses"
    __table_args__ = (
        UniqueConstraint("learner_id", "client_id"),
        CheckConstraint("status IN ('pending', 'evaluated', 'ungraded')", name="status_valid"),
        CheckConstraint("char_length(body) BETWEEN 40 AND 12000", name="body_length"),
        CheckConstraint("status <> 'evaluated' OR score IS NOT NULL", name="evaluated_has_score"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
        Index("ix_eng_exercise_responses_learner_created", "learner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("eng_project_versions.id", ondelete="RESTRICT"))
    exercise_slug: Mapped[str] = mapped_column(String(96))
    body: Mapped[str] = mapped_column(Text)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    evaluation: Mapped[dict | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EngAuditEvent(Base):
    """Append-only log of workspace actions (edits, resets, jobs, PR decisions)."""

    __tablename__ = "eng_audit_events"
    __table_args__ = (Index("ix_eng_audit_events_learner_created", "learner_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eng_workspaces.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
