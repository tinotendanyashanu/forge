"""Coding lab API + worker integration against PostgreSQL."""

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.coding.grading import MARK
from app.coding.sandbox import DockerSandbox, SandboxUnavailable, Verification
from app.coding.worker import Worker
from app.db.session import create_engine, create_sessionmaker
from app.llm.base import ProviderTimeout
from app.llm.fake import FakeProvider
from app.main import create_app
from tests.conftest import _execute, new_learner

SLUG = "run-length-encoding"
GOOD = "# PASS\ndef encode(text):\n    ...\n"
BAD = "def encode(text):\n    return ''\n"


class ScriptedSandbox:
    """Test double: echoes expected values for '# PASS' code, wrong values otherwise.

    Expected values are looked up from the DB by the test, never given to the
    sandbox by the worker; this double is only for exercising the job flow.
    """

    name = "docker"
    executes = True

    def __init__(self, expected: dict[int, dict], fail_times: int = 0, verified: bool = True) -> None:
        self.expected, self.fail_times, self.verified, self.calls = expected, fail_times, verified, 0

    async def verify(self) -> Verification:
        return Verification("docker", self.verified, True, languages={"python": self.verified})

    async def run(self, req):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise SandboxUnavailable("daemon restarting")
        good = "# PASS" in req.code
        lines = []
        for c in req.cases:
            exp = self.expected[c.id]
            if good and "raises" in exp:
                lines.append({"id": c.id, "ok": False, "error": {"type": exp["raises"], "message": "", "phase": "call"}, "ms": 1})
            else:
                lines.append({"id": c.id, "ok": True, "value": exp.get("value") if good else "wrong", "ms": 1})
        from app.coding.sandbox import ExecResult
        return ExecResult("".join(MARK + json.dumps(x) + "\n" for x in lines), 0, False, False, 5)


async def _fetch(settings, sql: str) -> list[tuple]:
    engine = create_engine(settings.require_database_url())
    try:
        async with engine.connect() as conn:
            return [tuple(r) for r in (await conn.execute(text(sql))).all()]
    finally:
        await engine.dispose()


def expected_map(settings) -> dict[int, dict]:
    rows = asyncio.run(_fetch(settings, "SELECT id, expected FROM coding_test_cases"))
    return {i: e for i, e in rows}


def drain(settings, sandbox, *, worker_id: str | None = None) -> Worker:
    async def go():
        engine = create_engine(settings.require_database_url())
        try:
            w = Worker(settings, create_sessionmaker(engine), sandbox=sandbox)
            if worker_id:
                w.id = worker_id
            await w.verify()
            while await w.run_once():
                pass
            return w
        finally:
            await engine.dispose()
    return asyncio.run(go())


@pytest.fixture
def lab_settings(settings):
    return settings.model_copy(update={"sandbox_backend": "docker", "sandbox_allow_container_isolation": True,
                                       "coding_runs_per_minute": 3, "coding_max_active_jobs": 2})


@pytest.fixture
def lab(lab_settings) -> Iterator[TestClient]:
    asyncio.run(_execute(lab_settings.require_database_url(), "TRUNCATE learners, worker_heartbeats CASCADE"))
    with TestClient(create_app(lab_settings, llm=FakeProvider())) as c:
        yield c


def job(c, h, code=GOOD, kind="submit", key=None, slug=SLUG):
    return c.post("/api/v1/coding/jobs", headers=h, json={
        "challenge_slug": slug, "language": "python", "code": code, "kind": kind,
        "idempotency_key": key or str(uuid.uuid4())})


# ---------------------------------------------------------------- catalogue confidentiality


def test_catalogue_never_exposes_hidden_tests_or_reference(lab: TestClient) -> None:
    listing = lab.get("/api/v1/coding/challenges").json()
    assert len(listing) == 19 and all(c["hidden_tests"] > 0 for c in listing)
    detail = lab.get(f"/api/v1/coding/challenges/{SLUG}")
    body = detail.json()
    assert body["examples"] and all(e["args"] for e in body["examples"])
    assert "Repeated letters separated by others are separate runs" in body["hidden_test_names"]
    assert "aabaa" not in detail.text  # hidden input
    assert "parts.append" not in detail.text  # reference solution
    assert "misconceptions" not in body


