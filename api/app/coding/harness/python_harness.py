"""Runs inside the sandbox. Calls the learner's code with each case's inputs and
prints raw outputs. It never sees expected values: grading happens outside.

Usage: python -I -B harness.py <per_case_ms>
Reads /work/cases.json: [{"id": int, "call": "fn" | "driver:fn", "args": [...]}]
Writes one line per case: @@FORGE@@{"id", "ok", "value" | "error", "ms"}
"""

import importlib.util
import io
import json
import math
import os
import signal
import sys
import time

MARK = "@@FORGE@@"
WORK = "/work"
real_stdout_fd = os.dup(1)


class CaseTimeout(BaseException):
    pass


def emit(obj):
    os.write(real_stdout_fd, (MARK + json.dumps(obj, separators=(",", ":")) + "\n").encode())


def to_json(v, depth=0):
    if depth > 50:
        return {"__repr__": "<too deep>"}
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return {"__float__": repr(v)}
        return v
    if isinstance(v, (list, tuple)):
        return [to_json(x, depth + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        items = [to_json(x, depth + 1) for x in v]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(v, dict):
        return {str(k): to_json(x, depth + 1) for k, x in v.items()}
    return {"__repr__": repr(v)[:200]}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def on_alarm(signum, frame):
    raise CaseTimeout()


def main():
    per_case_ms = int(sys.argv[1])
    with open(os.path.join(WORK, "cases.json")) as f:
        cases = json.load(f)
    signal.signal(signal.SIGALRM, on_alarm)
    sys.stdout = io.StringIO()  # learner prints are not part of the result channel
    try:
        signal.setitimer(signal.ITIMER_REAL, per_case_ms / 1000 * 2)
        solution = load("solution", os.path.join(WORK, "solution.py"))
        signal.setitimer(signal.ITIMER_REAL, 0)
    except BaseException as exc:  # noqa: BLE001 - report any import failure
        signal.setitimer(signal.ITIMER_REAL, 0)
        kind = "timeout" if isinstance(exc, CaseTimeout) else "import"
        for c in cases:
            emit({"id": c["id"], "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)[:500], "phase": kind}, "ms": 0})
        return
    driver = None
    if os.path.exists(os.path.join(WORK, "driver.py")):
        driver = load("driver", os.path.join(WORK, "driver.py"))

    for c in cases:
        call = c["call"]
        if call.startswith("driver:"):
            fn, args = getattr(driver, call.split(":", 1)[1]), [solution, *c["args"]]
        else:
            fn, args = getattr(solution, call, None), c["args"]
        start = time.perf_counter()
        try:
            if fn is None:
                raise AttributeError(f"'{call}' is not defined")
            signal.setitimer(signal.ITIMER_REAL, per_case_ms / 1000)
            value = fn(*args)
            signal.setitimer(signal.ITIMER_REAL, 0)
            emit({"id": c["id"], "ok": True, "value": to_json(value), "ms": int((time.perf_counter() - start) * 1000)})
        except CaseTimeout:
            emit({"id": c["id"], "ok": False, "error": {"type": "Timeout", "message": "", "phase": "timeout"}, "ms": per_case_ms})
        except BaseException as exc:  # noqa: BLE001 - learner code may raise anything
            signal.setitimer(signal.ITIMER_REAL, 0)
            emit({"id": c["id"], "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)[:500], "phase": "call"}, "ms": int((time.perf_counter() - start) * 1000)})


main()
