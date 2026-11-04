"""Global LLM spending cap and per-learner interview limit."""

import asyncio

import pytest

from app.core.config import Settings
from app.llm.base import ChatMessage, CompletionRequest, ProviderRateLimited
from app.llm.budget import BudgetedProvider
from app.llm.factory import build_provider
from app.llm.fake import FakeProvider

REQ = CompletionRequest(messages=[ChatMessage("user", "hi")])


def test_budget_blocks_calls_over_the_hourly_cap_and_recovers() -> None:
    now = [0.0]
    inner = FakeProvider(["a", "b", "c"])
    p = BudgetedProvider(inner, 2, clock=lambda: now[0])

    async def go():
        assert (await p.complete(REQ)).text == "a"
        assert (await p.complete(REQ)).text == "b"
        with pytest.raises(ProviderRateLimited):
            await p.complete(REQ)
        assert len(inner.requests) == 2  # the blocked call never reached the provider
        now[0] = 3601.0
        assert (await p.complete(REQ)).text == "c"

    asyncio.run(go())


def test_factory_wraps_real_providers_only() -> None:
    on = build_provider(Settings(llm_provider="ollama", llm_model="m", llm_max_calls_per_hour=5))
    assert isinstance(on, BudgetedProvider) and on.max_calls == 5
    off = build_provider(Settings(llm_provider="ollama", llm_model="m", llm_max_calls_per_hour=0))
    assert not isinstance(off, BudgetedProvider)
    assert build_provider(Settings(llm_provider="disabled")).name == "disabled"


def test_interview_evaluations_are_limited_per_learner(settings) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import _execute, new_learner
    from tests.interview_fixtures import FIXTURES

    asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
    f = FIXTURES[0]
    fake = FakeProvider()
    with TestClient(create_app(settings.model_copy(update={"interview_llm_calls_per_hour": 1}), llm=fake)) as c:
        h = new_learner(c)
        sid = c.post("/api/v1/interviews", headers=h, json={
            "skill_slug": f.skill, "difficulty": f.difficulty, "mode": f.mode, "challenge_count": 2}).json()["session"]["id"]
        fake.queue("not json", "still not json")  # one ungraded evaluation (one repair attempt)
        first = c.post(f"/api/v1/interviews/{sid}/answers", headers=h,
                       json={"client_turn_id": "11111111-1111-4111-8111-111111111111", "content": f.answer})
        assert first.status_code == 200, first.text
        calls = len(fake.requests)
        second = c.post(f"/api/v1/interviews/{sid}/answers", headers=h,
                        json={"client_turn_id": "22222222-2222-4222-8222-222222222222", "content": f.answer})
        assert second.status_code == 429
        assert len(fake.requests) == calls  # refused before any model call
