import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.seed.schema import SeedQuestion
from tests.conftest import correct_key, new_learner, next_q, start, wrong_key

ANSWER_MATERIAL = (
    "is_correct",
    "correct",
    "explanation",
    "rubric",
    "expected_concepts",
    "misconceptions",
    "resources",
)


# ---------------------------------------------------------------- session creation


def test_start_session_caps_length_to_available_questions(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "beginner")
    assert session["status"] == "active"
    assert session["skill"] == {"slug": "python", "title": "Python"}
    assert session["answered_count"] == 0
    # Python has two beginner questions; the default length (5) is capped.
    assert session["target_question_count"] == 2


def test_start_session_respects_requested_length(client: TestClient) -> None:
    h = new_learner(client)
    assert start(client, h, "sql", "beginner", question_count=1)["target_question_count"] == 1


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"skill_slug": "cobol", "difficulty": "beginner"}, 404),
        ({"skill_slug": "python", "difficulty": "expert"}, 422),
        ({"skill_slug": "python", "difficulty": "beginner", "question_count": 0}, 422),
        ({"skill_slug": "python", "difficulty": "beginner", "question_count": 21}, 422),
        ({"skill_slug": "Python!", "difficulty": "beginner"}, 422),
        ({"skill_slug": "python", "difficulty": "beginner", "learner_id": "x"}, 422),
        ({"difficulty": "beginner"}, 422),
    ],
    ids=["unknown-skill", "bad-difficulty", "zero", "too-many", "bad-slug", "extra-field", "missing"],
)
def test_start_session_rejects_invalid_input(
    client: TestClient, body: dict, status: int
) -> None:
    h = new_learner(client)
    assert client.post("/api/v1/assessments", json=body, headers=h).status_code == status


# ---------------------------------------------------------------- serving questions


def test_next_question_does_not_leak_answers(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "beginner")
    res = client.post(f"/api/v1/assessments/{session['id']}/next", headers=h)
    body = res.json()

    assert body["status"] == "question"
    question = body["item"]["question"]
    assert set(question) == {
        "slug", "title", "prompt", "code", "code_language", "hint", "format",
        "difficulty", "estimated_minutes", "topic", "options",
    }
    assert all(set(o) == {"key", "text"} for o in question["options"])
    raw = res.text
    for field in ANSWER_MATERIAL:
        assert f'"{field}"' not in raw, field


def test_next_question_is_stable_until_answered(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "react", "intermediate")
    first = next_q(client, h, session["id"])
    again = next_q(client, h, session["id"])
    assert first["item"]["id"] == again["item"]["id"]
    assert first["item"]["position"] == 1


def test_feedback_is_unavailable_before_submission(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "http", "beginner")
    item = next_q(client, h, session["id"])["item"]
    res = client.get(
        f"/api/v1/assessments/{session['id']}/items/{item['id']}/feedback", headers=h
    )
    assert res.status_code == 404
    for field in ANSWER_MATERIAL:
        assert f'"{field}"' not in res.text


# ---------------------------------------------------------------- submission & grading


def _submit(client: TestClient, h: dict, session_id: str, **body) -> "object":
    return client.post(f"/api/v1/assessments/{session_id}/answers", json=body, headers=h)


def test_correct_choice_is_graded_deterministically(
    client: TestClient, seed_questions: dict[str, SeedQuestion]
) -> None:
    h = new_learner(client)
    session = start(client, h, "sql", "beginner")
    item = next_q(client, h, session["id"])["item"]
    seed = seed_questions[item["question"]["slug"]]

    res = _submit(client, h, session["id"], item_id=item["id"], selected_option_key=correct_key(seed))
    assert res.status_code == 201, res.text
    fb = res.json()
    assert fb["evaluation"] == {
        "status": "graded",
        "method": "deterministic_choice",
        "is_correct": True,
        "score": 1.0,
        "summary": "Correct.",
    }
    assert fb["answer"]["selected_option_key"] == correct_key(seed)
    assert [o["key"] for o in fb["options"] if o["is_correct"]] == [correct_key(seed)]
    assert fb["rubric"] == list(seed.rubric)
    assert fb["expected_concepts"] and fb["misconceptions"] and fb["resources"]
    assert fb["explanation"] == seed.explanation


