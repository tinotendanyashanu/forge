"""Grader, sanitiser, sandbox configuration and bank schema (no Docker needed)."""

import asyncio
import json

import pytest

from app.coding.bank_loader import BankChallenge, load_bank
from app.coding.grading import MARK, CaseSpec, grade, parse_output, sanitize, values_equal
from app.coding.sandbox import DockerSandbox, ExecRequest, MockSandbox
from app.core.config import Settings
from app.db.enums import TestOutcome, TestVisibility

PUB, HID = TestVisibility.PUBLIC, TestVisibility.HIDDEN


def case(i, expected, vis=PUB):
    return CaseSpec(i, i, f"case {i}", vis, "f", [i], expected)


def rec(**kw) -> str:
    return MARK + json.dumps(kw) + "\n"


# ---------------------------------------------------------------- grading


def test_grade_pass_fail_and_actual_only_for_public() -> None:
    cases = [case(1, {"value": 2}), case(2, {"value": 3}, HID)]
    out = rec(id=1, ok=True, value=5, ms=1) + rec(id=2, ok=True, value=4, ms=1)
    r1, r2 = grade(cases, out, killed_for_time=False)
    assert r1.outcome is TestOutcome.FAILED and r1.actual == "5"
    assert r2.outcome is TestOutcome.FAILED and r2.actual is None


def test_hidden_errors_reveal_exception_type_only() -> None:
    cases = [case(1, {"value": 1}, HID), case(2, {"value": 1})]
    secret = "input was [[1, 2], 'secret-hidden-input']"
    out = rec(id=1, ok=False, error={"type": "KeyError", "message": secret, "phase": "call"}, ms=0) + \
        rec(id=2, ok=False, error={"type": "KeyError", "message": "boom at /work/solution.py", "phase": "call"}, ms=0)
    hidden, public = grade(cases, out, killed_for_time=False)
    assert hidden.message == "Raised KeyError" and "secret" not in hidden.message
    assert public.message == "Raised KeyError: boom at <path>"


def test_expected_exceptions() -> None:
    cases = [case(1, {"raises": "ValueError"}), case(2, {"raises": "ValueError"})]
    out = rec(id=1, ok=False, error={"type": "ValueError", "message": "", "phase": "call"}, ms=0) + \
        rec(id=2, ok=True, value=None, ms=0)
    a, b = grade(cases, out, killed_for_time=False)
    assert a.outcome is TestOutcome.PASSED and b.outcome is TestOutcome.FAILED


def test_missing_results_are_timeouts_when_killed_else_errors() -> None:
    cases = [case(1, {"value": 1})]
    assert grade(cases, "", killed_for_time=True)[0].outcome is TestOutcome.TIMEOUT
    assert grade(cases, "", killed_for_time=False)[0].outcome is TestOutcome.ERROR


def test_last_record_wins_so_early_forgeries_are_overwritten() -> None:
    cases = [case(1, {"value": 42})]
    forged = rec(id=1, ok=True, value=42, ms=0)  # printed by learner code before the harness
    real = rec(id=1, ok=True, value=7, ms=0)
    assert grade(cases, forged + real, killed_for_time=False)[0].outcome is TestOutcome.FAILED


def test_parse_output_ignores_garbage() -> None:
    out = "hello\n@@FORGE@@not json\n" + MARK + '{"id": "x"}\n' + rec(id=3, ok=True, value=1, ms=0)
    assert list(parse_output(out)) == [3]


@pytest.mark.parametrize(
    ("a", "b", "eq"),
    [(1, 1.0, True), (0.1 + 0.2, 0.3, True), (True, 1, False), ([1, [2]], [1, [2]], True),
     ({"a": 1}, {"a": 1, "b": 2}, False), ("1", 1, False), (None, None, True)],
)
def test_values_equal(a, b, eq) -> None:
    assert values_equal(a, b) is eq


def test_sanitize_strips_paths_ansi_and_truncates() -> None:
    s = sanitize("\x1b[31mError\x1b[0m in /usr/lib/x.py and /tmp/abc " + "y" * 500)
    assert "\x1b" not in s and "/usr/lib" not in s and "<path>" in s and s.endswith("…") and len(s) <= 301


