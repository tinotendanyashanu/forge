"""Content quality checks for authored assessment questions.

Run from ``api/``::

    venv/bin/python -m app.seed.qa              # offline checks
    venv/bin/python -m app.seed.qa --check-urls # also fetch every resource URL

Errors block publication (exit code 1). Warnings are reported for review.
These checks are a gate, not a substitute for technical review: they cannot
tell whether an explanation is correct. See docs/curriculum/CONTENT_WORKFLOW.md.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import difflib
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from app.curriculum.graph import load_curriculum
from app.seed.lessons import LessonSeed, load_lessons
from app.seed.schema import CONTENT_DIR, SeedQuestion, load_seed_files

META_DIR = CONTENT_DIR.parent / "meta"
META_STATUSES = {"draft", "reviewed", "verified", "needs-improvement", "rejected", "archived"}
META_REQUIRED = {"version", "status", "provenance", "learning_objective", "prerequisites"}
DUPLICATE_THRESHOLD = 0.6
LENGTH_TELL_RATIO = 1.3
MIN_EXPLANATION = 120
MIN_RUBRIC = 3
POSITIONAL = re.compile(
    r"\boption\s+`?[a-f]`?\b|\b(first|second|third|fourth|last)\s+(option|answer|choice)\b"
    r"|\bthe other (two|three|four)\b|\boptions?\s+[a-f]\s*(,|and|or)\s*[a-f]\b",
    re.I,
)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)


def _text(q: SeedQuestion) -> str:
    return (q.prompt + "\n" + (q.code or "")).lower()


def check_questions(report: Report) -> list[tuple[str, SeedQuestion]]:
    try:
        files = load_seed_files()
    except Exception as exc:  # schema errors are fatal
        report.errors.append(f"schema: {exc}")
        return []
    questions = [(f.skill.slug, q) for f in files for q in f.questions]
    report.stats["questions"] = len(questions)
    report.stats["by_skill_level_scored"] = {
        f.skill.slug: {
            d: sum(1 for q in f.questions if q.difficulty.value == d and q.format.value == "single_choice")
            for d in ("beginner", "intermediate", "advanced")
        }
        for f in files
    }
    for skill, levels in report.stats["by_skill_level_scored"].items():  # type: ignore[union-attr]
        for level, n in levels.items():
            if n < 2:
                report.warnings.append(
                    f"{skill}/{level}: {n} scored question(s); mastery needs 2 distinct to verify"
                )

    keys = collections.Counter()
    for skill, q in questions:
        sid = f"{skill}/{q.slug}"
        if len(q.explanation) < MIN_EXPLANATION:
            report.warnings.append(f"{sid}: explanation shorter than {MIN_EXPLANATION} characters")
        if len(q.rubric) < MIN_RUBRIC:
            report.warnings.append(f"{sid}: fewer than {MIN_RUBRIC} rubric criteria")
        if not q.hint:
            report.warnings.append(f"{sid}: no hint")
        if q.format.value != "single_choice":
            continue
        # Options are shuffled per session item, so text must never refer to
        # an option by letter or position.
        for field_name in ("prompt", "explanation", "acceptance_criteria", "hint"):
            value = getattr(q, field_name) or ""
            if POSITIONAL.search(value):
                report.errors.append(
                    f"{sid}: {field_name} refers to an option by letter or position"
                )
        correct = next(o for o in q.options if o.correct)
        keys[correct.key] += 1
        lengths = sorted((len(o.text) for o in q.options), reverse=True)
        if len(correct.text) == lengths[0] and lengths[0] > LENGTH_TELL_RATIO * lengths[1]:
            report.warnings.append(f"{sid}: correct option is much longer than every distractor")
        if any(re.search(r"\b(all|none) of the above\b", o.text, re.I) for o in q.options):
            report.warnings.append(f"{sid}: uses 'all/none of the above'")
        if len(q.options) < 4:
            report.warnings.append(f"{sid}: fewer than 4 options")
    report.stats["correct_key_distribution"] = dict(sorted(keys.items()))
    total = sum(keys.values())
    if total and max(keys.values()) > 0.5 * total:
        report.warnings.append(
            f"correct answers cluster on one option key: {dict(sorted(keys.items()))}"
        )

    dups = []
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            a, b = questions[i][1], questions[j][1]
            ratio = difflib.SequenceMatcher(None, _text(a), _text(b)).ratio()
            if ratio > DUPLICATE_THRESHOLD:
                dups.append((a.slug, b.slug, round(ratio, 2)))
    report.stats["near_duplicates"] = dups
    for a, b, r in dups:
        report.warnings.append(f"near-duplicate ({r}): {a} / {b}")
    return questions


def check_meta(report: Report, questions: list[tuple[str, SeedQuestion]]) -> None:
    slugs = {q.slug for _, q in questions}
    covered: set[str] = set()
    for path in sorted(META_DIR.glob("*.meta.json")) if META_DIR.exists() else []:
        meta = json.loads(path.read_text(encoding="utf-8"))
        for slug, entry in meta.get("questions", {}).items():
            if slug not in slugs:
                report.errors.append(f"{path.name}: metadata for unknown question {slug}")
                continue
            covered.add(slug)
            missing = META_REQUIRED - entry.keys()
            if missing:
                report.errors.append(f"{path.name}:{slug}: missing metadata {sorted(missing)}")
            if entry.get("status") not in META_STATUSES:
                report.errors.append(f"{path.name}:{slug}: invalid status {entry.get('status')!r}")
    report.stats["questions_with_metadata"] = len(covered)
    report.stats["questions_without_metadata"] = len(slugs - covered)


def check_lessons(report: Report, questions: list[tuple[str, SeedQuestion]]) -> list[LessonSeed]:
    try:
        curriculum, _ = load_curriculum()
        lessons = load_lessons(curriculum, {q.slug for _, q in questions})
    except Exception as exc:  # validation errors are fatal
        report.errors.append(f"lessons: {exc}")
        return []
    report.stats["lessons"] = len(lessons)
    report.stats["lessons_by_skill"] = dict(collections.Counter(x.skill for x in lessons))
    for x in lessons:
        words = len(x.body.split())
        if words < 700:
            report.warnings.append(f"lesson {x.slug}: only {words} words")
        if "```" not in x.body:
            report.warnings.append(f"lesson {x.slug}: no code example")
    return lessons


def _fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FORGE content QA)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return url, str(resp.status)
    except urllib.error.HTTPError as exc:
        return url, str(exc.code)
    except Exception as exc:  # noqa: BLE001 - report any network failure
        return url, f"error:{type(exc).__name__}"


def check_urls(
    report: Report, questions: list[tuple[str, SeedQuestion]], lessons: list[LessonSeed] = ()
) -> None:
    urls = sorted({r.url for _, q in questions for r in q.resources} | {r.url for x in lessons for r in x.resources})
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        results = list(pool.map(_fetch, urls))
    report.stats["urls_checked"] = len(urls)
    report.stats["urls_ok"] = sum(1 for _, s in results if s == "200")
    for url, status in results:
        if status != "200":
            report.errors.append(f"resource {url}: {status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-urls", action="store_true", help="fetch every resource URL")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    report = Report()
    questions = check_questions(report)
    if questions:
        check_meta(report, questions)
        lessons = check_lessons(report, questions)
        if args.check_urls:
            check_urls(report, questions, lessons)

    if args.json:
        print(json.dumps({"errors": report.errors, "warnings": report.warnings, "stats": report.stats}, indent=2))
    else:
        for k, v in report.stats.items():
            print(f"{k}: {v}")
        print(f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        for e in report.errors:
            print(f"ERROR   {e}")
        for w in report.warnings:
            print(f"WARNING {w}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
