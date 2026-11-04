"""Runs inside the sandbox for engineering projects. Calls trusted check
functions, which drive the learner's multi-file project, and prints their raw
observations. It never sees expected values: grading happens in the worker.

Usage: python -I -B harness.py <per_case_ms> <public|hidden>
Layout: /work/project/** (learner files, read-only), /work/checks_public.py,
/work/checks_hidden.py (hidden runs only), /work/cases.json.
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
        return {"__float__": repr(v)} if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, (list, tuple)):
        return [to_json(x, depth + 1) for x in v]
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
    per_case_ms, which = int(sys.argv[1]), sys.argv[2]
    with open(os.path.join(WORK, "cases.json")) as f:
        cases = json.load(f)
    # Trusted checks load first, so a learner module can't shadow them.
    checks = load("checks_public", os.path.join(WORK, "checks_public.py"))
    if which == "hidden":
        checks = load("checks_hidden", os.path.join(WORK, "checks_hidden.py"))
    # Appended, not prepended: learner files can't shadow the standard library.
    sys.path.append(os.path.join(WORK, "project"))
    signal.signal(signal.SIGALRM, on_alarm)
    sys.stdout = io.StringIO()  # learner prints are not part of the result channel
    for c in cases:
        fn = getattr(checks, c["call"], None)
        start = time.perf_counter()
        try:
            if fn is None:
                raise LookupError("unknown check")
            signal.setitimer(signal.ITIMER_REAL, per_case_ms / 1000)
            value = fn(*c["args"])
            signal.setitimer(signal.ITIMER_REAL, 0)
            emit({"id": c["id"], "ok": True, "value": to_json(value), "ms": int((time.perf_counter() - start) * 1000)})
        except CaseTimeout:
            emit({"id": c["id"], "ok": False, "error": {"type": "Timeout", "message": "", "phase": "timeout"}, "ms": per_case_ms})
        except BaseException as exc:  # noqa: BLE001 - learner code may raise anything
            signal.setitimer(signal.ITIMER_REAL, 0)
            emit({"id": c["id"], "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)[:500], "phase": "call"},
                  "ms": int((time.perf_counter() - start) * 1000)})


main()
