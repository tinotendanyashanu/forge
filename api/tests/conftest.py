"""Test setup: a real PostgreSQL database, migrated with Alembic and seeded.

Requires FORGE_TEST_DATABASE_URL (see api/.env.example). Tests are skipped,
not silently passed, when it is missing.
"""

import asyncio
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import create_engine
from app.main import create_app
from app.seed.__main__ import main as seed_main
from app.seed.schema import SeedQuestion, load_seed_files

API_DIR = Path(__file__).resolve().parent.parent


def _test_settings() -> Settings:
    base = Settings()
    url = base.test_database_url
    if not url:
        pytest.skip("FORGE_TEST_DATABASE_URL is not set", allow_module_level=True)
    if url == base.database_url:
        raise RuntimeError("FORGE_TEST_DATABASE_URL must differ from FORGE_DATABASE_URL")
    return base.model_copy(
        update={
            "database_url": url,
            # Starlette's TestClient reports its client host as "testclient".
            "local_only_allowed_hosts": [*base.local_only_allowed_hosts, "testclient"],
            "llm_provider": "disabled",
        }
    )


def _alembic(*args: str, url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"database_url={url}", *args],
        cwd=API_DIR,
        check=True,
        capture_output=True,
    )


async def _execute(url: str, sql: str) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def settings() -> Settings:
    s = _test_settings()
    url = s.require_database_url()
    # Exercise the migration in both directions on every run.
    _alembic("downgrade", "base", url=url)
    _alembic("upgrade", "head", url=url)
    asyncio.run(seed_main(url))
    return s


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # Learner data cascades to sessions, items, answers, evaluations and progress.
    asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture(scope="session")
def seed_questions() -> dict[str, SeedQuestion]:
    return {q.slug: q for f in load_seed_files() for q in f.questions}


def new_learner(client: TestClient) -> dict[str, str]:
    res = client.post("/api/v1/learners")
    assert res.status_code == 201, res.text
    return {"X-Learner-Id": res.json()["id"]}


def start(
    client: TestClient, headers: dict[str, str], skill: str, difficulty: str, **extra: Any
) -> dict[str, Any]:
    res = client.post(
        "/api/v1/assessments",
        json={"skill_slug": skill, "difficulty": difficulty, **extra},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def next_q(client: TestClient, headers: dict[str, str], session_id: str) -> dict[str, Any]:
    res = client.post(f"/api/v1/assessments/{session_id}/next", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def correct_key(q: SeedQuestion) -> str:
    return next(o.key for o in q.options if o.correct)


def wrong_key(q: SeedQuestion) -> str:
    return next(o.key for o in q.options if not o.correct)
