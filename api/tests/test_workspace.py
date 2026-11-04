"""FORGE Workspace (Milestone 9): projects, workspaces, jobs, reviews, PRs, evidence.

Most tests run against PostgreSQL with test doubles for the sandbox and a fake
LLM. Tests marked ``real_sandbox`` execute in the hardened Docker sandbox and
are skipped (not silently passed) when it can't verify itself.
"""

import asyncio
import json
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from app.coding.grading import MARK, CaseResult
from app.coding.sandbox import DockerSandbox, ExecResult, SandboxUnavailable, Verification
from app.coding.worker import Worker
from app.db.enums import TestOutcome
from app.db.session import create_engine, create_sessionmaker
from app.llm.base import ProviderTimeout
from app.llm.fake import FakeProvider
from app.main import create_app
from app.services.errors import Unprocessable
from app.workspace import paths
from app.workspace.content import load_projects
from app.workspace.execution import _redact_hidden
from tests.conftest import _execute, new_learner
from tests.test_coding_api import _fetch

SLUG = "task-api-status-codes"
API = "/api/v1/workspace"
PROJECT = next(p for p in load_projects() if p.slug == SLUG)


# ---------------------------------------------------------------- helpers


class ProjectDouble:
    """Sandbox double for project jobs: 'passes' every test whose expected value it is
    given by the test (looked up from the DB), only when the workspace contains the
    reference fix. The worker never hands expected values to a sandbox."""

    name = "docker"
    executes = True

    def __init__(self, expected: dict[int, dict], *, fail_times: int = 0, verified: bool = True) -> None:
        self.expected, self.fail_times, self.verified, self.calls = expected, fail_times, verified, []

    async def verify(self) -> Verification:
        return Verification("docker", self.verified, True, languages={"python": self.verified, "javascript": self.verified})

    async def run_project(self, req):
        self.calls.append(req)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise SandboxUnavailable("daemon restarting")
        fixed = "HTTP_404_NOT_FOUND" in req.files.get("app/routes/tasks.py", "")
        lines = [{"id": c.id, "ok": True, "value": self.expected[c.id]["value"] if fixed else "wrong", "ms": 1}
                 for c in req.cases]
        return ExecResult("".join(MARK + json.dumps(x) + "\n" for x in lines), 0, False, False, 5)


def expected_map(settings) -> dict[int, dict]:
    return {i: e for i, e in asyncio.run(_fetch(settings, "SELECT id, expected FROM eng_project_tests"))}


def drain(settings, sandbox) -> Worker:
    async def go():
        engine = create_engine(settings.require_database_url())
        try:
            w = Worker(settings, create_sessionmaker(engine), sandbox=sandbox)
            await w.verify()
            while await w.run_once():
                pass
            return w
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture
def mk(settings):
    """Builds a client with the given settings overrides and LLM."""
    clients = []

    def make(llm=None, **overrides) -> TestClient:
        asyncio.run(_execute(settings.require_database_url(), "TRUNCATE learners CASCADE"))
        c = TestClient(create_app(settings.model_copy(update=overrides), llm=llm))
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def open_ws(client, headers) -> dict:
    res = client.post(f"{API}/projects/{SLUG}/workspace", headers=headers)
    assert res.status_code in (200, 201), res.text
    return res.json()


