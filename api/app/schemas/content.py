from pydantic import BaseModel, ConfigDict

from app.db.enums import Difficulty, QuestionFormat


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DifficultyCounts(_Out):
    beginner: int = 0
    intermediate: int = 0
    advanced: int = 0


class TopicOut(_Out):
    slug: str
    title: str
    question_count: int


class SkillSummary(_Out):
    slug: str
    title: str
    summary: str
    position: int
    topic_count: int
    question_count: int
    questions_by_difficulty: DifficultyCounts


class SkillDetail(SkillSummary):
    description: str
    topics: list[TopicOut]


class SkillRef(_Out):
    slug: str
    title: str


class TopicRef(_Out):
    slug: str
    title: str


class OptionPublic(_Out):
    """An answer option without any indication of correctness."""

    key: str
    text: str


class QuestionPublic(_Out):
    """What a learner may see before answering. Contains no answer material."""

    slug: str
    title: str
    prompt: str
    code: str | None
    code_language: str | None
    hint: str | None
    format: QuestionFormat
    difficulty: Difficulty
    estimated_minutes: int
    topic: TopicRef
    options: list[OptionPublic]
