"""End-to-end learner journeys through the HTTP API (fake LLM, mock sandbox).

One learner goes from nothing to diagnosis, learning path, practice,
interview, project work and reassessment, and the evidence rules hold at
every step: nothing is invented, unverified AI judgments stay separate from
verified evidence, and mock execution never counts.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.coding.sandbox import MockSandbox
from app.llm.fake import FakeProvider
from app.main import create_app
from tests.conftest import _execute, new_learner
from tests.interview_fixtures import FIXTURES, strong
from tests.test_mastery_api import _answer_session, _skill
from tests.test_workspace import drain


def test_diagnosis_to_learning_practice_and_reassessment(settings, seed_questions) -> None:
    asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
    fake = FakeProvider()
    s = settings.model_copy(update={"sandbox_backend": "mock", "llm_provider": "openai_compatible"})
    with TestClient(create_app(s, llm=fake)) as c:
        h = new_learner(c)

        # 1. A new learner has no invented mastery or readiness.
        assert _skill(c, h, "python")["state"] == "not_started"
        career = c.get("/api/v1/career/dashboard", headers=h).json()
        assert career["readiness"]["target"]["status"] != "ready"
        assert career["insufficient_message"]

        # 2. Diagnosis: one wrong answer is recorded, but it is not enough to judge a level.
        _answer_session(c, h, seed_questions, "python", "beginner", correct=False)
        py = _skill(c, h, "python")
        assert py["state"] == "insufficient_evidence" and py["demonstrated_level"] is None

        # 3. The learning path explains what evidence is still missing.
        recs = c.get("/api/v1/recommendations", headers=h).json()
        assert recs and all(r["reasons"] for r in recs)

        # 4. Practice: independent successes demonstrate the beginner level.
        _answer_session(c, h, seed_questions, "python", "beginner")
        _answer_session(c, h, seed_questions, "python", "beginner")
        _answer_session(c, h, seed_questions, "python", "beginner")
        py = _skill(c, h, "python")
        assert py["demonstrated_level"] == "beginner", py

        # 5. An AI interview adds unverified evidence only, never verified.
        f = FIXTURES[0]
        sid = c.post("/api/v1/interviews", headers=h, json={
            "skill_slug": f.skill, "difficulty": f.difficulty, "mode": f.mode, "challenge_count": 1,
        }).json()["session"]["id"]
        fake.queue(strong(f))
        res = c.post(f"/api/v1/interviews/{sid}/answers", headers=h,
                     json={"client_turn_id": str(uuid.uuid4()), "content": f.answer})
        assert res.status_code == 200, res.text
        py = _skill(c, h, "python")
        assert py["evidence_count"] > py["verified_count"]  # interview evidence counted as unverified

        # 6. Project work run by the mock runner is never evidence.
        ws = c.post("/api/v1/workspace/projects/task-api-status-codes/workspace", headers=h).json()
        job = c.post(f"/api/v1/workspace/workspaces/{ws['id']}/jobs", headers=h,
                     json={"kind": "submit", "idempotency_key": str(uuid.uuid4())}).json()
        drain(s, MockSandbox())
        done = c.get(f"/api/v1/workspace/jobs/{job['id']}", headers=h).json()
        assert done["status"] == "completed" and not done["sandbox_verified"]
        assert _skill(c, h, "fastapi")["verified_count"] == 0

        # 7. Reassessment: answered questions are scheduled for spaced review.
        queue = c.get("/api/v1/reviews", headers=h).json()
        assert queue["total_due"] + len(queue["upcoming"]) > 0

        # 8. Career readiness names what is missing instead of guessing.
        career = c.get("/api/v1/career/dashboard", headers=h).json()
        assert career["readiness"]["target"]["status"] != "ready"
        assert career["engineering_projects"]["projects"][0]["unverified_attempts"] == 1
