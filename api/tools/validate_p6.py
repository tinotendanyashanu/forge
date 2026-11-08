"""Validate P6 mappings, immutable P5 content, and non-browser worked examples.

Run from api/: venv/bin/python tools/validate_p6.py > /private/tmp/p6-examples.json
Docker is used only for isolated Linux/dummy-security fixtures, never FORGE's coding sandbox.
"""
from __future__ import annotations

import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.curriculum.graph import load_curriculum
from app.seed.lessons import LESSON_DIR, load_lessons
from app.seed.schema import load_seed_files
from fastapi import Depends

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "f26daf2d8e5f8d6fdec1db8334baeebd5a3ce61c"
EXPECTED = {
    "react-list-identity-and-derived-data": ("react", "lists"),
    "react-effects-and-request-lifetimes": ("react", "effects"),
    "fastapi-dependency-lifetimes-and-overrides": ("fastapi", "dependencies"),
    "fastapi-async-handlers-and-bounded-work": ("fastapi", "async-handlers"),
    "test-doubles-fixtures-and-patching": ("testing", "test-doubles"),
    "reliable-tests-time-state-and-order": ("testing", "reliability"),
    "injection-safe-data-boundaries": ("security", "injection"),
    "secrets-storage-rotation-and-exposure": ("security", "secrets"),
    "git-commits-index-and-object-identity": ("git", "commits"),
    "linux-filesystem-paths-and-permissions": ("linux", "filesystem"),
}
FENCES = re.compile(r"^```([^\n]*)\n(.*?)^```\s*$", re.M | re.S)


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90, **kwargs)


def examples():
    files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASELINE,
                                     "api/app/seed", "api/app/curriculum", "api/app/mastery/algorithm.py"], cwd=ROOT, text=True).splitlines()
    assert len(files) >= 64
    for name in files:
        assert (ROOT/name).read_bytes() == subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT), name
    curriculum, checksum = load_curriculum()
    questions = {q.slug: (f.skill.slug, q) for f in load_seed_files() for q in f.questions}
    lessons = load_lessons(curriculum, set(questions))
    assert len(lessons) == 35 and len(questions) == 158
    assert len({x.body for x in lessons}) == 35
    old = [x for x in lessons if x.slug not in EXPECTED]
    assert len(old) == 25
    before = {(x.skill, x.topic) for x in old}
    report = {"baseline": BASELINE, "existing_files_unchanged": len(files), "curriculum_checksum": checksum, "examples": []}
    report["runtime_versions"] = {name:importlib.metadata.version(name) for name in ["fastapi","starlette","anyio","httpx","pytest"]}
    report["runtime_versions"]["python"] = sys.version.split()[0]
    report["runtime_versions"]["git"] = run(["git","--version"]).stdout.strip()
    report["fastapi_depends_exposes_scope"] = "scope" in inspect.signature(Depends).parameters
    assert report["fastapi_depends_exposes_scope"]
    report["linux_image_id"] = run(["docker","image","inspect","python:3.12-slim","--format","{{.Id}}"]).stdout.strip()
    for lesson in lessons:
        if lesson.slug not in EXPECTED:
            continue
        pair = (lesson.skill, lesson.topic)
        assert pair == EXPECTED[lesson.slug] and pair not in before
        assert lesson.status == "reviewed", "P6 is advisory-reviewed, not human-verified"
        for check in lesson.checks:
            skill, question = questions[check]
            assert (skill, question.topic) == pair, (lesson.slug, check)
        blocks = FENCES.findall(lesson.body)
        code = [(language, source) for language, source in blocks if language != "text"]
        item = {"slug": lesson.slug, "mapping": pair, "checks": lesson.checks, "code_blocks": len(code)}
        if lesson.skill == "react":
            assert len(code) == 1 and code[0][0] == "jsx"
            item["verification"] = "See p6-browser.json for actual React/Chromium execution"
        elif lesson.skill == "testing":
            names = ["price_gateway.py", "billing.py", "test_billing.py"] if lesson.topic == "test-doubles" else ["test_cache_lifetime.py"]
            assert len(names) == len(code)
            with tempfile.TemporaryDirectory(prefix="forge-p6-tests-") as directory:
                for name, (language, source) in zip(names, code, strict=True):
                    assert language == "python"
                    Path(directory, name).write_text(source)
                env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                       "PYTHONPATH": directory, "TZ": "UTC", "PYTHONHASHSEED": "1"}
                base = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "--rootdir", directory]
                collection = run([*base, "--collect-only"], cwd=directory, env=env).stdout
                nodes = [line for line in collection.splitlines() if line.startswith("test_") and "::" in line]
                count = 4 if lesson.topic == "test-doubles" else 5
                assert len(nodes) == count, collection
                runs = []
                for reverse, seed, tz in [(False,"1","UTC"), (True,"1","UTC"), (False,"42","America/New_York")]:
                    output = run([*base, *(reversed(nodes) if reverse else nodes)], cwd=directory,
                                 env={**env,"PYTHONHASHSEED":seed,"TZ":tz}).stdout
                    assert re.search(rf"\b{count} passed\b", output), output
                    runs.append({"reverse":reverse,"hash_seed":seed,"timezone":tz,"passed":count})
                item.update(unique_tests=count, runs=runs)
        else:
            assert len(code) == 1
            language, source = code[0]
            expected = next(value.strip() for kind, value in blocks if kind == "text")
            if lesson.skill in {"security", "linux"}:
                # No host mounts, network, credentials, writable root filesystem or capabilities.
                command = ["docker","run","--rm","--pull=never","--network=none","--read-only",
                           "--user=65534:65534","--cap-drop=ALL","--security-opt=no-new-privileges",
                           "--pids-limit=32","--memory=128m","--cpus=0.5","--ulimit=fsize=1048576:1048576",
                           "--tmpfs=/tmp:rw,nosuid,noexec,size=16m,mode=1777","python:3.12-slim",
                           "env","-i","PATH=/usr/local/bin:/usr/bin:/bin","TMPDIR=/tmp","timeout","20s","python","-I","-c",source]
                output = run(command).stdout.strip()
                item["isolation"] = {"image":"python:3.12-slim","user":"65534:65534","network":"none",
                                      "read_only_root":True,"capabilities":"none","memory_mb":128,
                                      "cpus":0.5,"pids":32,"scratch_mb":16,"container_timeout_seconds":20,"host_timeout_seconds":90}
            elif language == "bash":
                with tempfile.TemporaryDirectory(prefix="forge-p6-git-") as directory:
                    env = {"PATH":os.environ.get("PATH","/usr/bin:/bin"),"TMPDIR":directory,
                           "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null"}
                    output = run(["bash","-c",source], cwd=directory, env=env).stdout.strip()
            else:
                assert language == "python"
                output = run([sys.executable,"-c",source]).stdout.strip()
            assert output == expected, (lesson.slug, output, expected)
            item["stdout"] = output
        report["examples"].append(item)
    assert len(report["examples"]) == 10
    report["coverage"] = {"skills":len(curriculum.skills),"subskills":45,"lessons":35,"covered_subskills":len({(x.skill,x.topic) for x in lessons}),
                          "questions":len(questions),"new_check_links":sum(len(x.checks) for x in lessons if x.slug in EXPECTED),
                          "new_resources":sum(len(x.resources) for x in lessons if x.slug in EXPECTED)}
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    examples()
