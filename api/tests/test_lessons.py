"""Lessons: content API, read tracking, recommendations, and the rule that reading is not mastery."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.curriculum.graph import load_curriculum
from app.main import create_app
from app.seed.lessons import LESSON_DIR, load_lessons, parse_lesson
from app.seed.schema import load_seed_files
from tests.conftest import new_learner


def _count(settings, sql: str) -> int:
    async def run():
        conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
        try:
            return await conn.fetchval(sql)
        finally:
            await conn.close()

    return asyncio.run(run())


# ---------------------------------------------------------------- content validation


def test_committed_lessons_validate():
    curriculum, _ = load_curriculum()
    slugs = {q.slug for f in load_seed_files() for q in f.questions}
    lessons = load_lessons(curriculum, slugs)
    assert len(lessons) >= 10
    assert all(x.status in {"reviewed", "verified"} for x in lessons)


def _write(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")


def _lesson_text(slug: str, prereqs: str = "[]", checks: str = '["py-mutable-default-argument"]', drop: str | None = None) -> str:
    sections = [
        "Why it matters", "Mental model", "How it works", "Worked example", "Common mistakes",
        "In production", "Trade-offs and limits", "Check your understanding", "Practice",
    ]
    body = "\n\n".join(f"## {s}\n\n" + ("Explanation text. " * 12) for s in sections if s != drop)
    return (
        f'+++\nslug = "{slug}"\nskill = "python"\ntopic = "functions"\ndifficulty = "beginner"\n'
        f'title = "A lesson"\nsummary = "A summary that is long enough."\nestimated_minutes = 10\n'
        f'objectives = ["One", "Two"]\nprerequisites = {prereqs}\nmisconceptions = ["One", "Two"]\n'
        f'checks = {checks}\nstatus = "reviewed"\nversion = 1\nprovenance = "test fixture"\n'
        f'[[resources]]\ntitle = "Python docs"\nurl = "https://docs.python.org/3/"\n+++\n{body}\n'
    )


def test_lesson_validation_rejects_bad_content(tmp_path):
    curriculum, _ = load_curriculum()
    slugs = {q.slug for f in load_seed_files() for q in f.questions}

    _write(tmp_path, "a.md", _lesson_text("lesson-a", drop="Practice"))
    with pytest.raises(ValueError, match="missing sections"):
        load_lessons(curriculum, slugs, tmp_path)

    _write(tmp_path, "a.md", _lesson_text("lesson-a", checks='["no-such-question"]'))
    with pytest.raises(ValueError, match="unknown check questions"):
        load_lessons(curriculum, slugs, tmp_path)

    _write(tmp_path, "a.md", _lesson_text("lesson-a", prereqs='["lesson-b"]'))
    _write(tmp_path, "b.md", _lesson_text("lesson-b", prereqs='["lesson-a"]'))
    with pytest.raises(ValueError, match="cycle"):
        load_lessons(curriculum, slugs, tmp_path)


def test_every_lesson_parses_with_required_sections():
    for path in sorted(LESSON_DIR.glob("*.md")):
        lesson = parse_lesson(path)
        assert lesson.body.count("## ") >= 9, path.name


# ---------------------------------------------------------------- API


def test_list_and_detail(client: TestClient):
    lessons = client.get("/api/v1/lessons").json()
    assert len(lessons) >= 10
    assert {"slug", "title", "summary", "skill", "difficulty", "estimated_minutes", "status"} <= lessons[0].keys()
    only_http = client.get("/api/v1/lessons", params={"skill": "http"}).json()
    assert only_http and all(x["skill"]["slug"] == "http" for x in only_http)

    detail = client.get("/api/v1/lessons/security-auth-and-injection").json()
    assert [p["slug"] for p in detail["prerequisites"]] == [
        "http-requests-and-semantics", "fastapi-validation-and-dependencies"
    ]
    assert {c["slug"] for c in detail["checks"]} == {
        "sec-idor-invoice", "sec-parameterised-query", "sec-react-xss-bio"
    }
    assert detail["objectives"] and detail["misconceptions"] and detail["resources"]
    assert "## Worked example" in detail["body"]
    assert client.get("/api/v1/lessons/does-not-exist").status_code == 404


def test_read_tracking_is_idempotent_and_keeps_first_completion(client: TestClient):
    h = new_learner(client)
    assert client.get("/api/v1/lesson-progress", headers=h).json() == []
    opened = client.post("/api/v1/lessons/tracing-program-state/open", headers=h).json()
    assert opened["completed_at"] is None
    again = client.post("/api/v1/lessons/tracing-program-state/open", headers=h).json()
    assert again["first_opened_at"] == opened["first_opened_at"]
    done = client.post("/api/v1/lessons/tracing-program-state/complete", headers=h).json()
    redo = client.post("/api/v1/lessons/tracing-program-state/complete", headers=h).json()
    assert done["completed_at"] is not None and redo["completed_at"] == done["completed_at"]
    progress = client.get("/api/v1/lesson-progress", headers=h).json()
    assert [p["slug"] for p in progress] == ["tracing-program-state"]
    assert client.post("/api/v1/lessons/nope/complete", headers=h).status_code == 404


def test_reading_lessons_creates_no_mastery_evidence(client: TestClient, settings):
    h = new_learner(client)
    before = _count(settings, "select count(*) from mastery_evidence")
    for slug in [x["slug"] for x in client.get("/api/v1/lessons").json()]:
        assert client.post(f"/api/v1/lessons/{slug}/complete", headers=h).status_code == 200
    assert _count(settings, "select count(*) from mastery_evidence") == before
    overview = client.get("/api/v1/mastery", headers=h).json()
    assert all(s["evidence_count"] == 0 for s in overview["skills"])


def test_recommendations_suggest_unread_lessons(client: TestClient):
    h = new_learner(client)
    first = client.get("/api/v1/recommendations", headers=h).json()[0]
    assert first["skill"]["slug"] == "programming-fundamentals"
    assert first["lesson"]["slug"] == "tracing-program-state"
    assert first["activity"]["type"] == "assessment"  # the activity itself is unchanged
    client.post("/api/v1/lessons/tracing-program-state/complete", headers=h)
    after = client.get("/api/v1/recommendations", headers=h).json()[0]
    assert after["skill"]["slug"] == "programming-fundamentals"
    assert after["lesson"] is None  # no other unread lesson for this skill and level


def test_learner_lesson_routes_are_private_and_local_only(client: TestClient, settings):
    assert client.get("/api/v1/lesson-progress").status_code == 401
    assert client.post("/api/v1/lessons/tracing-program-state/complete").status_code == 401
    h = new_learner(client)
    with TestClient(create_app(settings), client=("198.51.100.4", 4000)) as remote:
        assert remote.get("/api/v1/lesson-progress", headers=h).status_code == 403
        assert remote.post("/api/v1/lessons/tracing-program-state/open", headers=h).status_code == 403
        assert remote.get("/api/v1/lessons").status_code == 200  # public content, like the curriculum