def test_filters(lab: TestClient) -> None:
    ts = lab.get("/api/v1/coding/challenges", params={"language": "typescript"}).json()
    assert {c["slug"] for c in ts} == {"parse-user", "todo-reducer"}
    sec = lab.get("/api/v1/coding/challenges", params={"skill": "security"}).json()
    assert {c["area"] for c in sec} == {"auth", "security"}


# ---------------------------------------------------------------- execution gating


def test_disabled_backend_refuses_jobs(settings) -> None:
    asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
    with TestClient(create_app(settings)) as c:  # default: disabled
        h = new_learner(c)
        assert job(c, h).status_code == 503
        assert c.get("/api/v1/coding/status").json()["accepts_jobs"] is False


def test_mock_backend_runs_nothing_and_creates_no_evidence(settings) -> None:
    mock = settings.model_copy(update={"sandbox_backend": "mock"})
    asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
    with TestClient(create_app(mock)) as c:
        h = new_learner(c)
        jid = job(c, h).json()["id"]
        from app.coding.sandbox import MockSandbox
        drain(mock, MockSandbox())
        j = c.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
        assert j["status"] == "completed" and j["sandbox_verified"] is False
        assert {r["outcome"] for r in j["results"]} == {"not_executed"}
        sub = c.get(f"/api/v1/coding/submissions/{j['submission_id']}", headers=h).json()
        assert sub["executed"] is False and sub["verified"] is False and sub["all_passed"] is False
        evidence = c.get("/api/v1/mastery/programming-fundamentals", headers=h).json()["evidence"]
        assert evidence == []


def test_unverified_sandbox_blocks_jobs(lab, lab_settings) -> None:
    h = new_learner(lab)
    jid = job(lab, h).json()["id"]
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings), verified=False))
    j = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
    assert j["status"] == "blocked" and j["error_code"] == "sandbox_unverified"


# ---------------------------------------------------------------- validation & limits


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"code": ""}, 422), ({"code": "   \n"}, 422), ({"code": "x" * 70_000}, 422),
        ({"language": "ruby"}, 422), ({"kind": "deploy"}, 422), ({"challenge_slug": "nope"}, 404),
        ({"language": "javascript"}, 422), ({"extra": 1}, 422),
    ],
)
def test_malformed_jobs_are_rejected(lab, body, code) -> None:
    h = new_learner(lab)
    payload = {"challenge_slug": SLUG, "language": "python", "code": GOOD, "kind": "run",
               "idempotency_key": str(uuid.uuid4()), **body}
    assert lab.post("/api/v1/coding/jobs", headers=h, json=payload).status_code == code


def test_rate_limits_and_active_job_cap(lab) -> None:
    h = new_learner(lab)
    assert job(lab, h, kind="run").status_code == 202
    assert job(lab, h, kind="run").status_code == 202
    capped = job(lab, h, kind="run")
    assert capped.status_code == 429 and "in progress" in capped.json()["detail"]


def test_runs_per_minute_limit(lab, lab_settings) -> None:
    h = new_learner(lab)
    sb = ScriptedSandbox(expected_map(lab_settings))
    for _ in range(3):
        assert job(lab, h, kind="run").status_code == 202
        drain(lab_settings, sb)
    assert job(lab, h, kind="run").status_code == 429


def test_idempotency_key_replays_the_same_job(lab) -> None:
    h = new_learner(lab)
    key = str(uuid.uuid4())
    first, again = job(lab, h, key=key), job(lab, h, key=key)
    assert first.status_code == 202 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]


# ---------------------------------------------------------------- running, grading, visibility


