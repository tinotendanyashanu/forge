"""Per-item option shuffling: stable presentation, correct grading, intact history."""

import asyncio
import uuid
from collections import Counter
from types import SimpleNamespace

import asyncpg
from fastapi.testclient import TestClient

from app.seed.schema import SeedQuestion
from app.services.option_order import key_for_option, option_for_key, presented_options
from tests.conftest import correct_key, new_learner, next_q, start, wrong_key


def _opts(n: int = 4):
    return [SimpleNamespace(id=100 + i, key="abcd"[i]) for i in range(n)]


def _fetch(settings, sql: str, *args):
    async def run():
        conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(run())


# ---------------------------------------------------------------- unit


def test_presentation_is_deterministic_per_item():
    item = uuid.uuid4()
    first = [(k, o.id) for k, o in presented_options(item, _opts())]
    again = [(k, o.id) for k, o in presented_options(item, list(reversed(_opts())))]
    assert first == again  # independent of input order, stable for the same item
    assert [k for k, _ in first] == ["a", "b", "c", "d"]  # relabelled by position


def test_presentation_spreads_the_authored_correct_option():
    # The authored "b" (id 101) must land on every displayed position, roughly evenly.
    positions = Counter(
        key_for_option(uuid.uuid4(), _opts(), 101) for _ in range(4000)
    )
    assert set(positions) == {"a", "b", "c", "d"}
    assert all(800 <= n <= 1200 for n in positions.values()), positions


def test_key_mapping_round_trips():
    item = uuid.uuid4()
    for key, option in presented_options(item, _opts()):
        assert option_for_key(item, _opts(), key).id == option.id
        assert key_for_option(item, _opts(), option.id) == key
    assert option_for_key(item, _opts(), "f") is None
    assert key_for_option(item, _opts(), None) is None


# ---------------------------------------------------------------- API


def test_refresh_does_not_reshuffle_and_feedback_matches(client: TestClient, settings, seed_questions):
    h = new_learner(client)
    s = start(client, h, "sql", "beginner")
    item = next_q(client, h, s["id"])["item"]
    again = next_q(client, h, s["id"])["item"]  # refresh before answering
    assert again["id"] == item["id"]
    assert again["question"]["options"] == item["question"]["options"]

    seed = seed_questions[item["question"]["slug"]]
    res = client.post(
        f"/api/v1/assessments/{s['id']}/answers",
        json={"item_id": item["id"], "selected_option_key": correct_key(seed, item)},
        headers=h,
    )
    assert res.status_code == 201 and res.json()["evaluation"]["is_correct"] is True
    fb = client.get(f"/api/v1/assessments/{s['id']}/items/{item['id']}/feedback", headers=h).json()
    shown = [(o["key"], o["text"]) for o in item["question"]["options"]]
    assert [(o["key"], o["text"]) for o in fb["options"]] == shown
    assert [(o["key"], o["text"]) for o in fb["question"]["options"]] == shown


def test_grading_stores_the_real_option_id(client: TestClient, settings, seed_questions):
    h = new_learner(client)
    s = start(client, h, "http", "beginner")
    item = next_q(client, h, s["id"])["item"]
    seed: SeedQuestion = seed_questions[item["question"]["slug"]]
    key = wrong_key(seed, item)
    assert client.post(
        f"/api/v1/assessments/{s['id']}/answers",
        json={"item_id": item["id"], "selected_option_key": key},
        headers=h,
    ).status_code == 201

    chosen_text = next(o["text"] for o in item["question"]["options"] if o["key"] == key)
    rows = _fetch(
        settings,
        "select o.key, o.text, o.is_correct, e.is_correct as graded "
        "from answers a join question_options o on o.id = a.selected_option_id "
        "join evaluation_results e on e.answer_id = a.id where a.session_item_id = $1",
        uuid.UUID(item["id"]),
    )
    assert len(rows) == 1
    assert rows[0]["text"] == chosen_text  # the option the learner saw is the one stored
    assert rows[0]["is_correct"] is False and rows[0]["graded"] is False


def test_authored_key_is_not_trusted(client: TestClient, settings, seed_questions):
    """Submitting the authored correct key only scores if it is also the displayed correct key."""
    seen = 0
    for _ in range(12):
        h = new_learner(client)
        s = start(client, h, "react", "beginner")
        item = next_q(client, h, s["id"])["item"]
        seed = seed_questions[item["question"]["slug"]]
        authored = next(o.key for o in seed.options if o.correct)
        if authored == correct_key(seed, item):
            continue
        seen += 1
        fb = client.post(
            f"/api/v1/assessments/{s['id']}/answers",
            json={"item_id": item["id"], "selected_option_key": authored},
            headers=h,
        ).json()
        assert fb["evaluation"]["is_correct"] is False
    assert seen > 0  # with 12 random items at least one is displaced (p ≈ 1 - 0.25^12)


def test_history_stored_before_shuffling_still_reads_correctly(client: TestClient, settings, seed_questions):
    """Answers keep option ids, so feedback for an existing answer shows the option actually chosen."""
    h = new_learner(client)
    s = start(client, h, "python", "beginner")
    item = next_q(client, h, s["id"])["item"]
    seed = seed_questions[item["question"]["slug"]]
    client.post(
        f"/api/v1/assessments/{s['id']}/answers",
        json={"item_id": item["id"], "selected_option_key": correct_key(seed, item)},
        headers=h,
    )
    stored = _fetch(
        settings,
        "select o.text from answers a join question_options o on o.id = a.selected_option_id "
        "where a.session_item_id = $1",
        uuid.UUID(item["id"]),
    )[0]["text"]
    fb = client.get(f"/api/v1/assessments/{s['id']}/items/{item['id']}/feedback", headers=h).json()
    picked = next(o for o in fb["options"] if o["key"] == fb["answer"]["selected_option_key"])
    assert picked["text"] == stored and picked["is_correct"] is True
