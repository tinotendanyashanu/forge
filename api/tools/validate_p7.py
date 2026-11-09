"""Validate P7 mappings, immutable P6 content, and worked examples.

Run from api/: venv/bin/python tools/validate_p7.py > /private/tmp/p7-examples.json
The container example uses the local Docker engine and the already present
python:3.12-slim image. It does not enable FORGE's coding sandbox.
The shell example prints a dangerous expansion and never executes it.
"""
from __future__ import annotations

import difflib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.curriculum.graph import load_curriculum
from app.seed.lessons import load_lessons
from app.seed.schema import load_seed_files

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "25c4b6ff80b418b298d11f530f582072a240b617"
EXPECTED = {
    "container-image-layers-and-signals": ("devops", "containers"),
    "observability-tails-traces-and-cardinality": ("devops", "observability"),
    "scaling-capacity-replicas-and-hotspots": ("system-design", "scaling"),
    "reliability-jitter-queues-and-availability": ("system-design", "reliability"),
    "consistency-replica-lag-and-conflicts": ("distributed-systems", "consistency"),
    "messaging-delivery-outbox-and-order": ("distributed-systems", "messaging"),
    "technical-decisions-records-and-reversibility": ("senior-practices", "decision-making"),
    "incident-response-mitigation-and-follow-up": ("senior-practices", "incidents"),
    "git-history-amend-revert-and-recovery": ("git", "history"),
    "linux-shell-redirection-pipelines-and-expansion": ("linux", "shell"),
}
FENCES = re.compile(r"^```([^\n]*)\n(.*?)^```\s*$", re.M | re.S)


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=kwargs.pop("timeout", 90), **kwargs)