def test_run_uses_public_tests_and_submit_uses_all(lab, lab_settings) -> None:
    h = new_learner(lab)
    run_id = job(lab, h, kind="run").json()["id"]
    sub_id = job(lab, h, kind="submit").json()["id"]
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings)))
    run = lab.get(f"/api/v1/coding/jobs/{run_id}", headers=h).json()
    assert {r["visibility"] for r in run["results"]} == {"public"} and run["submission_id"] is None
    sub = lab.get(f"/api/v1/coding/jobs/{sub_id}", headers=h).json()
    assert sub["passed"] == sub["total"] == 6 and sub["submission_id"]
    for r in sub["results"]:
        if r["visibility"] == "hidden":
            assert r["args"] is None and r["expected"] is None and r["actual"] is None


def test_failed_hidden_tests_reveal_nothing(lab, lab_settings) -> None:
    h = new_learner(lab)
    jid = job(lab, h, code=BAD).json()["id"]
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings)))
    res = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h)
    hidden = [r for r in res.json()["results"] if r["visibility"] == "hidden"]
    assert all(r["outcome"] == "failed" and r["actual"] is None for r in hidden)
    assert "aabaa" not in res.text and "a2b1a2" not in res.text


def test_reference_is_revealed_only_after_a_verified_pass(lab, lab_settings) -> None:
    h = new_learner(lab)
    sb = ScriptedSandbox(expected_map(lab_settings))
    job(lab, h, code=BAD)
    drain(lab_settings, sb)
    state = lab.get(f"/api/v1/coding/challenges/{SLUG}/state", headers=h).json()
    assert state["solved"] is False and state["reference_solutions"] is None and state["misconceptions"] is None
    job(lab, h, code=GOOD)
    drain(lab_settings, sb)
    state = lab.get(f"/api/v1/coding/challenges/{SLUG}/state", headers=h).json()
    assert state["solved"] and "parts.append" in state["reference_solutions"]["python"]


# ---------------------------------------------------------------- reliability


def test_infrastructure_failures_are_retried_then_succeed(lab, lab_settings) -> None:
    h = new_learner(lab)
    jid = job(lab, h).json()["id"]
    sb = ScriptedSandbox(expected_map(lab_settings), fail_times=1)
    drain(lab_settings, sb)
    j = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
    assert j["status"] == "completed" and j["attempts"] == 2
    assert asyncio.run(_fetch(lab_settings, f"SELECT count(*) FROM coding_submissions WHERE job_id = '{jid}'"))[0][0] == 1


def test_persistent_infrastructure_failure_fails_the_job(lab, lab_settings) -> None:
    h = new_learner(lab)
    jid = job(lab, h).json()["id"]
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings), fail_times=99))
    j = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
    assert j["status"] == "failed" and j["attempts"] == lab_settings.job_max_attempts


def test_expired_lease_is_reclaimed_and_stale_worker_cannot_finish(lab, lab_settings) -> None:
    h = new_learner(lab)
    jid = job(lab, h).json()["id"]
    # Simulate a crashed worker holding an expired lease.
    asyncio.run(_execute(lab_settings.require_database_url(), f"""
        UPDATE coding_jobs SET status = 'running', worker_id = 'dead-worker', attempts = 1,
               lease_expires_at = now() - interval '1 minute' WHERE id = '{jid}'"""))
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings)), worker_id="healthy")
    j = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
    assert j["status"] == "completed" and j["attempts"] == 2

    # The dead worker coming back can't overwrite the completed job.
    async def stale_finish():
        engine = create_engine(lab_settings.require_database_url())
        try:
            w = Worker(lab_settings, create_sessionmaker(engine), sandbox=ScriptedSandbox({}))
            w.id = "dead-worker"
            return await w._finish(uuid.UUID(jid), status="failed")
        finally:
            await engine.dispose()
    assert asyncio.run(stale_finish()) is False


# ---------------------------------------------------------------- mastery integration


