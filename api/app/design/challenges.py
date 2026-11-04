"""Versioned system design challenges: app/design/challenges/*.toml."""

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import DesignLevel
from app.db.models import DesignChallenge, DesignChallengeVersion, Skill
from app.design.catalog import COMPETENCIES, CRITERIA, FAILURE_SCENARIOS, RUBRIC_VERSION

CHALLENGE_DIR = Path(__file__).resolve().parent / "challenges"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
Items = list[str]


class ChallengeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(pattern=SLUG)
    title: str = Field(min_length=5, max_length=160)
    skills: Items = Field(min_length=1)  # curriculum skills, primary first
    competencies: Items = Field(min_length=1)
    prerequisites: Items = Field(default_factory=list)
    business_context: str = Field(min_length=40)
    functional: Items = Field(min_length=2)
    non_functional: Items = Field(min_length=2)
    scale: Items = Field(min_length=1)  # hypothetical, labelled as such
    reliability: Items = Field(min_length=1)
    security: Items = Field(min_length=1)
    constraints: Items = Field(min_length=1)
    hints: Items = Field(min_length=2, max_length=3)
    failure_scenarios: Items = Field(min_length=2)
    # Hidden until the learner's first completed evaluation:
    expected_concepts: Items = Field(min_length=3)
    rubric_focus: dict[str, str] = Field(min_length=3)
    common_mistakes: Items = Field(min_length=2)
    follow_ups: Items = Field(min_length=2)

    @model_validator(mode="after")
    def _valid(self) -> Self:
        if unknown := set(self.competencies) - COMPETENCIES:
            raise ValueError(f"{self.slug}: unknown competencies {sorted(unknown)}")
        if unknown := set(self.rubric_focus) - set(CRITERIA):
            raise ValueError(f"{self.slug}: unknown rubric criteria {sorted(unknown)}")
        if unknown := set(self.failure_scenarios) - set(FAILURE_SCENARIOS):
            raise ValueError(f"{self.slug}: unknown failure scenarios {sorted(unknown)}")
        if not any(s.lower().startswith("hypothetical") for s in self.scale):
            raise ValueError(f"{self.slug}: scale figures must be labelled as hypothetical")
        return self

    def content_hash(self) -> str:
        payload = {"spec": self.model_dump(), "rubric": RUBRIC_VERSION}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class LevelFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: DesignLevel
    challenges: list[ChallengeSpec] = Field(min_length=1)


PUBLIC_FIELDS = (
    "business_context", "functional", "non_functional", "scale", "reliability", "security",
    "constraints", "skills", "competencies", "prerequisites", "failure_scenarios",
)
HIDDEN_FIELDS = ("expected_concepts", "rubric_focus", "common_mistakes", "follow_ups")


def load_challenges(directory: Path = CHALLENGE_DIR) -> list[tuple[DesignLevel, ChallengeSpec]]:
    out = []
    for path in sorted(directory.glob("*.toml")):
        f = LevelFile.model_validate(tomllib.loads(path.read_text()))
        out += [(f.level, c) for c in f.challenges]
    slugs = [c.slug for _, c in out]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate design challenge slugs")
    return out


async def sync_challenges(db: AsyncSession, specs: list[tuple[DesignLevel, ChallengeSpec]]) -> int:
    skills = {s.slug for s in (await db.scalars(select(Skill))).all()}
    created = 0
    seen = set()
    for position, (level, spec) in enumerate(specs):
        if missing := (set(spec.skills) | set(spec.prerequisites)) - skills:
            raise ValueError(f"{spec.slug}: unknown skills {sorted(missing)}")
        ch = await db.scalar(select(DesignChallenge).where(DesignChallenge.slug == spec.slug))
        if ch is None:
            ch = DesignChallenge(slug=spec.slug, level=level, position=position)
            db.add(ch)
            await db.flush()
        ch.level, ch.position, ch.is_active = level, position, True
        digest = spec.content_hash()
        version = await db.scalar(select(DesignChallengeVersion).where(
            DesignChallengeVersion.challenge_id == ch.id, DesignChallengeVersion.content_hash == digest))
        if version is None:
            number = (await db.scalar(select(func.max(DesignChallengeVersion.number)).where(
                DesignChallengeVersion.challenge_id == ch.id)) or 0) + 1
            version = DesignChallengeVersion(
                challenge_id=ch.id, number=number, content_hash=digest, rubric_version=RUBRIC_VERSION,
                title=spec.title, content=spec.model_dump(),
            )
            db.add(version)
            await db.flush()
            created += 1
        ch.current_version_id = version.id
        seen.add(spec.slug)
    await db.execute(update(DesignChallenge).where(DesignChallenge.slug.not_in(seen)).values(is_active=False))
    await db.flush()
    return created
