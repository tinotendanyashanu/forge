"""The content quality gate must pass for the committed question bank (offline checks)."""

import json

from app.seed import qa
from app.seed.schema import load_seed_files


def test_quality_gate_has_no_errors():
    report = qa.Report()
    questions = qa.check_questions(report)
    qa.check_meta(report, questions)
    assert report.errors == []


def test_metadata_covers_every_new_skill_file():
    meta_files = sorted(qa.META_DIR.glob("*.meta.json"))
    assert meta_files, "expected QA metadata for authored batches"
    seeded = {q.slug for f in load_seed_files() for q in f.questions}
    for path in meta_files:
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert set(meta["questions"]) <= seeded


def test_every_skill_has_two_scored_questions_per_level_where_authored_with_metadata():
    """Batches authored under the workflow must make every level verifiable."""
    files = {f.skill.slug: f for f in load_seed_files()}
    for path in sorted(qa.META_DIR.glob("*.meta.json")):
        skill = json.loads(path.read_text(encoding="utf-8"))["skill"]
        for level in ("beginner", "intermediate", "advanced"):
            scored = [
                q for q in files[skill].questions
                if q.difficulty.value == level and q.format.value == "single_choice"
            ]
            assert len(scored) >= 2, f"{skill}/{level} has {len(scored)} scored questions"