def test_verified_submissions_become_practical_evidence_once(lab, lab_settings) -> None:
    h = new_learner(lab)
    sb = ScriptedSandbox(expected_map(lab_settings))
    job(lab, h, code=GOOD)
    drain(lab_settings, sb)
    # Resubmitting identical code returns the same job: no duplicate evidence.
    again = job(lab, h, code=GOOD)
    assert again.status_code == 200
    drain(lab_settings, sb)
    detail = lab.get("/api/v1/mastery/programming-fundamentals", headers=h).json()
    assert len(detail["evidence"]) == 1
    e = detail["evidence"][0]
    assert e["source"] == "coding_submission" and e["verified"] and e["dimension"] == "practical"
    assert detail["mastery"]["practical_score"] == 1.0
    assert detail["mastery"]["knowledge_accuracy"] is None  # practical is tracked separately
    first = lab.post("/api/v1/mastery/recalculate", headers=h).json()
    assert first == {"new_evidence": 0, "skills_recomputed": 0, "events_created": 0}


def test_two_challenges_demonstrate_a_level_and_failures_recommend_retry(lab, lab_settings) -> None:
    h = new_learner(lab)
    sb = ScriptedSandbox(expected_map(lab_settings))
    job(lab, h, code=GOOD)
    job(lab, h, code=GOOD.replace("encode", "two_sum"), slug="two-sum-indices")
    drain(lab_settings, sb)
    pf = lab.get("/api/v1/mastery/programming-fundamentals", headers=h).json()["mastery"]
    assert pf["state"] == "developing" and pf["demonstrated_level"] == "beginner"

    job(lab, h, code=BAD, slug="merge-intervals")
    drain(lab_settings, sb)
    recs = lab.get("/api/v1/recommendations", headers=h).json()
    retry = [r for r in recs if r["kind"] == "practical_retry"]
    assert retry and retry[0]["activity"]["challenge_slug"] == "merge-intervals"
    assert "hidden tests" in retry[0]["reasons"][0]


# ---------------------------------------------------------------- drafts, hints, authorization


def test_drafts_autosave_with_revision_conflicts(lab) -> None:
    h = new_learner(lab)
    url = f"/api/v1/coding/challenges/{SLUG}/draft"
    d1 = lab.put(url, headers=h, json={"language": "python", "code": "a"}).json()
    d2 = lab.put(url, headers=h, json={"language": "python", "code": "b", "base_revision": d1["revision"]}).json()
    assert d2["revision"] == 2
    stale = lab.put(url, headers=h, json={"language": "python", "code": "c", "base_revision": 1})
    assert stale.status_code == 409
    assert lab.get(f"/api/v1/coding/challenges/{SLUG}/state", headers=h).json()["drafts"]["python"]["code"] == "b"


def test_hints_are_progressive_and_bounded(lab) -> None:
    h = new_learner(lab)
    url = f"/api/v1/coding/challenges/{SLUG}/hints"
    assert len(lab.post(url, headers=h, json={"language": "python"}).json()["hints"]) == 1
    assert len(lab.post(url, headers=h, json={"language": "python"}).json()["hints"]) == 2
    assert lab.post(url, headers=h, json={"language": "python"}).status_code == 409


def test_jobs_and_submissions_are_private_and_local_only(lab, lab_settings) -> None:
    owner, other = new_learner(lab), new_learner(lab)
    jid = job(lab, owner).json()["id"]
    drain(lab_settings, ScriptedSandbox(expected_map(lab_settings)))
    sid = lab.get(f"/api/v1/coding/jobs/{jid}", headers=owner).json()["submission_id"]
    assert lab.get(f"/api/v1/coding/jobs/{jid}", headers=other).status_code == 404
    assert lab.get(f"/api/v1/coding/submissions/{sid}", headers=other).status_code == 404
    assert lab.post(f"/api/v1/coding/submissions/{sid}/review", headers=other).status_code == 404
    assert lab.get("/api/v1/coding/submissions").status_code == 401
    with TestClient(create_app(lab_settings), client=("203.0.113.9", 1)) as remote:
        assert remote.post("/api/v1/coding/jobs", headers=owner, json={}).status_code == 403
        assert remote.get("/api/v1/coding/challenges").status_code == 200  # public catalogue


# ---------------------------------------------------------------- AI review


