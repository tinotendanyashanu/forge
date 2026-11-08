"""Execute P5 lesson examples and check the additive curriculum contract.

Run from api/: venv/bin/python tools/validate_p5.py
SQL examples require FORGE_P5_DATABASE_URL pointing at a local forge_p5_* database.
No migration, seed or production connection is performed by this script.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from app.curriculum.graph import load_curriculum
from app.seed.lessons import LESSON_DIR, load_lessons
from app.seed.schema import load_seed_files

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "8062fa9"
EXPECTED = {
    "choosing-data-structures": ("programming-fundamentals", "data-structures"),
    "reasoning-about-complexity": ("programming-fundamentals", "complexity"),
    "python-objects-equality-and-copying": ("python", "data-model"),
    "python-functions-scope-and-closures": ("python", "functions"),
    "sql-querying-joins-and-nulls": ("sql", "querying"),
    "postgres-indexes-and-query-plans": ("sql", "indexing"),
    "typescript-runtime-boundaries": ("typescript", "type-system"),
    "typescript-generics-that-preserve-relationships": ("typescript", "generics"),
    "http-caching-and-validation": ("http", "caching"),
    "browser-origins-cors-and-csrf": ("http", "browser-security"),
}
FENCES = re.compile(r"^```([^\n]*)\n(.*?)^```\s*$", re.M | re.S)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)


def baseline_contract() -> int:
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE, "api/app/seed", "api/app/curriculum"],
        cwd=ROOT, text=True,
    ).splitlines()
    assert len(files) >= 45, "Baseline inventory must include existing questions, metadata and lessons"
    for name in files:
        original = subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original, f"Existing content changed: {name}"
    return len(files)


async def sql_examples(code: str, slug: str) -> dict:
    url = os.environ["FORGE_P5_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    target = urlsplit(url)
    assert target.hostname in {"localhost", "127.0.0.1"}, "Only local scratch databases are permitted"
    assert target.path.startswith("/forge_p5_"), "Use a dedicated forge_p5_* database"
    conn = await asyncpg.connect(url)
    results, plans = [], []
    try:
        version = await conn.fetchval("SHOW server_version")
        # These lesson scripts contain no semicolons inside literals or procedures.
        for statement in code.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            if statement.startswith("SELECT"):
                results.append([list(row) for row in await conn.fetch(statement)])
            elif statement.startswith("EXPLAIN"):
                plans.append([row[0] for row in await conn.fetch(statement)])
            else:
                await conn.execute(statement)
    finally:
        await conn.close()
    if slug == "sql-querying-joins-and-nulls":
        expected = [[[1, "Asha", 1, 40], [2, "Bo", 0, 0], [3, "Cy", 0, 0]],
                    [[1, 2, 2], [2, 1, 0], [3, 1, 1]], [[13]], []]
    else:
        expected = [[[19907], [19807], [19707]], [[19607], [19507], [19407]], [[123]]]
        assert len(plans) == 2
    assert results == expected, (slug, results, expected)
    return {"results": results, "plans": plans, "server_version": version}


async def disputed_postgres_claims() -> dict:
    url = os.environ["FORGE_P5_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("BEGIN; CREATE TEMP TABLE p5_rollback_probe(id integer); ROLLBACK;")
        absent = await conn.fetchval("SELECT to_regclass('pg_temp.p5_rollback_probe') IS NULL")
        assert absent, "CREATE TEMP TABLE inside a rolled-back transaction must be undone"
        await conn.execute("BEGIN; CREATE TEMP TABLE p5_dependency_probe(id integer PRIMARY KEY, name text); "
                           "INSERT INTO p5_dependency_probe VALUES(1, 'Ada');")
        dependent = await conn.fetch("SELECT id, name, count(*) FROM p5_dependency_probe GROUP BY id")
        assert [list(row) for row in dependent] == [[1, "Ada", 1]]
        try:
            await conn.fetch("SELECT id, name, count(*) FROM p5_dependency_probe GROUP BY name")
        except asyncpg.GroupingError:
            invalid_grouping_rejected = True
        else:
            raise AssertionError("An arbitrary ungrouped id should be rejected")
        finally:
            await conn.execute("ROLLBACK")
        await conn.execute("BEGIN; CREATE TEMP TABLE p5_case_probe(email text COLLATE \"C\"); "
                           "INSERT INTO p5_case_probe SELECT 'User' || n || '@example.test' FROM generate_series(1, 20000) n; "
                           "CREATE INDEX p5_case_lower ON p5_case_probe(lower(email)); ANALYZE p5_case_probe;")
        plan = [row[0] for row in await conn.fetch("EXPLAIN SELECT email FROM p5_case_probe WHERE lower(email)='user123@example.test'")]
        assert any("p5_case_lower" in line for line in plan), plan
        await conn.execute("ROLLBACK")
        return {"transactional_temp_ddl_undone": absent, "group_by_primary_key": [list(row) for row in dependent],
                "invalid_grouping_rejected": invalid_grouping_rejected, "case_sensitive_collation_expression_index": plan}
    finally:
        await conn.close()


def main() -> None:
    original_files_checked = baseline_contract()
    curriculum, checksum = load_curriculum()
    questions = {q.slug: (f.skill.slug, q) for f in load_seed_files() for q in f.questions}
    lessons = load_lessons(curriculum, set(questions))
    assert len({x.body for x in lessons}) == len(lessons), "Duplicated lesson bodies"
    originals = [x for x in lessons if x.slug not in EXPECTED]
    covered_before = {(x.skill, x.topic) for x in originals}
    assert len(lessons) == 25 and len(originals) == 15 and len(questions) == 158
    assert set(EXPECTED) <= {x.slug for x in lessons}
    report = {"baseline": BASELINE, "existing_seed_files_checked": original_files_checked,
              "curriculum_checksum": checksum, "examples": []}
    for lesson in lessons:
        if lesson.slug not in EXPECTED:
            continue
        pair = (lesson.skill, lesson.topic)
        assert lesson.status == "reviewed", "P5 is AI-reviewed, not human-verified"
        assert pair == EXPECTED[lesson.slug] and pair not in covered_before
        for slug in lesson.checks:
            skill, question = questions[slug]
            assert (skill, question.topic) == pair, (lesson.slug, slug, "incorrect assessment mapping")
        blocks = FENCES.findall(lesson.body)
        executable = [(i, lang, code) for i, (lang, code) in enumerate(blocks) if lang != "text"]
        assert len(executable) == 1, (lesson.slug, "Update validator for multiple examples")
        i, language, code = executable[0]
        result = {"slug": lesson.slug, "language": language, "mapping": pair, "checks": lesson.checks}
        if language == "sql":
            result.update(asyncio.run(sql_examples(code, lesson.slug)))
        else:
            assert blocks[i + 1][0] == "text", (lesson.slug, "Missing expected output")
            expected_output = blocks[i + 1][1].strip()
            if language == "python":
                output = run(sys.executable, "-c", code).stdout.strip()
            elif language == "typescript":
                with tempfile.TemporaryDirectory(prefix="forge-p5-ts-") as directory:
                    source = Path(directory, "example.ts")
                    source.write_text(code)
                    tsc = str(ROOT / "web/node_modules/.bin/tsc")
                    flags = ["--strict", "--noUncheckedIndexedAccess", "--target", "ES2022", "--module", "commonjs", "--skipLibCheck"]
                    run(tsc, str(source), *flags)
                    output = run("node", str(source.with_suffix(".js"))).stdout.strip()
                    negative_count = code.count("@ts-expect-error")
                    assert negative_count
                    source.write_text(re.sub(r"^.*@ts-expect-error.*\n", "", code, flags=re.M))
                    negative = subprocess.run([tsc, str(source), *flags, "--noEmit"], capture_output=True, text=True, timeout=60)
                    diagnostics = [line for line in negative.stdout.splitlines() if "error TS" in line]
                    assert negative.returncode != 0 and len(diagnostics) == negative_count, diagnostics
                    result["expected_compile_errors"] = diagnostics
                    if lesson.slug == "typescript-runtime-boundaries":
                        # Reject the reviewer's claim that guarded properties become any.
                        source.write_text(code.replace("return { id: value.id, name: value.name };",
                                                       "const rejected: string = value.id; return { id: value.id, name: value.name };"))
                        probe = subprocess.run([tsc, str(source), *flags, "--noEmit"], capture_output=True, text=True, timeout=60)
                        assert probe.returncode != 0 and "Type 'number' is not assignable to type 'string'" in probe.stdout, probe.stdout
                        result["in_operator_narrows_to_number"] = True
            else:
                raise AssertionError(f"Unexecuted code language: {language}")
            assert output == expected_output, (lesson.slug, output, expected_output)
            result["stdout"] = output
        report["examples"].append(result)
    report["coverage"] = {"skills": len(curriculum.skills), "subskills": 45, "questions": len(questions),
                          "lessons": len(lessons), "covered_subskills": len({(x.skill, x.topic) for x in lessons})}
    report["review_disagreement_probes"] = asyncio.run(disputed_postgres_claims())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