def read(client, headers, ws_id, path) -> dict:
    res = client.get(f"{API}/workspaces/{ws_id}/files/{path}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def write(client, headers, ws_id, path, content, base):
    return client.put(f"{API}/workspaces/{ws_id}/files", headers=headers,
                      json={"path": path, "content": content, "base_revision": base})


def apply_reference(client, headers, ws_id) -> None:
    for path, content in PROJECT.reference.items():
        f = read(client, headers, ws_id, path)
        assert write(client, headers, ws_id, path, content, f["revision"]).status_code == 200


def job(client, headers, ws_id, kind, key=None):
    return client.post(f"{API}/workspaces/{ws_id}/jobs", headers=headers,
                       json={"kind": kind, "idempotency_key": str(key or uuid.uuid4())})


# ---------------------------------------------------------------- content


def test_project_library_validates_and_hides_hidden_material(mk) -> None:
    client = mk()
    listing = client.get(f"{API}/projects").json()
    assert {p["slug"] for p in listing} >= {SLUG}
    d = client.get(f"{API}/projects/{SLUG}").json()
    assert d["ticket"]["acceptance_criteria"] and d["rubric_version"] and d["exercises"]
    assert d["hidden_test_names"] and all("args" in t for t in d["public_tests_detail"])
    assert set(d["public_check_sources"]) == {"python"}
    body = json.dumps(d)
    hidden = [t for t in PROJECT.tests if t.visibility.value == "hidden"]
    assert PROJECT.checks["python:hidden"] not in body
    # No hidden inputs or expected values, and no reference solution.
    assert all(json.dumps(t.resolved_args()) not in body for t in hidden)
    assert "HTTP_404_NOT_FOUND" not in body


def test_every_project_has_reference_changes_and_both_test_kinds() -> None:
    projects = load_projects()
    assert len(projects) >= 3
    for p in projects:
        assert p.reference and {t.visibility.value for t in p.tests} == {"public", "hidden"}
        assert set(p.reference) <= set(p.reference_tree())


# ---------------------------------------------------------------- workspace files


def test_open_is_idempotent_and_copies_starter(mk) -> None:
    client = mk()
    h = new_learner(client)
    first = client.post(f"{API}/projects/{SLUG}/workspace", headers=h)
    again = client.post(f"{API}/projects/{SLUG}/workspace", headers=h)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert {f["path"] for f in first.json()["files"]} == set(PROJECT.starter)
    assert all(f["status"] == "unchanged" for f in first.json()["files"])
    assert read(client, h, first.json()["id"], "app/main.py")["content"] == PROJECT.starter["app/main.py"]


def test_edit_create_delete_and_concurrent_edit_protection(mk) -> None:
    client = mk()
    h = new_learner(client)
    ws = open_ws(client, h)
    f = read(client, h, ws["id"], "app/models.py")
    ok = write(client, h, ws["id"], "app/models.py", f["content"] + "\n# edited\n", f["revision"])
    assert ok.status_code == 200 and ok.json()["revision"] == f["revision"] + 1
    # A second tab still holding the old revision can't overwrite the newer edit.
    stale = write(client, h, ws["id"], "app/models.py", "lost update", f["revision"])
    assert stale.status_code == 409
    assert read(client, h, ws["id"], "app/models.py")["content"].endswith("# edited\n")
    # Create, then refuse to "create" over an existing file.
    assert write(client, h, ws["id"], "tests/test_extra.py", "def test_x():\n    pass\n", None).status_code == 200
    assert write(client, h, ws["id"], "tests/test_extra.py", "x", None).status_code == 409
    detail = client.get(f"{API}/workspaces/{ws['id']}", headers=h).json()
    status = {x["path"]: x["status"] for x in detail["files"]}
    assert status["tests/test_extra.py"] == "added" and status["app/models.py"] == "modified"
    # Delete needs the current revision.
    rev = read(client, h, ws["id"], "tests/test_extra.py")["revision"]
    assert client.post(f"{API}/workspaces/{ws['id']}/files/delete", headers=h,
                       json={"path": "tests/test_extra.py", "base_revision": rev + 5}).status_code == 409
    assert client.post(f"{API}/workspaces/{ws['id']}/files/delete", headers=h,
                       json={"path": "tests/test_extra.py", "base_revision": rev}).status_code == 204
    diff = client.get(f"{API}/workspaces/{ws['id']}/diff", headers=h).json()
    assert [d["path"] for d in diff] == ["app/models.py"] and diff[0]["additions"] == 2


@pytest.mark.parametrize("path", [
    "../escape.py", "/etc/passwd.py", "app/../../x.py", "app/./x.py", ".env.py", "app/.hidden/x.py",
    "a\\b.py", "x.exe", "app//x.py", "a/b/c/d/e/f/g.py", "x.py\x00.txt", "",
])
def test_unsafe_paths_are_rejected(mk, path) -> None:
    client = mk()
    h = new_learner(client)
    ws = open_ws(client, h)
    res = write(client, h, ws["id"], path, "x = 1\n", None)
    assert res.status_code == 422, (path, res.text)


def test_stage_tree_never_follows_symlinks() -> None:
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        os.symlink(outside, os.path.join(root, "app"))
        with pytest.raises((ValueError, OSError)):
            paths.stage_tree(root, {"app/x.py": "pwned"})
        assert os.listdir(outside) == []
        os.symlink(os.path.join(outside, "target.py"), os.path.join(root, "link.py"))
        with pytest.raises(OSError):
            paths.stage_tree(root, {"link.py": "pwned"})
        assert os.listdir(outside) == []
    with pytest.raises(Unprocessable):
        paths.normalise("../../etc/passwd.py")


def test_quotas(mk) -> None:
    client = mk()
    h = new_learner(client)
    ws = open_ws(client, h)
    assert write(client, h, ws["id"], "big.py", "x" * 70_000, None).status_code == 422


def test_snapshots_reset_and_restore(mk) -> None:
    client = mk()
    h = new_learner(client)
    ws = open_ws(client, h)
    f = read(client, h, ws["id"], "app/models.py")
    write(client, h, ws["id"], "app/models.py", "# mine\n", f["revision"])
    snap = client.post(f"{API}/workspaces/{ws['id']}/snapshots", headers=h, json={"label": "checkpoint"})
    assert snap.status_code == 201 and snap.json()["files_changed"] == 1
    detail = client.get(f"{API}/workspaces/{ws['id']}", headers=h).json()
    # Reset needs the current workspace revision.
    assert client.post(f"{API}/workspaces/{ws['id']}/reset", headers=h,
                       json={"expected_revision": detail["revision"] - 1}).status_code == 409
    reset = client.post(f"{API}/workspaces/{ws['id']}/reset", headers=h,
                        json={"expected_revision": detail["revision"]})
    assert reset.status_code == 200 and reset.json()["resets"] == 1
    assert read(client, h, ws["id"], "app/models.py")["content"] == PROJECT.starter["app/models.py"]
    snaps = client.get(f"{API}/workspaces/{ws['id']}/snapshots", headers=h).json()
    assert [s["label"] for s in snaps][:2] == ["Before reset", "checkpoint"]  # nothing is lost
    restored = client.post(f"{API}/workspaces/{ws['id']}/snapshots/1/restore", headers=h,
                           json={"expected_revision": reset.json()["revision"]})
    assert restored.status_code == 200
    assert read(client, h, ws["id"], "app/models.py")["content"] == "# mine\n"
    one = client.get(f"{API}/workspaces/{ws['id']}/snapshots/1", headers=h).json()
    assert one["files"]["app/models.py"] == "# mine\n" and one["diff"][0]["path"] == "app/models.py"
    history = client.get(f"{API}/workspaces/{ws['id']}/history", headers=h).json()
    assert {"workspace.reset", "snapshot.restored", "file.updated"} <= {e["action"] for e in history}


def test_other_learners_cannot_see_or_touch_a_workspace(mk) -> None:
    client = mk(sandbox_backend="mock")
    owner, other = new_learner(client), new_learner(client)
    ws = open_ws(client, owner)
    j = job(client, owner, ws["id"], "run").json()
    base = f"{API}/workspaces/{ws['id']}"
    assert client.get(base, headers=other).status_code == 404
    assert client.get(f"{base}/files/app/main.py", headers=other).status_code == 404
    assert write(client, other, ws["id"], "app/main.py", "x", 1).status_code == 404
    assert client.post(f"{base}/reset", headers=other, json={"expected_revision": 1}).status_code == 404
    assert job(client, other, ws["id"], "run").status_code == 404
    assert client.get(f"{API}/jobs/{j['id']}", headers=other).status_code == 404
    assert client.get(f"{base}/snapshots", headers=other).status_code == 404
    assert client.get(base).status_code == 401


# ---------------------------------------------------------------- jobs


def test_execution_disabled_refuses_jobs(mk) -> None:
    client = mk(sandbox_backend="disabled")
    h = new_learner(client)
    ws = open_ws(client, h)
    assert job(client, h, ws["id"], "run").status_code == 503


def test_mock_runner_executes_nothing_and_creates_no_evidence(mk, settings) -> None:
    client = mk(sandbox_backend="mock")
    h = new_learner(client)
    ws = open_ws(client, h)
    key = uuid.uuid4()
    first = job(client, h, ws["id"], "submit", key)
    assert first.status_code == 202
    assert job(client, h, ws["id"], "submit", key).json()["id"] == first.json()["id"]  # idempotent retry
    from app.coding.sandbox import MockSandbox
    drain(settings.model_copy(update={"sandbox_backend": "mock"}), MockSandbox())
    done = client.get(f"{API}/jobs/{first.json()['id']}", headers=h).json()
    assert done["status"] == "completed" and not done["sandbox_verified"]
    assert {r["outcome"] for r in done["results"]} == {"not_executed"}
    sub = client.get(f"{API}/submissions/{done['submission_id']}", headers=h).json()
    assert not sub["executed"] and not sub["verified"] and sub["reference_diff"] is None
    rows = asyncio.run(_fetch(settings, "SELECT count(*) FROM mastery_evidence WHERE source = 'engineering_task'"))
    assert rows[0][0] == 0
    # Same code again: the earlier submission is returned, not a new one.
    assert job(client, h, ws["id"], "submit").json()["id"] == first.json()["id"]


def test_rate_limit_on_active_jobs(mk) -> None:
    client = mk(sandbox_backend="mock", coding_max_active_jobs=1)
    h = new_learner(client)
    ws = open_ws(client, h)
    assert job(client, h, ws["id"], "run").status_code == 202
    assert job(client, h, ws["id"], "run").status_code == 429


def test_worker_retries_infrastructure_failures_then_records_once(mk, settings) -> None:
    client = mk(sandbox_backend="docker")
    h = new_learner(client)
    ws = open_ws(client, h)
    apply_reference(client, h, ws["id"])
    j = job(client, h, ws["id"], "submit").json()
    s = settings.model_copy(update={"sandbox_backend": "docker", "job_max_attempts": 3})
    sandbox = ProjectDouble(expected_map(settings), fail_times=1)
    drain(s, sandbox)
    done = client.get(f"{API}/jobs/{j['id']}", headers=h).json()
    assert done["status"] == "completed" and done["attempts"] == 2
    assert done["passed"] == done["total"] == len(PROJECT.tests)
    # Public and hidden checks ran in separate sandboxes; public runs never see hidden checks.
    assert {r.visibility for r in sandbox.calls} == {"public", "hidden"}
    assert all(r.checks["hidden"] == "" for r in sandbox.calls if r.visibility == "public")
    public_runs = [r for r in sandbox.calls if r.visibility == "public"]
    assert all(c.visibility.value == "public" for r in public_runs for c in r.cases)
    subs = client.get(f"{API}/workspaces/{ws['id']}/submissions", headers=h).json()
    assert len(subs) == 1 and subs[0]["verified"] and subs[0]["all_passed"]


def test_worker_fails_job_after_max_attempts(mk, settings) -> None:
    client = mk(sandbox_backend="docker")
    h = new_learner(client)
    ws = open_ws(client, h)
    j = job(client, h, ws["id"], "run").json()
    s = settings.model_copy(update={"sandbox_backend": "docker", "job_max_attempts": 2})
    drain(s, ProjectDouble(expected_map(settings), fail_times=10))
    done = client.get(f"{API}/jobs/{j['id']}", headers=h).json()
    assert done["status"] == "failed" and done["error_code"] in ("sandbox_unavailable", "max_attempts_exceeded")


def test_unverified_sandbox_blocks_jobs(mk, settings) -> None:
    client = mk(sandbox_backend="docker")
    h = new_learner(client)
    ws = open_ws(client, h)
    j = job(client, h, ws["id"], "run").json()
    sandbox = ProjectDouble(expected_map(settings), verified=False)
    drain(settings.model_copy(update={"sandbox_backend": "docker"}), sandbox)
    done = client.get(f"{API}/jobs/{j['id']}", headers=h).json()
    assert done["status"] == "blocked" and done["error_code"] == "sandbox_unverified" and not sandbox.calls


def test_cited_test_names_tolerate_formatting_only() -> None:
    from app.workspace.review import match_failed

    failed = {"Unknown task id returns 404", "Deleting a task returns 204 and removes it"}
    assert match_failed("[public] unknown task ID returns 404.", failed) == "Unknown task id returns 404"
    assert match_failed("\u201cDeleting a task returns 204 and removes it\u201d", failed) == "Deleting a task returns 204 and removes it"
    assert match_failed("Unknown task returns 404", failed) is None  # different words are not forgiven
    assert match_failed(None, failed) is None


def test_hidden_results_are_redacted() -> None:
    r = CaseResult(1, 0, TestOutcome.ERROR, 3, "Raised SecretInput_42_abc", None)
    assert _redact_hidden(r).message == "Raised an exception"
    assert _redact_hidden(CaseResult(1, 0, TestOutcome.ERROR, 3, "Raised KeyError", None)).message == "Raised KeyError"
    failed = _redact_hidden(CaseResult(1, 0, TestOutcome.FAILED, 3, "x", '{"leak": 1}'))
    assert failed.actual is None


# ---------------------------------------------------------------- AI review


def _review_json(**over) -> str:
    base = {
        "summary": "Status codes are fixed in the routes; the filter still treats False as no filter.",
        "findings": [
            {"category": "proven_failure", "dimension": "correctness", "severity": "major", "path": "app/repository.py",
             "line": 21, "message": "completed=False is ignored by the filter.", "test_name": "Filtering incomplete tasks excludes completed ones"},
            {"category": "proven_failure", "dimension": "correctness", "severity": "major", "path": "app/nope.py",
             "line": 999, "message": "Claimed failure without a failing test.", "test_name": "Not a real test"},
            {"category": "suggestion", "dimension": "readability", "severity": "info", "path": "app/routes/tasks.py",
             "line": 9999, "message": "Name the 404 message as a constant."},
        ],
        "requested_changes": ["Handle completed=False explicitly."],
        "questions": ["Why did you put the priority check in the model rather than the handler?"],
        "tradeoffs": [], "strengths": ["Small, focused diff."],
        "rubric": [{"criterion": 1, "rating": "partial", "note": "Two of three defects fixed."},
                   {"criterion": 99, "rating": "meets", "note": "out of range"}],
        "recommendation": "approve", "confidence": 0.8,
    }
    base.update(over)
    return json.dumps(base)


def _submitted(client, settings, h, *, fixed: bool) -> dict:
    ws = open_ws(client, h)
    if fixed:
        apply_reference(client, h, ws["id"])
    else:
        f = read(client, h, ws["id"], "app/models.py")
        write(client, h, ws["id"], "app/models.py", f["content"].replace("priority: int = 3", "priority: int = Field(default=3, ge=1, le=5)"), f["revision"])
    j = job(client, h, ws["id"], "submit").json()
    drain(settings.model_copy(update={"sandbox_backend": "docker"}), ProjectDouble(expected_map(settings)))
    return {"ws": ws, "job": client.get(f"{API}/jobs/{j['id']}", headers=h).json()}


def test_review_is_grounded_in_tests_and_validated(mk, settings) -> None:
    llm = FakeProvider()
    client = mk(llm=llm, sandbox_backend="docker", llm_provider="openai_compatible")
    h = new_learner(client)
    s = _submitted(client, settings, h, fixed=False)
    sub_id = s["job"]["submission_id"]
    failed = [r["name"] for r in s["job"]["results"] if r["outcome"] != "passed"]
    llm.queue(_review_json(findings=[
        {"category": "proven_failure", "dimension": "correctness", "severity": "major", "path": "app/repository.py",
         "line": 21, "message": "completed=False is ignored by the filter.", "test_name": failed[0]},
        {"category": "proven_failure", "dimension": "correctness", "severity": "major", "path": "app/nope.py",
         "line": 999, "message": "Claimed failure without a failing test.", "test_name": "Not a real test"},
        {"category": "suggestion", "dimension": "readability", "severity": "info", "path": "app/routes/tasks.py",
         "line": 9999, "message": "Name the 404 message as a constant."},
    ]))
    res = client.post(f"{API}/submissions/{sub_id}/reviews", headers=h, json={"mode": "tech_lead"})
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["status"] == "completed" and r["rubric_version"] == PROJECT.rubric_version
    rv = r["review"]
    cats = [(f["category"], f["path"], f["line"]) for f in rv["findings"]]
    assert cats[0] == ("proven_failure", "app/repository.py", 21)
    assert cats[1] == ("potential_concern", None, None)  # no failing test -> downgraded; unknown path dropped
    assert cats[2] == ("suggestion", "app/routes/tasks.py", None)  # out-of-range line dropped
    assert rv["recommendation"] == "request_changes" and rv["recommendation_overridden"]
    assert rv["requested_changes"][0].startswith("Make the failing tests pass")
    assert [x["criterion"] for x in rv["rubric"]] == [1]
    assert "advisory" in rv["grounding"]
    # The prompt carries code as delimited untrusted data and never the reference or hidden inputs.
    prompt = "\n".join(m.content for m in llm.requests[-1].messages)
    assert "<diff>" in prompt and "HTTP_404_NOT_FOUND" not in prompt
    hidden_args = [json.dumps(t.resolved_args()) for t in PROJECT.tests if t.visibility.value == "hidden"]
    assert all(a not in prompt for a in hidden_args)
    # Idempotent per (submission, mode).
    again = client.post(f"{API}/submissions/{sub_id}/reviews", headers=h, json={"mode": "tech_lead"})
    assert again.json()["id"] == r["id"] and len(llm.requests) == 1


def test_review_blocks_reference_leaks_and_failures_are_ungraded(mk, settings) -> None:
    llm = FakeProvider()
    client = mk(llm=llm, sandbox_backend="docker", llm_provider="openai_compatible", llm_max_repair_attempts=0)
    h = new_learner(client)
    sub_id = _submitted(client, settings, h, fixed=False)["job"]["submission_id"]
    leak = "Use `priority: int = Field(default=3, ge=1, le=5)` and raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)"
    llm.queue(_review_json(findings=[{"category": "suggestion", "dimension": "correctness", "severity": "minor",
                                      "message": "Consider this.", "suggestion": "raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) in get_task when the repo returns None"}],
                           summary="Mostly fine; one suggestion below."))
    r = client.post(f"{API}/submissions/{sub_id}/reviews", headers=h, json={"mode": "guided"}).json()
    assert r["leak_blocked"] and r["review"]["findings"] == []
    assert leak  # documented example of the material that is filtered
    llm.queue(ProviderTimeout("slow"))
    r2 = client.post(f"{API}/submissions/{sub_id}/reviews", headers=h, json={"mode": "strict"}).json()
    assert r2["status"] == "ungraded" and r2["error_code"] == "provider_timeout"
    llm.queue("not json")
    r3 = client.post(f"{API}/submissions/{sub_id}/reviews", headers=h, json={"mode": "strict"}).json()
    assert r3["status"] == "ungraded" and r3["error_code"] == "malformed_output" and r3["id"] == r2["id"]


# ---------------------------------------------------------------- pull requests


def _respond_all(client, h, pr_id) -> None:
    detail = client.get(f"{API}/pulls/{pr_id}", headers=h).json()
    for c in detail["comments"]:
        if c["author"] == "reviewer" and c["kind"] == "change_request" and not c["answered"]:
            res = client.post(f"{API}/pulls/{pr_id}/comments", headers=h, json={
                "body": "Addressed: I fixed the filter and explained my choice.", "parent_id": c["id"],
                "client_id": str(uuid.uuid4())})
            assert res.status_code == 201, res.text


def test_pull_request_workflow_end_to_end(mk, settings) -> None:
    llm = FakeProvider()
    client = mk(llm=llm, sandbox_backend="docker", llm_provider="openai_compatible")
    h = new_learner(client)
    ws = open_ws(client, h)
    sandbox = ProjectDouble(expected_map(settings))
    s = settings.model_copy(update={"sandbox_backend": "docker"})
    key = str(uuid.uuid4())
    body = {"title": "Fix TASKS-142 status codes", "description": "Fixes status codes and validation for TASKS-142.",
            "idempotency_key": key}
    opened = client.post(f"{API}/workspaces/{ws['id']}/pulls", headers=h, json=body)
    assert opened.status_code == 201, opened.text
    pr_id = opened.json()["id"]
    assert client.post(f"{API}/workspaces/{ws['id']}/pulls", headers=h, json=body).json()["id"] == pr_id  # retry
    other = {**body, "idempotency_key": str(uuid.uuid4())}
    assert client.post(f"{API}/workspaces/{ws['id']}/pulls", headers=h, json=other).status_code == 409  # one open PR
    # Reviewing before checks finish is refused.
    assert client.post(f"{API}/pulls/{pr_id}/reviews", headers=h, json={"mode": "senior"}).status_code == 409
    drain(s, sandbox)

    # Revision 1: starter code fails; the AI requests changes; the decision is not approval.
    llm.queue(_review_json(findings=[], recommendation="request_changes"))
    rv = client.post(f"{API}/pulls/{pr_id}/reviews", headers=h, json={"mode": "senior"})
    assert rv.status_code == 200 and rv.json()["status"] == "completed"
    pr = client.get(f"{API}/pulls/{pr_id}", headers=h).json()
    assert pr["status"] == "changes_requested"
    assert any(c["author"] == "reviewer" and c["kind"] == "change_request" for c in pr["comments"])
    crit = {c["key"]: c["met"] for c in pr["criteria"]["criteria"]}
    assert crit == {"verified_tests": True, "all_tests_pass": False, "review_completed": True, "feedback_answered": False}
    decided = client.post(f"{API}/pulls/{pr_id}/decision", headers=h).json()
    assert decided["status"] == "changes_requested" and not decided["decision"]["approved"]

    # Inline comment on a file in the latest revision; invalid line rejected.
    assert client.post(f"{API}/pulls/{pr_id}/comments", headers=h, json={
        "body": "Note to self", "path": "app/models.py", "line": 500, "client_id": str(uuid.uuid4())}).status_code == 422
    inline = client.post(f"{API}/pulls/{pr_id}/comments", headers=h, json={
        "body": "Validation lives here.", "path": "app/models.py", "line": 7, "client_id": str(uuid.uuid4())})
    assert inline.status_code == 201 and inline.json()["line"] == 7

    # Pushing without changes is refused; with the fix it creates revision 2.
    assert client.post(f"{API}/pulls/{pr_id}/revisions", headers=h,
                       json={"idempotency_key": str(uuid.uuid4())}).status_code == 409
    apply_reference(client, h, ws["id"])
    rev = client.post(f"{API}/pulls/{pr_id}/revisions", headers=h,
                      json={"note": "Fixed the filter and 404s.", "idempotency_key": str(uuid.uuid4())})
    assert rev.status_code == 200 and len(rev.json()["revision_list"]) == 2
    assert rev.json()["revision_list"][1]["diff_from_previous"]
    drain(s, sandbox)

    # Approval needs a review of the latest revision and answers to every reviewer request,
    # even though the AI recommends approval: the model is never the gate.
    llm.queue(_review_json(findings=[], requested_changes=[], recommendation="approve"))
    assert client.post(f"{API}/pulls/{pr_id}/reviews", headers=h, json={"mode": "tech_lead"}).status_code == 200
    assert client.post(f"{API}/pulls/{pr_id}/decision", headers=h).json()["status"] == "changes_requested"
    _respond_all(client, h, pr_id)
    final = client.post(f"{API}/pulls/{pr_id}/decision", headers=h).json()
    assert final["status"] == "approved" and final["decision"]["approved"], final["decision"]
    assert client.get(f"{API}/workspaces/{ws['id']}", headers=h).json()["status"] == "completed"
    assert client.post(f"{API}/pulls/{pr_id}/comments", headers=h,
                       json={"body": "late", "client_id": str(uuid.uuid4())}).status_code == 409

    # Evidence: verified practical evidence for mastery, and a career portfolio entry.
    rows = asyncio.run(_fetch(settings, "SELECT verified, success, dimension FROM mastery_evidence "
                                        "WHERE source = 'engineering_task' ORDER BY observed_at"))
    assert rows and rows[-1] == (True, True, "practical") and rows[0][1] is False
    folio = client.get(f"{API}/portfolio", headers=h).json()["projects"][0]
    assert folio["revisions_required"] == 1 and folio["completed_at"] and len(folio["review_history"]) == 2
    career = client.get("/api/v1/career/dashboard", headers=h).json()
    assert career["engineering_projects"]["projects"][0]["project"] == SLUG
    prog = client.get(f"{API}/progress", headers=h).json()
    assert prog["totals"]["projects_approved"] == 1
    assert any(c["verified"]["total"] for c in prog["competencies"])


def test_pr_without_ai_provider_waives_review_but_still_needs_tests(mk, settings) -> None:
    client = mk(sandbox_backend="docker", llm_provider="disabled")
    h = new_learner(client)
    ws = open_ws(client, h)
    apply_reference(client, h, ws["id"])
    pr = client.post(f"{API}/workspaces/{ws['id']}/pulls", headers=h, json={
        "title": "Fix TASKS-142", "description": "Fixes every acceptance criterion.", "idempotency_key": str(uuid.uuid4())}).json()
    pending = client.post(f"{API}/pulls/{pr['id']}/decision", headers=h).json()
    assert pending["status"] == "changes_requested"  # checks not run yet
    drain(settings.model_copy(update={"sandbox_backend": "docker"}), ProjectDouble(expected_map(settings)))
    final = client.post(f"{API}/pulls/{pr['id']}/decision", headers=h).json()
    review = next(c for c in final["decision"]["criteria"] if c["key"] == "review_completed")
    assert final["status"] == "approved" and review["waived"]


def test_mock_runs_never_approve_a_pr(mk, settings) -> None:
    from app.coding.sandbox import MockSandbox

    client = mk(sandbox_backend="mock", llm_provider="disabled")
    h = new_learner(client)
    ws = open_ws(client, h)
    apply_reference(client, h, ws["id"])
    pr = client.post(f"{API}/workspaces/{ws['id']}/pulls", headers=h, json={
        "title": "Fix TASKS-142", "description": "Fixes every acceptance criterion.", "idempotency_key": str(uuid.uuid4())}).json()
    drain(settings.model_copy(update={"sandbox_backend": "mock"}), MockSandbox())
    final = client.post(f"{API}/pulls/{pr['id']}/decision", headers=h).json()
    assert final["status"] == "changes_requested"
    assert not next(c for c in final["decision"]["criteria"] if c["key"] == "verified_tests")["met"]


# ---------------------------------------------------------------- exercises & progress


def test_collaboration_exercise_review(mk, settings) -> None:
    llm = FakeProvider()
    client = mk(llm=llm, llm_provider="openai_compatible")
    h = new_learner(client)
    ws = open_ws(client, h)
    answer = ("Old Android clients send priority 0 meaning no priority. I would normalise 0 to the default of 3 "
              "on input for clients below version 4.2, keep rejecting other invalid values, add a metric for "
              "old-client traffic and remove the path after a deprecation date agreed with the Android team.")
    llm.queue(json.dumps({
        "criteria": [{"criterion": f"c{i}", "score": 2, "quote": "normalise 0 to the default of 3 on input",
                      "rationale": "Clear."} for i in range(1, 6)],
        "summary": "Solid plan with a rollout and removal path.", "strengths": ["Rollout"], "gaps": [],
        "misconceptions": [], "follow_up_questions": ["How would you test it?"], "confidence": 0.8}))
    cid = str(uuid.uuid4())
    res = client.post(f"{API}/workspaces/{ws['id']}/exercises/backward-compat-change", headers=h,
                      json={"body": answer, "client_id": cid})
    assert res.status_code == 201, res.text
    r = res.json()
    assert r["status"] == "evaluated" and r["eligible"] and r["score"] == 1.0
    again = client.post(f"{API}/workspaces/{ws['id']}/exercises/backward-compat-change", headers=h,
                        json={"body": answer, "client_id": cid})
    assert again.json()["id"] == r["id"] and len(llm.requests) == 1  # idempotent
    assert client.post(f"{API}/workspaces/{ws['id']}/exercises/nope", headers=h,
                       json={"body": answer, "client_id": str(uuid.uuid4())}).status_code == 404
    career = client.get("/api/v1/career/dashboard", headers=h)
    assert career.status_code == 200


def test_progress_recommends_follow_ups_from_failed_tests(mk, settings) -> None:
    client = mk(sandbox_backend="docker")
    h = new_learner(client)
    _submitted(client, settings, h, fixed=False)
    prog = client.get(f"{API}/progress", headers=h).json()
    kinds = {r["kind"] for r in prog["recommendations"]}
    assert "failed_tests" in kinds
    mine = next(p for p in prog["projects"] if p["slug"] == SLUG)
    assert mine["verified_submissions"] == 1 and not mine["latest_all_passed"]
    assert [p["level"] for p in prog["projects"]] == ["beginner", "mid", "senior"]
    assert "never used to mark a task complete" in prog["note"]


# ---------------------------------------------------------------- real sandbox


REAL = None


def _real_sandbox(settings):
    global REAL
    if REAL is None:
        s = settings.model_copy(update={"sandbox_backend": "docker", "sandbox_allow_container_isolation": True})
        sb = DockerSandbox(s)
        REAL = (s, sb, asyncio.run(sb.verify()))
    s, sb, report = REAL
    if not report.verified:
        pytest.skip(f"Docker sandbox not verified: {report.problems}")
    return s, sb


def test_real_sandbox_end_to_end(mk, settings) -> None:
    s, sb = _real_sandbox(settings)
    client = mk(sandbox_backend="docker", sandbox_allow_container_isolation=True)
    h = new_learner(client)
    ws = open_ws(client, h)
    run = job(client, h, ws["id"], "run").json()
    drain(s, sb)
    run = client.get(f"{API}/jobs/{run['id']}", headers=h).json()
    assert run["status"] == "completed" and run["sandbox_verified"]
    assert all(r["visibility"] == "public" for r in run["results"])
    assert any(r["outcome"] == "failed" and r["actual"] for r in run["results"])  # public diagnostics

    sub = job(client, h, ws["id"], "submit").json()
    drain(s, sb)
    sub = client.get(f"{API}/jobs/{sub['id']}", headers=h).json()
    hidden = [r for r in sub["results"] if r["visibility"] == "hidden"]
    assert hidden and any(r["outcome"] != "passed" for r in hidden)
    assert all(r["args"] is None and r["expected"] is None and r["actual"] is None for r in hidden)

    apply_reference(client, h, ws["id"])
    fixed = job(client, h, ws["id"], "submit").json()
    drain(s, sb)
    fixed = client.get(f"{API}/jobs/{fixed['id']}", headers=h).json()
    assert fixed["passed"] == fixed["total"] == len(PROJECT.tests), fixed["results"]
    detail = client.get(f"{API}/submissions/{fixed['submission_id']}", headers=h).json()
    assert detail["verified"] and detail["reference_diff"]  # revealed only after a verified all-pass
    rows = asyncio.run(_fetch(settings, "SELECT count(*) FILTER (WHERE success) FROM mastery_evidence "
                                        "WHERE source = 'engineering_task'"))
    assert rows[0][0] == 1


def test_real_sandbox_learner_code_cannot_escape_or_read_hidden_checks(mk, settings) -> None:
    s, sb = _real_sandbox(settings)
    client = mk(sandbox_backend="docker", sandbox_allow_container_isolation=True)
    h = new_learner(client)
    ws = open_ws(client, h)
    f = read(client, h, ws["id"], "app/main.py")
    hostile = '''import os, socket

from fastapi import FastAPI

from app.repository import TaskRepository
from app.routes import tasks


def _probe():
    out = {}
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1); out["net"] = "open"
    except OSError:
        out["net"] = "blocked"
    try:
        open("/work/project/app/x.py", "w").write("x"); out["write"] = "ok"
    except OSError:
        out["write"] = "denied"
    out["hidden"] = os.path.exists("/work/checks_hidden.py")
    out["secrets"] = [k for k in os.environ if k.startswith(("FORGE", "DATABASE", "PG"))]
    out["uid"] = os.getuid()
    return out


PROBE = _probe()


def create_app():
    app = FastAPI()
    app.state.repo = TaskRepository()

    @app.get("/tasks/42")  # registered first, so the public 404 test returns the probe
    def leak():
        return PROBE

    app.include_router(tasks.router)
    return app
'''
    assert write(client, h, ws["id"], "app/main.py", hostile, f["revision"]).status_code == 200
    r = job(client, h, ws["id"], "run").json()
    drain(s, sb)
    r = client.get(f"{API}/jobs/{r['id']}", headers=h).json()
    probe = next(x for x in r["results"] if x["name"] == "Unknown task id returns 404")
    seen = json.loads(probe["actual"])[0][1]
    assert seen == {"net": "blocked", "write": "denied", "hidden": False, "secrets": [], "uid": 65534}


def test_real_sandbox_verifies_every_project(settings) -> None:
    """Every reference passes every test; every starter fails at least one hidden test."""
    from app.workspace.verify_projects import verify_project

    s, sb = _real_sandbox(settings)
    reports = [asyncio.run(verify_project(sb, p)) for p in load_projects()]
    assert all(r.ok for r in reports), [(r.slug, r.reference_failures, r.starter_hidden_failures) for r in reports]
