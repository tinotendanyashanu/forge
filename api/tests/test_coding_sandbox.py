"""Real-sandbox security and bank verification. Requires Docker and the images;
skipped (not silently passed) when the sandbox can't verify itself."""

import asyncio

import pytest

from app.coding.grading import CaseSpec, grade
from app.coding.sandbox import DockerSandbox, ExecRequest
from app.coding.verify_bank import verify_all
from app.core.config import Settings
from app.db.enums import TestOutcome, TestVisibility

SETTINGS = Settings(sandbox_backend="docker", sandbox_allow_container_isolation=True,
                    sandbox_max_time_ms=3000, sandbox_max_output_bytes=8192)


@pytest.fixture(scope="module")
def sandbox() -> DockerSandbox:
    sb = DockerSandbox(SETTINGS)
    report = asyncio.run(sb.verify())
    if not report.verified:
        pytest.skip(f"Docker sandbox not verified: {report.problems}")
    return sb


def run(sb, code, *, language="python", expected=None, time_ms=1000, mem=64, hidden=False):
    cases = [CaseSpec(1, 0, "t", TestVisibility.HIDDEN if hidden else TestVisibility.PUBLIC, "f", [],
                      expected or {"value": "ok"})]
    res = asyncio.run(sb.run(ExecRequest(language, code, None, cases, time_ms, mem)))
    return res, grade(cases, res.stdout, killed_for_time=res.killed_for_time)[0]


def test_network_is_unreachable(sandbox) -> None:
    code = '''
import socket
def f():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2)
        return "connected"
    except OSError:
        return "ok"
'''
    _, r = run(sandbox, code)
    assert r.outcome is TestOutcome.PASSED


def test_runs_as_non_root_without_secrets(sandbox) -> None:
    code = '''
import os
def f():
    leaked = [k for k in os.environ if k.startswith(("FORGE", "DATABASE", "PG"))]
    return "ok" if os.getuid() != 0 and not leaked else f"bad {os.getuid()} {leaked}"
'''
    assert run(sandbox, code)[1].outcome is TestOutcome.PASSED


def test_filesystem_is_read_only(sandbox) -> None:
    code = '''
def f():
    for p in ("/work/solution.py", "/etc/forge", "/work/cases.json"):
        try:
            open(p, "w").write("x")
            return "wrote " + p
        except OSError:
            pass
    return "ok"
'''
    assert run(sandbox, code)[1].outcome is TestOutcome.PASSED


def test_infinite_loop_times_out(sandbox) -> None:
    res, r = run(sandbox, "def f():\n    while True:\n        pass\n", time_ms=500)
    assert r.outcome is TestOutcome.TIMEOUT


def test_js_infinite_loop_is_killed_by_wall_clock(sandbox) -> None:
    res, r = run(sandbox, "export function f() { for (;;) {} }\n", language="javascript", time_ms=500)
    assert res.killed_for_time and r.outcome is TestOutcome.TIMEOUT


def test_memory_limit_is_enforced(sandbox) -> None:
    code = "def f():\n    blocks = []\n    while True:\n        blocks.append(bytearray(16 * 1024 * 1024))\n"
    _, r = run(sandbox, code, mem=64, time_ms=3000)
    assert r.outcome in (TestOutcome.ERROR, TestOutcome.TIMEOUT)


def test_fork_bomb_is_contained(sandbox) -> None:
    code = '''
import os
def f():
    n = 0
    try:
        while True:
            if os.fork() == 0:
                import time; time.sleep(5); os._exit(0)
            n += 1
    except OSError:
        return "ok" if n < 64 else f"forked {n}"
'''
    res, r = run(sandbox, code, time_ms=3000)
    assert r.outcome is TestOutcome.PASSED, r.message
    assert res.duration_ms < 15_000


def test_output_flood_is_truncated(sandbox) -> None:
    code = "import os\ndef f():\n    while True:\n        os.write(1, b'x' * 65536)\n"
    res, r = run(sandbox, code, time_ms=2000)
    assert res.output_truncated and len(res.stdout) <= SETTINGS.sandbox_max_output_bytes
    assert r.outcome is not TestOutcome.PASSED


def test_forged_results_cannot_pass_hidden_tests(sandbox) -> None:
    # Learner code impersonates the harness: prints "passing" records and exits.
    code = '''
import json, os
for i in range(1, 50):
    os.write(1, ("@@FORGE@@" + json.dumps({"id": i, "ok": True, "value": "guess", "ms": 0}) + "\\n").encode())
os._exit(0)
def f():
    return "x"
'''
    _, r = run(sandbox, code, expected={"value": "the-real-hidden-answer"}, hidden=True)
    assert r.outcome is TestOutcome.FAILED  # expected values never enter the sandbox


def test_import_errors_are_reported_safely(sandbox) -> None:
    _, r = run(sandbox, "def f(:\n", hidden=True)
    assert r.outcome is TestOutcome.ERROR and r.message == "Failed to load your code SyntaxError"


def test_every_reference_passes_and_every_starter_fails() -> None:
    results = asyncio.run(verify_all(SETTINGS.model_copy(update={"sandbox_max_time_ms": 10_000})))
    bad = [(r.slug, r.language, r.reference_failures) for r in results if not r.reference_ok]
    assert not bad
    assert all(r.starter_fails_hidden for r in results), [r.slug for r in results if not r.starter_fails_hidden]