def test_wrong_choice_is_marked_incorrect(
    client: TestClient, seed_questions: dict[str, SeedQuestion]
) -> None:
    h = new_learner(client)
    session = start(client, h, "typescript", "beginner")
    item = next_q(client, h, session["id"])["item"]
    seed = seed_questions[item["question"]["slug"]]

    fb = _submit(
        client, h, session["id"], item_id=item["id"], selected_option_key=wrong_key(seed)
    ).json()
    assert fb["evaluation"]["is_correct"] is False
    assert fb["evaluation"]["score"] == 0.0
    assert correct_key(seed).upper() in fb["evaluation"]["summary"]


def test_free_text_is_saved_as_pending_ai_evaluation(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "advanced")
    item = next_q(client, h, session["id"])["item"]
    assert item["question"]["format"] == "free_text"
    assert item["question"]["options"] == []

    # Packing the answer with every expected keyword must not earn credit.
    text = "GIL CPU-bound I/O-bound process pool asyncio event loop semaphore " * 5
    fb = _submit(client, h, session["id"], item_id=item["id"], response_text=text).json()
    assert fb["evaluation"]["status"] == "pending_ai_evaluation"
    assert fb["evaluation"]["method"] is None
    assert fb["evaluation"]["is_correct"] is None
    assert fb["evaluation"]["score"] is None
    assert fb["answer"]["response_text"] == text.strip()
    assert len(fb["rubric"]) >= 2


def test_answer_cannot_be_submitted_twice(
    client: TestClient, seed_questions: dict[str, SeedQuestion]
) -> None:
    h = new_learner(client)
    session = start(client, h, "fastapi", "intermediate")
    item = next_q(client, h, session["id"])["item"]
    key = correct_key(seed_questions[item["question"]["slug"]])
    assert _submit(client, h, session["id"], item_id=item["id"], selected_option_key=key).status_code == 201
    second = _submit(client, h, session["id"], item_id=item["id"], selected_option_key=key)
    assert second.status_code == 409


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"selected_option_key": "a", "response_text": "both"}, 422),
        ({}, 422),
        ({"response_text": "a free-text answer to a choice question"}, 422),
        ({"selected_option_key": "f"}, 422),
        ({"selected_option_key": "z"}, 422),
        ({"selected_option_key": "a", "score": 1}, 422),
    ],
    ids=["both", "neither", "wrong-format", "missing-option", "bad-key", "extra-field"],
)
def test_invalid_choice_submissions_are_rejected(
    client: TestClient, body: dict, status: int
) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "beginner")
    item = next_q(client, h, session["id"])["item"]
    assert item["question"]["format"] == "single_choice"
    res = _submit(client, h, session["id"], item_id=item["id"], **body)
    assert res.status_code == status, res.text
    # A rejected submission must not consume the question.
    assert next_q(client, h, session["id"])["item"]["id"] == item["id"]


@pytest.mark.parametrize(
    "body",
    [{"response_text": "   \n  "}, {"response_text": "x" * 10_001}, {"selected_option_key": "a"}],
    ids=["blank", "too-long", "option-for-free-text"],
)
def test_invalid_free_text_submissions_are_rejected(client: TestClient, body: dict) -> None:
    h = new_learner(client)
    session = start(client, h, "react", "advanced")
    item = next_q(client, h, session["id"])["item"]
    assert _submit(client, h, session["id"], item_id=item["id"], **body).status_code == 422


def test_unknown_item_is_404(client: TestClient) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "beginner")
    next_q(client, h, session["id"])
    res = _submit(
        client, h, session["id"], item_id=str(uuid.uuid4()), selected_option_key="a"
    )
    assert res.status_code == 404