# ---------------------------------------------------------------- sandbox configuration


def _docker(**kw) -> DockerSandbox:
    return DockerSandbox(Settings(sandbox_backend="docker", sandbox_allow_container_isolation=True, **kw))


def test_docker_args_are_hardened() -> None:
    args = _docker().docker_args("n", "/tmp/w", "python:3.12-slim", 128)
    joined = " ".join(args)
    for flag in ["--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit 64", "--memory 128m", "--memory-swap 128m", "--user 65534:65534",
                 "--ipc none", "--log-driver none", "--rm"]:
        assert flag in joined, flag
    assert "type=bind,source=/tmp/w,target=/work,readonly" in joined
    mounts = [a for a in args if a.startswith("type=bind") or a.startswith("-v")]
    assert mounts == ["type=bind,source=/tmp/w,target=/work,readonly"]  # nothing else from the host
    assert "docker.sock" not in joined and "--privileged" not in joined


def test_memory_and_time_are_capped_by_settings() -> None:
    sb = _docker(sandbox_max_memory_mb=128, sandbox_max_time_ms=2000)
    assert "--memory 128m" in " ".join(sb.docker_args("n", "/w", "img", 900))
    req = ExecRequest("python", "", None, [case(i, {}) for i in range(50)], 5000, 64)
    assert sb.wall_clock_ms(req) == 2000 + 2500


def test_docker_backend_refuses_without_acknowledgement() -> None:
    v = asyncio.run(DockerSandbox(Settings(sandbox_backend="docker")).verify())
    assert v.verified is False and "not acknowledged" in v.problems[0]


def test_mock_sandbox_executes_nothing() -> None:
    sb = MockSandbox()
    assert sb.executes is False
    assert asyncio.run(sb.run(ExecRequest("python", "import os; os.system('x')", None, [], 1000, 64))).stdout == ""


# ---------------------------------------------------------------- bank schema


def test_bank_loads_and_covers_required_areas() -> None:
    bank = load_bank()
    assert len(bank) >= 15
    areas = {c.area for c in bank}
    for required in ["foundations", "algorithms", "python-fastapi", "javascript-typescript", "react", "sql",
                     "api-design", "auth", "concurrency", "testing-debugging", "performance", "security"]:
        assert required in areas, required
    assert {lang for c in bank for lang in c.languages} == {"python", "javascript", "typescript"}
    # Versions are keyed by content hash, so hashing must be deterministic.
    assert [c.content_hash() for c in bank] == [c.content_hash() for c in load_bank()]
    assert len({c.content_hash() for c in bank}) == len(bank)


BASE = {
    "slug": "x", "title": "Title", "area": "a", "skill": "python", "difficulty": "beginner",
    "entrypoint": "f", "time_limit_ms": 1000, "memory_limit_mb": 64, "description": "A description long enough.",
    "constraints": ["c"], "rubric": ["r1", "r2"], "misconceptions": ["m"], "hints": ["h"],
    "languages": {"python": {"starter": "s", "reference": "r"}},
    "tests": [
        {"name": "one", "visibility": "public", "args": [], "expected": 1},
        {"name": "two", "visibility": "hidden", "args": [], "expected": 1},
        {"name": "three", "visibility": "hidden", "args": [], "raises": "E"},
    ],
}


@pytest.mark.parametrize(
    "change",
    [
        {"tests": [{"name": n, "visibility": "public", "args": [], "expected": 1} for n in ("a", "b", "c")]},
        {"tests": [*BASE["tests"][:2], {"name": "z", "visibility": "hidden", "expected": 1, "raises": "E"}]},
        {"tests": [*BASE["tests"][:2], {"name": "z", "visibility": "hidden"}]},
        {"languages": {"ruby": {"starter": "s", "reference": "r"}}},
        {"tests": [*BASE["tests"][:2], {"name": "z", "visibility": "hidden", "call": "driver:f", "expected": 1}]},
        {"rubric": ["only one"]},
    ],
    ids=["no-hidden", "two-outcomes", "no-outcome", "bad-language", "driver-without-driver", "thin-rubric"],
)
def test_bank_schema_rejects_bad_challenges(change) -> None:
    with pytest.raises(ValueError):
        BankChallenge.model_validate({**BASE, **change})