def examples():
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE, "api/app/seed", "api/app/curriculum", "api/app/mastery/algorithm.py"],
        cwd=ROOT, text=True).splitlines()
    assert len(files) == 75, len(files)
    for name in files:
        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT), name
    curriculum, checksum = load_curriculum()
    assert checksum == "4f4eb928bee1243b526cb3bfdbc725f0b894acb5b63fe8b8f6a9b0063fdc0941"
    questions = {q.slug: (f.skill.slug, q) for f in load_seed_files() for q in f.questions}
    lessons = load_lessons(curriculum, set(questions))
    assert len(lessons) == 45 and len(questions) == 158
    assert len({x.body for x in lessons}) == 45
    old = [x for x in lessons if x.slug not in EXPECTED]
    assert len(old) == 35
    before = {(x.skill, x.topic) for x in old}
    report = {"baseline": BASELINE, "existing_files_unchanged": len(files), "curriculum_checksum": checksum,
              "human_verified": False, "examples": []}
    report["runtime_versions"] = {name: importlib.metadata.version(name) for name in ["fastapi", "starlette", "anyio", "httpx", "pytest"]}
    report["runtime_versions"]["python"] = sys.version.split()[0]
    report["runtime_versions"]["git"] = run(["git", "--version"]).stdout.strip()
    report["runtime_versions"]["bash"] = run(["bash", "--version"]).stdout.splitlines()[0]
    report["linux_image_id"] = run(["docker", "image", "inspect", "python:3.12-slim", "--format", "{{.Id}}"]).stdout.strip()
    ratios = []
    for lesson in lessons:
        if lesson.slug not in EXPECTED:
            continue
        pair = (lesson.skill, lesson.topic)
        assert pair == EXPECTED[lesson.slug] and pair not in before, lesson.slug
        assert lesson.status == "reviewed", "P7 is advisory-reviewed, not human-verified"
        assert "human subject-matter verification" in lesson.provenance
        for check in lesson.checks:
            skill, question = questions[check]
            assert (skill, question.topic) == pair, (lesson.slug, check)
            assert question.topic == lesson.topic
        for previous in old:
            ratios.append(difflib.SequenceMatcher(None, lesson.body, previous.body).ratio())
        blocks = FENCES.findall(lesson.body)
        code = [(language, source) for language, source in blocks if language != "text"]
        assert len(code) == 1, lesson.slug
        expected = next(value.strip() for kind, value in blocks if kind == "text")
        language, source = code[0]
        item = {"slug": lesson.slug, "mapping": list(pair), "checks": lesson.checks,
                "words": len(lesson.body.split()), "resources": len(lesson.resources)}
        if lesson.slug == "container-image-layers-and-signals":
            assert language == "bash"
            output = run(["bash", "-c", source], timeout=240).stdout.strip()
            item["isolation"] = {"engine": "local docker", "image": "python:3.12-slim", "pull": False,
                                 "sandbox": "FORGE coding sandbox not used"}
        elif lesson.slug == "git-history-amend-revert-and-recovery":
            assert language == "bash"
            assert "push" not in source and "remote add" not in source
            with tempfile.TemporaryDirectory(prefix="forge-p7-git-") as directory:
                env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": directory,
                       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
                output = run(["bash", "-c", source], cwd=directory, env=env).stdout.strip()
        elif lesson.slug == "linux-shell-redirection-pipelines-and-expansion":
            assert language == "bash"
            rm_lines = [line.strip() for line in source.splitlines() if line.strip().startswith("rm ")]
            assert rm_lines == ['rm -rf "$root"'], rm_lines
            assert "rm -rf /" not in source
            with tempfile.TemporaryDirectory(prefix="forge-p7-shell-") as directory:
                env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": directory}
                script = Path(directory, "shell-failures.sh")
                script.write_text(source)
                # The lesson's text fence is this file execution. bash -c on Bash 3.2.57
                # reports a different non-zero status for the two guard subshells.
                output = run(["bash", str(script)], cwd=directory, env=env).stdout.strip()
                dash_c = run(["bash", "-c", source], cwd=directory, env=env).stdout.strip()
            probe = run(["bash", "-c", 'set -u; BUILD_DIR=; printf \'%s\\n\' "rm -rf ${BUILD_DIR-}/*"'])
            assert probe.stdout.strip() == "rm -rf /*"
            item["empty_variable_probe"] = {"stdout": probe.stdout.strip(), "status": probe.returncode, "rm_executed": False}
            item["bash_c_stdout"] = dash_c
            if report["runtime_versions"]["bash"].startswith("GNU bash, version 3.2.57"):
                assert "nounset 127" in dash_c and "required_guard 127" in dash_c
            linux_args = [
                "docker", "run", "--rm", "-i", "--pull=never", "--network=none",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only",
                "--memory=128m", "--cpus=0.5", "--pids-limit=32",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m", "--user=65534:65534",
                "--entrypoint=bash", "python:3.12-slim",
            ]
            linux = run(linux_args + ["-s"], input=source).stdout.strip()
            assert linux == expected, (lesson.slug, "Linux Bash", linux, expected)
            item["linux_bash"] = {
                "version": run(linux_args + ["--version"]).stdout.splitlines()[0],
                "stdout": linux, "network": "none", "user": "65534:65534",
                "read_only_root": True,
            }
        else:
            assert language == "python"
            output = run([sys.executable, "-c", source]).stdout.strip()
        assert output == expected, (lesson.slug, output, expected)
        item["stdout"] = output
        report["examples"].append(item)
    assert len(report["examples"]) == 10
    report["max_body_similarity_to_existing"] = round(max(ratios), 3)
    report["coverage"] = {
        "skills": len(curriculum.skills),
        "subskills": 45,
        "lessons": 45,
        "covered_subskills": len({(x.skill, x.topic) for x in lessons}),
        "questions": len(questions),
        "lesson_checks": sum(len(x.checks) for x in lessons),
        "lesson_resources": sum(len(x.resources) for x in lessons),
        "new_check_links": sum(len(x.checks) for x in lessons if x.slug in EXPECTED),
        "new_resources": sum(len(x.resources) for x in lessons if x.slug in EXPECTED),
    }
    assert report["coverage"]["covered_subskills"] == 45
    assert report["coverage"]["lesson_checks"] == 147
    assert report["coverage"]["lesson_resources"] == 157
    assert report["coverage"]["new_check_links"] == 35
    assert report["coverage"]["new_resources"] == 34
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    examples()