def review_json(**kw) -> str:
    return json.dumps({
        "summary": "Clear structure; consider the empty-input path.",
        "findings": [{"dimension": "correctness", "severity": "major", "line": 2, "message": "Empty input returns the wrong value."}],
        "strengths": ["Readable names"], "follow_up_questions": ["What happens when the input is empty?"],
        "hints": ["Handle the final run after the loop."], "confidence": 0.7, **kw})


@pytest.fixture
def reviewed(lab_settings):
    fake = FakeProvider()
    asyncio.run(_execute(lab_settings.require_database_url(), "TRUNCATE learners CASCADE"))
    with TestClient(create_app(lab_settings, llm=fake)) as c:
        h = new_learner(c)
        jid = job(c, h, code=BAD).json()["id"]
        drain(lab_settings, ScriptedSandbox(expected_map(lab_settings)))
        sid = c.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()["submission_id"]
        yield c, h, sid, fake


def test_review_is_grounded_and_never_sees_secrets(reviewed) -> None:
    c, h, sid, fake = reviewed
    fake.queue(review_json())
    body = c.post(f"/api/v1/coding/submissions/{sid}/review", headers=h).json()
    review = body["review"]["review"]
    assert body["review"]["status"] == "completed"
    assert review["grounding"].startswith("Hidden tests: 0 of 6 passed")
    assert "does not prove" in review["grounding"]
    prompt = " ".join(m.content for m in fake.requests[0].messages)
    assert "parts.append" not in prompt  # reference solution
    assert "aabaa" not in prompt  # hidden test input
    assert "<submission>" in prompt
    # Idempotent: a completed review is returned without calling the model again.
    c.post(f"/api/v1/coding/submissions/{sid}/review", headers=h)
    assert len(fake.requests) == 1


def test_review_leaking_the_reference_is_trimmed(reviewed) -> None:
    c, h, sid, fake = reviewed
    leak = "parts.append(f\"{current}{count}\") then current, count = ch, 1 and return \"\".join(parts)"
    fake.queue(review_json(hints=[leak], findings=[{"dimension": "correctness", "severity": "major", "line": 99, "message": "Fine here."}]))
    body = c.post(f"/api/v1/coding/submissions/{sid}/review", headers=h).json()
    assert body["review"]["leak_blocked"] is True
    assert body["review"]["review"]["hints"] == []
    assert body["review"]["review"]["findings"][0]["line"] is None  # out-of-range line dropped


@pytest.mark.parametrize("failure", ["not json", ProviderTimeout("slow")], ids=["malformed", "timeout"])
def test_review_failures_are_ungraded_and_retryable(reviewed, failure) -> None:
    c, h, sid, fake = reviewed
    # Malformed output is repaired once (two calls); provider errors aren't repaired.
    fake.queue(*([failure, failure] if isinstance(failure, str) else [failure]))
    body = c.post(f"/api/v1/coding/submissions/{sid}/review", headers=h).json()
    assert body["review"]["status"] == "ungraded" and body["review"]["review"] is None
    fake.queue(review_json())
    assert c.post(f"/api/v1/coding/submissions/{sid}/review", headers=h).json()["review"]["status"] == "completed"


# ---------------------------------------------------------------- real sandbox, end to end


def test_end_to_end_with_real_docker_worker(lab, lab_settings) -> None:
    sb = DockerSandbox(lab_settings)
    if not asyncio.run(sb.verify()).verified:
        pytest.skip("Docker sandbox not verified")
    from app.coding.bank_loader import load_bank

    reference = next(c for c in load_bank() if c.slug == SLUG).languages["python"].reference
    h = new_learner(lab)
    jid = job(lab, h, code=reference).json()["id"]
    drain(lab_settings, sb)
    j = lab.get(f"/api/v1/coding/jobs/{jid}", headers=h).json()
    assert j["status"] == "completed" and j["sandbox_verified"] and j["passed"] == j["total"] == 6
    status = lab.get("/api/v1/coding/status").json()
    assert status["verified"] and status["worker_online"] and status["executes_code"]
    ev = lab.get("/api/v1/mastery/programming-fundamentals", headers=h).json()["evidence"]
    assert ev[0]["source"] == "coding_submission" and ev[0]["verified"]
