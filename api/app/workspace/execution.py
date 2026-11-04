"""Runs an engineering project's checks in the sandbox and grades them.

Used by the worker (learner jobs) and by ``verify_projects`` (content checks).
Trusted code only: it runs in the worker process, never in the API.

* Each (suite, visibility) group is a separate, ephemeral container. Public
  runs never contain hidden checks or hidden inputs.
* Raw outputs are graded here against expected values that never entered the
  sandbox (``app.coding.grading.grade``).
* Hidden failures are reduced further: no actual values, and an exception type
  is shown only if it is a standard built-in name (learner-defined exception
  class names could otherwise carry data out of a hidden run).
"""

import builtins
from dataclasses import dataclass

from app.coding.grading import CaseResult, CaseSpec, grade
from app.coding.sandbox import ProjectExecRequest
from app.db.enums import TestOutcome, TestVisibility

SAFE_EXCEPTION_NAMES = frozenset(
    name for name in dir(builtins)
    if isinstance(getattr(builtins, name), type) and issubclass(getattr(builtins, name), BaseException)
)


@dataclass(frozen=True)
class SuiteCase:
    suite: str
    spec: CaseSpec


def _redact_hidden(r: CaseResult) -> CaseResult:
    if r.outcome is TestOutcome.PASSED:
        return r
    msg = r.message or ""
    if msg.startswith("Raised "):
        etype = msg.removeprefix("Raised ").split(":")[0].strip()
        msg = f"Raised {etype}" if etype in SAFE_EXCEPTION_NAMES else "Raised an exception"
    elif r.outcome is TestOutcome.FAILED:
        msg = "Output did not match the expected result"
    return CaseResult(r.case_id, r.position, r.outcome, r.duration_ms, msg, None)


async def run_checks(sandbox, *, files: dict[str, str], checks: dict[str, str], cases: list[SuiteCase],
                     include_hidden: bool, time_limit_ms: int, memory_limit_mb: int) -> list[CaseResult]:
    """Raises SandboxUnavailable on infrastructure problems (the caller retries)."""
    results: list[CaseResult] = []
    groups: dict[tuple[str, str], list[CaseSpec]] = {}
    for c in cases:
        if c.spec.visibility is TestVisibility.HIDDEN and not include_hidden:
            continue
        groups.setdefault((c.suite, c.spec.visibility.value), []).append(c.spec)
    for (suite, visibility), specs in sorted(groups.items()):
        if not sandbox.executes:
            results += [CaseResult(s.id, s.position, TestOutcome.NOT_EXECUTED, None, "Mock runner: not executed", None)
                        for s in specs]
            continue
        req = ProjectExecRequest(
            suite=suite, visibility=visibility, files=files,
            # Hidden check source is attached only to hidden runs.
            checks={"public": checks.get(f"{suite}:public", ""),
                    "hidden": checks.get(f"{suite}:hidden", "") if visibility == "hidden" else ""},
            cases=specs, time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb,
        )
        res = await sandbox.run_project(req)
        graded = grade(specs, res.stdout, killed_for_time=res.killed_for_time)
        if res.output_truncated:
            graded = [r if r.outcome is TestOutcome.PASSED else
                      CaseResult(r.case_id, r.position, TestOutcome.ERROR, r.duration_ms, "Output limit exceeded", None)
                      for r in graded]
        if visibility == "hidden":
            graded = [_redact_hidden(r) for r in graded]
        results += graded
    return sorted(results, key=lambda r: r.position)
