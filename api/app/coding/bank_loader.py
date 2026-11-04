"""Versioned coding challenge bank: ``app/coding/bank/*.toml``.

Challenges are authored and verified by hand (see tests/test_coding_bank.py,
which runs every reference solution through the real sandbox). A change to a
challenge's content creates a new immutable version; past jobs keep pointing at
the version they ran against.
"""

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Difficulty, TestVisibility
from app.db.models import CodingChallenge, CodingChallengeVersion, CodingFile, CodingTestCase, Skill

BANK_DIR = Path(__file__).resolve().parent / "bank"
LANGUAGES = ("python", "javascript", "typescript")
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BankLanguage(_Strict):
    starter: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class BankDriver(_Strict):
    code: str = Field(min_length=1)


class BankTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=160)
    visibility: TestVisibility
    call: str | None = Field(default=None, pattern=r"^(driver:)?[A-Za-z_][A-Za-z0-9_]*$")
    args: list[Any] = Field(default_factory=list)
    args_json: str | None = None
    expected: Any = None
    expected_json: str | None = None
    raises: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

    @model_validator(mode="after")
    def _one_outcome(self) -> Self:
        given = [k for k in ("expected", "expected_json", "raises") if k in self.model_fields_set]
        if len(given) != 1:
            raise ValueError(f"{self.name}: give exactly one of expected, expected_json, raises")
        if self.args_json is not None and "args" in self.model_fields_set:
            raise ValueError(f"{self.name}: give args or args_json, not both")
        return self

    def resolved_args(self) -> list:
        return json.loads(self.args_json) if self.args_json is not None else list(self.args)

    def outcome(self) -> dict:
        if self.raises:
            return {"raises": self.raises}
        if self.expected_json is not None:
            return {"value": json.loads(self.expected_json)}
        return {"value": self.expected}


class BankChallenge(_Strict):
    slug: str = Field(pattern=SLUG, max_length=96)
    title: str = Field(min_length=3, max_length=160)
    area: str = Field(pattern=SLUG)
    skill: str = Field(pattern=SLUG)
    prerequisites: list[str] = Field(default_factory=list)
    difficulty: Difficulty
    entrypoint: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    time_limit_ms: int = Field(ge=100, le=10_000)
    memory_limit_mb: int = Field(ge=32, le=512)
    description: str = Field(min_length=20)
    constraints: list[str] = Field(min_length=1)
    rubric: list[str] = Field(min_length=2)
    misconceptions: list[str] = Field(min_length=1)
    hints: list[str] = Field(min_length=1, max_length=3)
    languages: dict[str, BankLanguage] = Field(min_length=1)
    driver: dict[str, BankDriver] = Field(default_factory=dict)
    tests: list[BankTest] = Field(min_length=3)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        unknown = (set(self.languages) | set(self.driver)) - set(LANGUAGES)
        if unknown:
            raise ValueError(f"{self.slug}: unsupported languages {sorted(unknown)}")
        if not set(self.driver) <= set(self.languages):
            raise ValueError(f"{self.slug}: driver for a language the challenge doesn't offer")
        names = [t.name for t in self.tests]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.slug}: duplicate test names")
        vis = {t.visibility for t in self.tests}
        if vis != {TestVisibility.PUBLIC, TestVisibility.HIDDEN}:
            raise ValueError(f"{self.slug}: needs at least one public and one hidden test")
        if any(t.call and t.call.startswith("driver:") for t in self.tests) and not self.driver:
            raise ValueError(f"{self.slug}: driver calls without a driver")
        return self

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def load_bank(bank_dir: Path = BANK_DIR) -> list[BankChallenge]:
    paths = sorted(bank_dir.glob("*.toml"))
    challenges = [BankChallenge.model_validate(tomllib.loads(p.read_text())) for p in paths]
    slugs = [c.slug for c in challenges]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate challenge slugs in bank")
    return challenges


async def sync_bank(db: AsyncSession, challenges: list[BankChallenge]) -> dict[str, int]:
    skills = {s.slug: s for s in (await db.scalars(select(Skill))).all()}
    created_versions = 0
    seen: set[str] = set()
    for position, c in enumerate(challenges):
        if c.skill not in skills:
            raise ValueError(f"{c.slug}: unknown skill '{c.skill}'")
        missing = set(c.prerequisites) - set(skills)
        if missing:
            raise ValueError(f"{c.slug}: unknown prerequisite skills {sorted(missing)}")
        challenge = await db.scalar(select(CodingChallenge).where(CodingChallenge.slug == c.slug))
        if challenge is None:
            challenge = CodingChallenge(slug=c.slug, area=c.area, skill_id=skills[c.skill].id,
                                        difficulty=c.difficulty, position=position)
            db.add(challenge)
            await db.flush()
        challenge.area, challenge.skill_id = c.area, skills[c.skill].id
        challenge.difficulty, challenge.position, challenge.is_active = c.difficulty, position, True

        digest = c.content_hash()
        version = await db.scalar(
            select(CodingChallengeVersion).where(
                CodingChallengeVersion.challenge_id == challenge.id,
                CodingChallengeVersion.content_hash == digest,
            )
        )
        if version is None:
            number = (await db.scalar(
                select(func.max(CodingChallengeVersion.number)).where(CodingChallengeVersion.challenge_id == challenge.id)
            ) or 0) + 1
            version = CodingChallengeVersion(
                challenge_id=challenge.id, number=number, content_hash=digest, title=c.title,
                description=c.description.strip(), constraints=c.constraints, prerequisites=c.prerequisites,
                entrypoint=c.entrypoint, time_limit_ms=c.time_limit_ms, memory_limit_mb=c.memory_limit_mb,
                rubric=c.rubric, misconceptions=c.misconceptions, hints=c.hints,
            )
            version.files = [
                CodingFile(language=lang, role=role, content=getattr(spec, role).strip("\n") + "\n")
                for lang, spec in c.languages.items()
                for role in ("starter", "reference")
            ] + [CodingFile(language=lang, role="driver", content=d.code.strip("\n") + "\n") for lang, d in c.driver.items()]
            version.tests = [
                CodingTestCase(
                    position=i, name=t.name, visibility=t.visibility, call=t.call or c.entrypoint,
                    args=t.resolved_args(), expected=t.outcome(),
                )
                for i, t in enumerate(c.tests)
            ]
            db.add(version)
            await db.flush()
            created_versions += 1
        challenge.current_version_id = version.id
        seen.add(c.slug)
    await db.execute(
        update(CodingChallenge).where(CodingChallenge.slug.not_in(seen)).values(is_active=False)
    )
    await db.flush()
    return {"challenges": len(challenges), "new_versions": created_versions}
