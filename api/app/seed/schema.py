"""Validation for authored seed content in ``app/seed/content/*.json``.

These rules are stricter than the database constraints: they encode the
editorial requirements every question must meet before it can be loaded.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import Difficulty, QuestionFormat

CONTENT_DIR = Path(__file__).resolve().parent / "content"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
MIN_TOTAL_QUESTIONS = 30


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SeedOption(_Strict):
    key: str = Field(pattern=r"^[a-f]$")
    text: str = Field(min_length=1)
    correct: bool = False


class SeedResource(_Strict):
    title: str = Field(min_length=3, max_length=200)
    url: str = Field(pattern=r"^https://\S+$", max_length=500)


class SeedQuestion(_Strict):
    slug: str = Field(pattern=SLUG, max_length=96)
    topic: str = Field(pattern=SLUG)
    difficulty: Difficulty
    format: QuestionFormat
    title: str = Field(min_length=3, max_length=160)
    prompt: str = Field(min_length=10)
    code: str | None = None
    code_language: str | None = Field(default=None, max_length=32)
    hint: str | None = None
    options: list[SeedOption] = Field(default_factory=list)
    explanation: str = Field(min_length=20)
    acceptance_criteria: str = Field(min_length=10)
    rubric: list[str] = Field(min_length=2)
    expected_concepts: list[str] = Field(min_length=1)
    misconceptions: list[str] = Field(min_length=1)
    resources: list[SeedResource] = Field(min_length=1)
    estimated_minutes: int = Field(ge=1, le=120)

    @model_validator(mode="after")
    def _check_format(self) -> Self:
        if self.code_language and not self.code:
            raise ValueError(f"{self.slug}: code_language set without code")
        if self.format is QuestionFormat.SINGLE_CHOICE:
            if not 2 <= len(self.options) <= 6:
                raise ValueError(f"{self.slug}: single_choice needs 2–6 options")
            keys = [o.key for o in self.options]
            if len(set(keys)) != len(keys):
                raise ValueError(f"{self.slug}: duplicate option keys")
            if sum(o.correct for o in self.options) != 1:
                raise ValueError(f"{self.slug}: single_choice needs exactly one correct option")
        elif self.options:
            raise ValueError(f"{self.slug}: free_text questions must not have options")
        return self


class SeedSkill(_Strict):
    slug: str = Field(pattern=SLUG, max_length=64)
    title: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=10)
    description: str = Field(min_length=10)


class SeedTopic(_Strict):
    slug: str = Field(pattern=SLUG, max_length=64)
    title: str = Field(min_length=2, max_length=120)


class SeedSkillFile(_Strict):
    skill: SeedSkill
    topics: list[SeedTopic] = Field(min_length=1)
    questions: list[SeedQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        topic_slugs = [t.slug for t in self.topics]
        if len(set(topic_slugs)) != len(topic_slugs):
            raise ValueError(f"{self.skill.slug}: duplicate topic slug")
        unknown = {q.topic for q in self.questions} - set(topic_slugs)
        if unknown:
            raise ValueError(f"{self.skill.slug}: unknown topics {sorted(unknown)}")
        missing = set(Difficulty) - {q.difficulty for q in self.questions}
        if missing:
            raise ValueError(
                f"{self.skill.slug}: no questions for {sorted(d.value for d in missing)}"
            )
        return self


def load_seed_files(content_dir: Path = CONTENT_DIR) -> list[SeedSkillFile]:
    """Reads and validates every content file, ordered by filename."""
    paths = sorted(content_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"No seed content found in {content_dir}")
    files = [
        SeedSkillFile.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in paths
    ]

    skill_dupes = [s for s, n in Counter(f.skill.slug for f in files).items() if n > 1]
    if skill_dupes:
        raise ValueError(f"Duplicate skill slugs: {skill_dupes}")
    question_dupes = [
        s for s, n in Counter(q.slug for f in files for q in f.questions).items() if n > 1
    ]
    if question_dupes:
        raise ValueError(f"Duplicate question slugs: {question_dupes}")
    total = sum(len(f.questions) for f in files)
    if total < MIN_TOTAL_QUESTIONS:
        raise ValueError(f"Expected at least {MIN_TOTAL_QUESTIONS} questions, found {total}")
    return files
