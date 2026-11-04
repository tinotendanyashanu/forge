"""Trusted grading. Runs in the worker, never inside the sandbox.

The sandbox returns only raw outputs. Expected values live here, so learner
code cannot forge a pass by tampering with the harness or printing fake
results: the only way to pass is to produce the correct output.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.db.enums import TestOutcome, TestVisibility

MARK = "@@FORGE@@"
MESSAGE_LIMIT = 300
ACTUAL_LIMIT = 500
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PATHS = re.compile(r"(/work|/tmp|/usr|/app|/home|/var)/[^\s'\"]*")


@dataclass(frozen=True)
class CaseSpec:
    id: int
    position: int
    name: str
    visibility: TestVisibility
    call: str
    args: list
    expected: dict  # {"value": ...} | {"raises": "Name"}


@dataclass(frozen=True)
class CaseResult:
    case_id: int
    position: int
    outcome: TestOutcome
    duration_ms: int | None
    message: str | None
    actual: str | None


def parse_output(stdout: str) -> dict[int, dict]:
    """Last well-formed record per case id wins; anything else is ignored."""
    records: dict[int, dict] = {}
    for line in stdout.splitlines():
        if not line.startswith(MARK):
            continue
        try:
            rec = json.loads(line[len(MARK):])
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("id"), int):
            records[rec["id"]] = rec
    return records


def sanitize(text: str | None, limit: int = MESSAGE_LIMIT) -> str | None:
    if not text:
        return None
    cleaned = _PATHS.sub("<path>", _ANSI.sub("", str(text))).replace("\x00", "")
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def values_equal(actual: Any, expected: Any, tol: float = 1e-9) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(actual, expected, rel_tol=tol, abs_tol=tol)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(values_equal(a, e, tol) for a, e in zip(actual, expected))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(values_equal(actual[k], expected[k], tol) for k in expected)
    return actual == expected


def _short(value: Any) -> str:
    text = json.dumps(value, separators=(", ", ": "))
    return text[:ACTUAL_LIMIT] + ("…" if len(text) > ACTUAL_LIMIT else "")


def grade(cases: list[CaseSpec], stdout: str, *, killed_for_time: bool) -> list[CaseResult]:
    records = parse_output(stdout)
    results: list[CaseResult] = []
    for case in cases:
        rec = records.get(case.id)
        hidden = case.visibility is TestVisibility.HIDDEN
        if rec is None:
            outcome = TestOutcome.TIMEOUT if killed_for_time else TestOutcome.ERROR
            msg = "Time limit exceeded" if killed_for_time else "No result: the process crashed or exceeded a resource limit"
            results.append(CaseResult(case.id, case.position, outcome, None, msg, None))
            continue
        ms = rec.get("ms") if isinstance(rec.get("ms"), int) else None
        expected_raise = case.expected.get("raises")
        if not rec.get("ok"):
            err = rec.get("error") or {}
            etype = str(err.get("type") or "Error")[:60]
            if err.get("phase") == "timeout":
                results.append(CaseResult(case.id, case.position, TestOutcome.TIMEOUT, ms, "Time limit exceeded", None))
            elif expected_raise and etype == expected_raise:
                results.append(CaseResult(case.id, case.position, TestOutcome.PASSED, ms, None, None))
            else:
                # Hidden tests reveal the exception type only, never its message.
                detail = etype if hidden else f"{etype}: {sanitize(err.get('message')) or ''}".rstrip(": ")
                prefix = "Failed to load your code" if err.get("phase") == "import" else "Raised"
                results.append(CaseResult(case.id, case.position, TestOutcome.ERROR, ms, f"{prefix} {detail}", None))
            continue
        value = rec.get("value")
        if expected_raise:
            msg = f"Expected {expected_raise} to be raised" if not hidden else "Expected an exception"
            results.append(CaseResult(case.id, case.position, TestOutcome.FAILED, ms, msg, None if hidden else _short(value)))
        elif values_equal(value, case.expected.get("value")):
            results.append(CaseResult(case.id, case.position, TestOutcome.PASSED, ms, None, None))
        else:
            msg = "Output did not match the expected result"
            results.append(CaseResult(case.id, case.position, TestOutcome.FAILED, ms, msg, None if hidden else _short(value)))
    return results
