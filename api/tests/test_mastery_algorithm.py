"""Pure tests for the mastery algorithm, SM-2 scheduling, graph and ranking."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.curriculum.graph import (
    Curriculum,
    CurriculumCycleError,
    ancestors,
    load_curriculum,
    topological_order,
)
from app.db.enums import Difficulty, EvidenceDimension, EvidenceSource, InterviewMode, MasteryState
from app.mastery.algorithm import (
    Evidence,
    apply_review,
    compute_mastery,
    new_card,
    quality_for,
    weight,
)
from app.mastery.service import Gap, SkillContext, recommend

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
B, I, A = Difficulty.BEGINNER, Difficulty.INTERMEDIATE, Difficulty.ADVANCED
ALL_VERIFIABLE = {B, I}  # mirrors the seed: advanced questions are written answers

_n = 0


def ev(
    *, q: int, session: str, level=B, success=True, verified=True, days=0, hints=0, dont_know=False,
    dimension=None, score=None,
) -> Evidence:
    global _n
    _n += 1
    source = (
        EvidenceSource.SELF_REPORT if dont_know
        else EvidenceSource.OBJECTIVE_ASSESSMENT if verified
        else EvidenceSource.AI_INTERVIEW
    )
    return Evidence(
        id=f"e{_n:04d}", question_id=q, session_id=session, difficulty=level, source=source,
        dimension=dimension or (EvidenceDimension.KNOWLEDGE if verified else EvidenceDimension.REASONING),
        verified=verified and not dont_know, score=score if score is not None else (1.0 if success else 0.0),
        success=success and not dont_know, hints_used=hints, said_dont_know=dont_know,
        observed_at=T0 + timedelta(days=days, minutes=_n),
    )


def mastery(evidence, *, verifiable=ALL_VERIFIABLE, reviews=(), recurring=False, now=None):
    return compute_mastery(
        evidence, now=now or T0 + timedelta(days=30), verifiable_levels=set(verifiable),
        due_review_qualities=list(reviews), recurring_misconception=recurring,
    )


# ---------------------------------------------------------------- independence & variety


def test_no_evidence_is_not_started_with_no_scores() -> None:
    r = mastery([])
    assert r.state is MasteryState.NOT_STARTED
    assert r.knowledge_accuracy is None and r.uncertainty is None and r.retention_score is None


def test_one_correct_answer_never_grants_a_level() -> None:
    r = mastery([ev(q=1, session="s1")])
    assert r.state is MasteryState.INSUFFICIENT_EVIDENCE and r.demonstrated_level is None


def test_same_question_twice_is_not_varied_evidence() -> None:
    r = mastery([ev(q=1, session="s1"), ev(q=1, session="s2", days=1)])
    assert r.demonstrated_level is None
    assert any("different questions" in m for m in r.levels[0].missing)


def test_two_questions_in_one_session_are_not_independent() -> None:
    r = mastery([ev(q=1, session="s1"), ev(q=2, session="s1")])
    assert r.demonstrated_level is None
    assert any("separate sessions" in m for m in r.levels[0].missing)


def test_two_questions_two_sessions_demonstrates_beginner() -> None:
    r = mastery([ev(q=1, session="s1"), ev(q=2, session="s2", days=1)])
    assert r.state is MasteryState.DEVELOPING and r.demonstrated_level is B
    assert r.unverified_only is False


# ---------------------------------------------------------------- verified vs unverified


def test_ai_only_success_cannot_demonstrate_a_verifiable_level() -> None:
    r = mastery([ev(q=1, session="s1", verified=False, score=0.9), ev(q=2, session="s2", verified=False, score=0.9)])
    assert r.demonstrated_level is None
    assert any("objectively graded" in m for m in r.levels[0].missing)


def test_ai_only_level_is_flagged_unverified() -> None:
    evidence = [
        ev(q=1, session="s1"), ev(q=2, session="s2"),
        ev(q=3, session="s3", level=I), ev(q=4, session="s4", level=I),
        ev(q=5, session="s5", level=A, verified=False, score=0.9, days=1),
        ev(q=6, session="s6", level=A, verified=False, score=0.9, days=3),
    ]
    r = mastery(evidence)
    assert r.demonstrated_level is A and r.unverified_only is True
    assert any("AI evaluations" in reason for reason in r.reasons)


def test_scores_are_separated_by_source() -> None:
    r = mastery([
        ev(q=1, session="s1", success=True), ev(q=2, session="s2", success=False),
        ev(q=3, session="s3", verified=False, score=0.6),
        ev(q=4, session="s4", verified=False, score=0.8, dimension=EvidenceDimension.DEBUGGING),
    ])
    assert r.knowledge_accuracy is not None and r.knowledge_accuracy < Decimal("1")
    assert r.reasoning_score == Decimal("0.600")
    assert r.debugging_score == Decimal("0.800")
    assert r.practical_score is None  # no verified practical tests exist


# ---------------------------------------------------------------- progression rules


def test_levels_cannot_be_skipped() -> None:
    r = mastery([ev(q=3, session="s1", level=I), ev(q=4, session="s2", level=I)])
    assert r.demonstrated_level is None


def test_recent_failures_withdraw_a_level() -> None:
    evidence = [ev(q=1, session="s1"), ev(q=2, session="s2")] + [
        ev(q=1 + i % 2, session=f"f{i}", success=False, days=2 + i) for i in range(3)
    ]
    r = mastery(evidence)
    assert r.demonstrated_level is None
    assert any("recent accuracy" in m for m in r.levels[0].missing)


def test_dont_know_counts_against_recent_accuracy() -> None:
    evidence = [ev(q=1, session="s1"), ev(q=2, session="s2")] + [
        ev(q=3, session=f"d{i}", dont_know=True, days=3 + i) for i in range(2)
    ]
    assert mastery(evidence).demonstrated_level is None


def test_inconsistency_is_flagged() -> None:
    evidence = [
        ev(q=1, session="a"), ev(q=2, session="b", success=False),
        ev(q=1, session="c"), ev(q=2, session="d", success=False),
    ]
    assert mastery(evidence).inconsistent is True


def _full_ladder(adv_days=(1, 1)) -> list[Evidence]:
    return [
        ev(q=1, session="b1"), ev(q=2, session="b2"),
        ev(q=3, session="i1", level=I), ev(q=4, session="i2", level=I),
        ev(q=5, session="a1", level=A, verified=False, score=0.9, days=adv_days[0]),
        ev(q=6, session="a2", level=A, verified=False, score=0.9, days=adv_days[1]),
    ]


def test_mastery_requires_advanced_success_on_separate_days() -> None:
    same_day = mastery(_full_ladder((1, 1)))
    assert same_day.state is MasteryState.PROFICIENT and same_day.demonstrated_level is A
    assert "different days" in same_day.reasons[0]
    assert mastery(_full_ladder((1, 4))).state is MasteryState.MASTERED


def test_failed_review_or_recurring_misconception_blocks_mastery() -> None:
    assert mastery(_full_ladder((1, 4)), reviews=[5, 2]).state is MasteryState.PROFICIENT
    assert mastery(_full_ladder((1, 4)), recurring=True).state is MasteryState.PROFICIENT


def test_recency_halves_weight_every_45_days() -> None:
    e = ev(q=1, session="s")
    assert weight(e, e.observed_at) == pytest.approx(1.0)
    assert weight(e, e.observed_at + timedelta(days=45)) == pytest.approx(0.5)
    ai = ev(q=1, session="s", verified=False, score=1)
    assert weight(ai, ai.observed_at) == pytest.approx(0.5)


def test_result_is_deterministic() -> None:
    evidence = _full_ladder((1, 4))
    assert mastery(evidence) == mastery(list(reversed(evidence)))


# ---------------------------------------------------------------- SM-2 scheduling


def test_sm2_intervals_grow_on_success() -> None:
    card, at, intervals = new_card(T0), T0, []
    for _ in range(3):
        out = apply_review(card, 5, at)
        card, at = out.card, out.card.due_at
        intervals.append(card.interval_days)
    assert intervals == [1, 6, 16]
    assert card.ease == Decimal("2.80")


def test_failed_review_reschedules_for_tomorrow_and_counts_a_lapse() -> None:
    card = apply_review(new_card(T0), 5, T0).card  # learned
    out = apply_review(card, 1, card.due_at)
    assert out.card.interval_days == 1 and out.card.repetitions == 0
    assert out.card.due_at == card.due_at + timedelta(days=1)  # not "now": no same-day loop
    assert out.card.lapses == 1 and out.card.consecutive_lapses == 1


def test_first_ever_failure_is_not_a_lapse() -> None:
    out = apply_review(new_card(T0), 1, T0)
    assert out.card.lapses == 0 and out.card.consecutive_lapses == 1


def test_cramming_before_due_does_not_extend_interval() -> None:
    card = apply_review(new_card(T0), 5, T0).card
    card = apply_review(card, 5, card.due_at).card  # interval 6
    early = apply_review(card, 5, card.due_at - timedelta(days=3))
    assert early.was_due is False and early.card.interval_days == 6 and early.card.due_at == card.due_at


def test_overdue_review_records_missed_review() -> None:
    card = apply_review(new_card(T0), 5, T0).card
    out = apply_review(card, 4, card.due_at + timedelta(days=5))
    assert out.was_due and out.overdue_days == 5 and out.card.missed_reviews == 1


def test_ease_never_drops_below_floor() -> None:
    card = new_card(T0)
    for i in range(10):
        card = apply_review(card, 0, T0 + timedelta(days=i)).card
    assert card.ease == Decimal("1.30")


@pytest.mark.parametrize(
    ("evidence", "quality"),
    [
        (dict(success=True), 5),
        (dict(success=True, hints=1), 4),
        (dict(success=False), 1),
        (dict(verified=False, score=0.9), 4),  # unverified caps at 4
        (dict(verified=False, score=0.5, success=False), 2),
        (dict(dont_know=True), 0),
    ],
)
def test_quality_mapping(evidence, quality) -> None:
    assert quality_for(ev(q=1, session="s", **evidence)) == quality


# ---------------------------------------------------------------- curriculum graph


def test_topological_order_puts_prerequisites_first() -> None:
    order = topological_order({"c": ["b"], "b": ["a"], "a": []})
    assert order == ["a", "b", "c"]


@pytest.mark.parametrize(
    "edges",
    [{"a": ["b"], "b": ["a"]}, {"a": ["c"], "b": ["a"], "c": ["b"]}, {"x": [], "a": ["b"], "b": ["c"], "c": ["a"]}],
    ids=["two-cycle", "three-cycle", "cycle-beside-valid-node"],
)
def test_cycles_are_rejected_with_names(edges) -> None:
    with pytest.raises(CurriculumCycleError, match="a"):
        topological_order(edges)


def _spec(slug: str, prereqs: list[str]) -> dict:
    level = {"objective": "An objective here.", "competency": "A competency here."}
    return {
        "slug": slug, "title": f"Skill {slug}", "category": "Test", "summary": "A summary here.",
        "prerequisites": prereqs, "learning_objectives": ["Learn it."],
        "subskills": [{"slug": "s", "title": "Sub"}],
        "levels": {"beginner": level, "intermediate": level, "advanced": level},
    }


@pytest.mark.parametrize(
    ("skills", "message"),
    [
        ([_spec("a", ["b"]), _spec("b", ["a"])], "cycle"),
        ([_spec("a", ["missing"])], "unknown prerequisites"),
        ([_spec("a", ["a"])], "own prerequisite"),
        ([_spec("a", []), _spec("a", [])], "Duplicate"),
    ],
)
def test_invalid_curricula_are_rejected(skills, message) -> None:
    with pytest.raises(ValueError, match=message):
        Curriculum.model_validate({"version": "2026.1.1", "skills": skills})


def test_shipped_curriculum_is_valid_and_ordered() -> None:
    curriculum, checksum = load_curriculum()
    edges = {s.slug: s.prerequisites for s in curriculum.skills}
    order = topological_order(edges)
    assert len(order) == 13 and len(checksum) == 64
    for skill, prereqs in edges.items():
        assert all(order.index(p) < order.index(skill) for p in prereqs)
    assert {"programming-fundamentals", "http", "sql", "system-design"} <= ancestors(edges, "distributed-systems") | ancestors(edges, "senior-practices")


# ---------------------------------------------------------------- recommendation ranking


def _graph():
    specs = [
        ("fundamentals", [], False),
        ("python", ["fundamentals"], True),
        ("typescript", ["fundamentals"], True),
        ("react", ["typescript"], True),
    ]
    edges = {slug: prereqs for slug, prereqs, _ in specs}
    contexts = [
        SkillContext(
            skill=SimpleNamespace(id=i + 1, slug=slug, title=slug.title(), position=i),
            prerequisites=prereqs, assessable=assessable,
            question_counts={B: 2, I: 2, A: 1} if assessable else {B: 0, I: 0, A: 0},
            verifiable_levels={B, I} if assessable else set(),
            objective_levels={B, I} if assessable else set(),
        )
        for i, (slug, prereqs, assessable) in enumerate(specs)
    ]
    return contexts, edges, {c.skill.slug: c for c in contexts}


def _snap(state, level=None):
    return SimpleNamespace(state=state, demonstrated_level=level, reasons=["Some reason."])


def _card(due, consecutive_lapses=0, last_reviewed=None):
    return SimpleNamespace(due_at=due, interval_days=6, lapses=consecutive_lapses,
                           consecutive_lapses=consecutive_lapses, last_reviewed_at=last_reviewed)


def test_new_learner_starts_with_unlocked_fundamentals_only() -> None:
    contexts, edges, _ = _graph()
    recs = recommend(contexts, edges, {}, {}, [], {}, T0)
    slugs = [r.skill.slug for r in recs]
    assert slugs[:2] == ["python", "typescript"]
    assert "react" not in slugs  # locked behind TypeScript
    assert "fundamentals" not in slugs  # nothing to assess yet
    assert any("doesn't block" in reason for reason in recs[0].reasons)
    assert all(r.reasons for r in recs)
    assert recs[0].activity.type == "assessment" and recs[0].activity.difficulty is B


def test_due_review_outranks_new_material() -> None:
    contexts, edges, by = _graph()
    snaps = {by["python"].skill.id: _snap(MasteryState.DEVELOPING, B)}
    cards = {by["python"].skill.id: _card(T0 - timedelta(days=3))}
    recs = recommend(contexts, edges, snaps, cards, [], {}, T0)
    assert recs[0].kind == "review" and recs[0].skill.slug == "python"
    assert "3 day(s) ago" in recs[0].reasons[0]


def test_reviewed_today_does_not_loop() -> None:
    contexts, edges, by = _graph()
    snaps = {by["python"].skill.id: _snap(MasteryState.DEVELOPING, B)}
    cards = {by["python"].skill.id: _card(T0 - timedelta(hours=1), last_reviewed=T0 - timedelta(hours=2))}
    recs = recommend(contexts, edges, snaps, cards, [], {}, T0)
    assert all(r.kind != "review" for r in recs)


def test_repeated_lapses_switch_to_guided_relearning() -> None:
    contexts, edges, by = _graph()
    snaps = {by["python"].skill.id: _snap(MasteryState.LEARNING)}
    cards = {by["python"].skill.id: _card(T0 - timedelta(days=1), consecutive_lapses=3)}
    rec = recommend(contexts, edges, snaps, cards, [], {}, T0)[0]
    assert rec.kind == "relearn"
    assert rec.activity.type == "interview" and rec.activity.mode is InterviewMode.TUTOR


def test_missing_prerequisite_gap_recommends_the_prerequisite() -> None:
    contexts, edges, by = _graph()
    react = by["react"].skill
    snaps = {react.id: _snap(MasteryState.LEARNING)}
    gap = Gap("missing_prerequisite", react, "TypeScript not yet demonstrated", "d", 2, T0,
              related_skill=by["typescript"].skill)
    recs = recommend(contexts, edges, snaps, {}, [gap], {}, T0)
    assert recs[0].kind == "prerequisite" and recs[0].skill.slug == "typescript"


def test_goal_pulls_its_path_forward() -> None:
    contexts, edges, by = _graph()
    recs = recommend(contexts, edges, {}, {}, [], {by["react"].skill.id: A}, T0)
    assert recs[0].skill.slug == "typescript"
    assert any("goal" in reason for reason in recs[0].reasons)


def test_advancing_is_blocked_by_inconsistency() -> None:
    contexts, edges, by = _graph()
    py = by["python"].skill
    snaps = {py.id: _snap(MasteryState.DEVELOPING, B)}
    gap = Gap("inconsistent", py, "Inconsistent", "d", 4, T0)
    recs = recommend(contexts, edges, snaps, {}, [gap], {}, T0)
    py_recs = [r for r in recs if r.skill.slug == "python"]
    assert py_recs and py_recs[0].kind == "remediate"