def test_sessions_are_private_to_their_learner(client: TestClient) -> None:
    owner, other = new_learner(client), new_learner(client)
    session = start(client, owner, "python", "beginner")
    item = next_q(client, owner, session["id"])["item"]
    sid = session["id"]
    assert client.get(f"/api/v1/assessments/{sid}", headers=other).status_code == 404
    assert client.post(f"/api/v1/assessments/{sid}/next", headers=other).status_code == 404
    res = _submit(client, other, sid, item_id=item["id"], selected_option_key="a")
    assert res.status_code == 404


# ---------------------------------------------------------------- full flow & persistence


def test_full_session_flow_persists_and_updates_progress(
    client: TestClient, seed_questions: dict[str, SeedQuestion], settings
) -> None:
    h = new_learner(client)
    session = start(client, h, "python", "intermediate")  # 1 choice + 1 free text
    sid = session["id"]
    outcomes = []
    while (step := next_q(client, h, sid))["status"] == "question":
        q = step["item"]["question"]
        body = (
            {"selected_option_key": correct_key(seed_questions[q["slug"]])}
            if q["format"] == "single_choice"
            else {"response_text": "Shallow copies share inner objects; deep copies do not."}
        )
        fb = _submit(client, h, sid, item_id=step["item"]["id"], **body).json()
        outcomes.append(fb["evaluation"]["status"])
    assert sorted(outcomes) == ["graded", "pending_ai_evaluation"]

    assert step["session"]["status"] == "completed"
    assert step["session"]["answered_count"] == 2

    # A brand-new client (like a page refresh or server restart) sees saved state.
    from app.main import create_app

    with TestClient(create_app(settings)) as fresh:
        assert fresh.get(f"/api/v1/assessments/{sid}", headers=h).json()["status"] == "completed"
        history = fresh.get("/api/v1/answers", headers=h).json()
        assert len(history) == 2
        by_session = fresh.get("/api/v1/answers", params={"session": sid}, headers=h).json()
        assert {a["answer_id"] for a in by_session} == {a["answer_id"] for a in history}
        assert fresh.get(
            "/api/v1/answers", params={"session": str(uuid.uuid4())}, headers=h
        ).json() == []
        assert {a["evaluation_status"] for a in history} == {"graded", "pending_ai_evaluation"}
        for a in history:
            fb = fresh.get(
                f"/api/v1/assessments/{a['session_id']}/items/{a['item_id']}/feedback",
                headers=h,
            )
            assert fb.status_code == 200

        progress = {p["skill"]["slug"]: p for p in fresh.get("/api/v1/progress", headers=h).json()["skills"]}
    py = progress["python"]
    assert py["sessions_started"] == 1
    assert py["sessions_completed"] == 1
    assert py["answers_submitted"] == 2
    assert py["objective_graded"] == 1
    assert py["objective_correct"] == 1
    assert py["pending_ai_evaluation"] == 1
    assert progress["sql"]["answers_submitted"] == 0


def test_new_sessions_prefer_unseen_questions(client: TestClient) -> None:
    h = new_learner(client)
    first = start(client, h, "sql", "beginner", question_count=1)
    q1 = next_q(client, h, first["id"])["item"]
    _submit(client, h, first["id"], item_id=q1["id"], selected_option_key="a")

    second = start(client, h, "sql", "beginner", question_count=1)
    q2 = next_q(client, h, second["id"])["item"]
    assert q2["question"]["slug"] != q1["question"]["slug"]


def test_progress_for_new_learner_is_all_zero(client: TestClient) -> None:
    h = new_learner(client)
    body = client.get("/api/v1/progress", headers=h).json()
    assert len(body["skills"]) == 13  # every curriculum skill, assessable or not
    for p in body["skills"]:
        assert p["answers_submitted"] == 0
        assert p["last_activity_at"] is None
    # No mastery or score estimate is exposed.
    assert "mastery" not in json.dumps(body)
