"""Deterministic mastery and scheduling rules (``mastery-v1.1``).

Pure functions over evidence; no I/O. See docs/mastery.md for the narrative.

Evidence
  * verified   — deterministic grading of objective questions (weight 1.0)
  * unverified — AI interview evaluations that passed validation and were
                 marked mastery-eligible (weight 0.5). Never ground truth.
  * self-report — "I don't know" (counts only against mastery)

A level is *demonstrated* when, at that level:
  1. successes come from >= 2 independent sessions and >= 2 distinct questions,
  2. the most recent 4 attempts are >= 75 % successful, and
  3. if objectively gradable questions exist at that level, >= 1 success is
     verified. Otherwise the level is flagged ``unverified_only``.
Levels must be demonstrated in order (no skipping fundamentals).

States: not_started → insufficient_evidence → learning → developing (beginner)
→ proficient (intermediate) → mastered (advanced, plus retention: advanced
successes on >= 2 distinct days, the latest due review passed, and no
recurring misconception).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.db.enums import Difficulty, EvidenceDimension, EvidenceSource, MasteryState

ALGORITHM_VERSION = "mastery-v1.5"  # v1.5: FORGE Workspace project evidence; v1.4: FORGE OPS evidence
LEVELS = [Difficulty.BEGINNER, Difficulty.INTERMEDIATE, Difficulty.ADVANCED]

VERIFIED_WEIGHT = 1.0
UNVERIFIED_WEIGHT = 0.5
# v1.3: AI-judged system design evaluations and failure analyses join
# interviews as (unverified) reasoning evidence.
REASONING_SOURCES = frozenset({
    EvidenceSource.AI_INTERVIEW, EvidenceSource.DESIGN_EVALUATION, EvidenceSource.FAILURE_SCENARIO,
})
RECENCY_HALF_LIFE_DAYS = 45
AI_SUCCESS_SCORE = 0.7
MIN_SESSIONS = 2
MIN_QUESTIONS = 2
RECENT_WINDOW = 4
RECENT_ACCURACY = 0.75
MIN_EVIDENCE_FOR_LEARNING = 3
MASTERY_DISTINCT_DAYS = 2


@dataclass(frozen=True)
class Evidence:
    id: str
    # Subject: a question id, "c<id>" coding challenge, "d<id>" design challenge, "i<id>" incident scenario,
    # "e<id>" engineering project.
    question_id: int | str
    session_id: str
    difficulty: Difficulty
    source: EvidenceSource
    dimension: EvidenceDimension
    verified: bool
    score: float
    success: bool
    hints_used: int
    said_dont_know: bool
    observed_at: datetime


@dataclass(frozen=True)
class LevelReport:
    level: Difficulty
    attempts: int
    successes: int
    verified_successes: int
    distinct_success_sessions: int
    distinct_success_questions: int
    recent_accuracy: float | None
    verifiable: bool
    demonstrated: bool
    unverified_only: bool
    missing: list[str]


@dataclass
class MasteryResult:
    state: MasteryState
    demonstrated_level: Difficulty | None
    unverified_only: bool
    knowledge_accuracy: Decimal | None
    reasoning_score: Decimal | None
    debugging_score: Decimal | None
    practical_score: Decimal | None
    retention_score: Decimal | None
    uncertainty: Decimal | None
    inconsistent: bool
    evidence_count: int
    verified_count: int
    distinct_questions: int
    distinct_sessions: int
    successful_attempts: int
    last_evidence_at: datetime | None
    last_success_at: datetime | None
    levels: list[LevelReport] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _q(x: float | None) -> Decimal | None:
    if x is None:
        return None
    return Decimal(str(round(x, 6))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def weight(e: Evidence, now: datetime) -> float:
    base = VERIFIED_WEIGHT if e.verified else UNVERIFIED_WEIGHT
    age_days = max(0.0, (now - e.observed_at).total_seconds() / 86400)
    return base * 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def _weighted_mean(items: list[tuple[float, float]]) -> float | None:
    total = sum(w for _, w in items)
    return sum(v * w for v, w in items) / total if total > 0 else None


def _level_report(level: Difficulty, evidence: list[Evidence], verifiable: bool) -> LevelReport:
    at = sorted((e for e in evidence if e.difficulty == level), key=lambda e: (e.observed_at, e.id))
    wins = [e for e in at if e.success]
    recent = at[-RECENT_WINDOW:]
    recent_accuracy = sum(e.success for e in recent) / len(recent) if recent else None
    sessions = {e.session_id for e in wins}
    questions = {e.question_id for e in wins}
    verified_wins = sum(1 for e in wins if e.verified)

    missing: list[str] = []
    if len(sessions) < MIN_SESSIONS:
        missing.append(f"successes in {MIN_SESSIONS} separate sessions ({len(sessions)} so far)")
    if len(questions) < MIN_QUESTIONS:
        missing.append(f"successes on {MIN_QUESTIONS} different questions ({len(questions)} so far)")
    if recent_accuracy is not None and recent_accuracy < RECENT_ACCURACY and wins:
        missing.append(f"recent accuracy of {int(RECENT_ACCURACY * 100)}% (currently {round(recent_accuracy * 100)}%)")
    if verifiable and verified_wins == 0:
        missing.append("at least one objectively graded success")

    demonstrated = bool(wins) and not missing
    return LevelReport(
        level=level,
        attempts=len(at),
        successes=len(wins),
        verified_successes=verified_wins,
        distinct_success_sessions=len(sessions),
        distinct_success_questions=len(questions),
        recent_accuracy=recent_accuracy,
        verifiable=verifiable,
        demonstrated=demonstrated,
        unverified_only=demonstrated and verified_wins == 0,
        missing=missing,
    )


def compute_mastery(
    evidence: Iterable[Evidence],
    *,
    now: datetime,
    verifiable_levels: set[Difficulty],
    due_review_qualities: list[int],
    recurring_misconception: bool,
) -> MasteryResult:
    """``due_review_qualities``: SM-2 qualities of reviews taken when due, oldest first."""
    ev = sorted(evidence, key=lambda e: (e.observed_at, e.id))
    n = len(ev)

    def mean_of(pred, value) -> Decimal | None:
        return _q(_weighted_mean([(value(e), weight(e, now)) for e in ev if pred(e)]))

    knowledge = mean_of(
        lambda e: e.verified and e.dimension is EvidenceDimension.KNOWLEDGE,
        lambda e: 1.0 if e.success else 0.0,
    )
    # Verified practical evidence: hidden tests executed in a verified sandbox.
    practical = mean_of(
        lambda e: e.verified and e.dimension is EvidenceDimension.PRACTICAL, lambda e: e.score
    )
    reasoning = mean_of(
        lambda e: not e.verified and e.dimension is EvidenceDimension.REASONING
        and e.source in REASONING_SOURCES,
        lambda e: e.score,
    )
    debugging = mean_of(
        lambda e: not e.verified and e.dimension is EvidenceDimension.DEBUGGING,
        lambda e: e.score,
    )
    retention = (
        _q(sum(q >= 3 for q in due_review_qualities) / len(due_review_qualities))
        if due_review_qualities
        else None
    )
    effective_n = sum(weight(e, now) for e in ev)
    uncertainty = _q(1 / math.sqrt(1 + effective_n)) if n else None
    last4 = ev[-RECENT_WINDOW:]
    inconsistent = (
        len(last4) == RECENT_WINDOW
        and sum(e.success for e in last4) >= 2
        and sum(not e.success for e in last4) >= 2
    )

    reports = [_level_report(lvl, ev, lvl in verifiable_levels) for lvl in LEVELS]
    demonstrated: Difficulty | None = None
    for r in reports:  # contiguous from beginner: never skip fundamentals
        if not r.demonstrated:
            break
        demonstrated = r.level
    unverified_only = any(r.unverified_only for r in reports if r.demonstrated)

    reasons: list[str] = []
    sessions = {e.session_id for e in ev}
    wins = [e for e in ev if e.success]

    if n == 0:
        state = MasteryState.NOT_STARTED
        reasons.append("No evidence yet.")
    elif demonstrated is None:
        state = (
            MasteryState.INSUFFICIENT_EVIDENCE
            if n < MIN_EVIDENCE_FOR_LEARNING or len(sessions) < MIN_SESSIONS
            else MasteryState.LEARNING
        )
        first = reports[0]
        reasons.append(
            "Beginner level not yet demonstrated: needs " + "; ".join(first.missing or ["a success"]) + "."
        )
    elif demonstrated is Difficulty.BEGINNER:
        state = MasteryState.DEVELOPING
        reasons.append("Beginner level demonstrated.")
    elif demonstrated is Difficulty.INTERMEDIATE:
        state = MasteryState.PROFICIENT
        reasons.append("Intermediate level demonstrated.")
    else:
        adv_days = {e.observed_at.date() for e in wins if e.difficulty is Difficulty.ADVANCED}
        retention_ok = not due_review_qualities or due_review_qualities[-1] >= 3
        blockers = []
        if len(adv_days) < MASTERY_DISTINCT_DAYS:
            blockers.append(f"advanced successes on {MASTERY_DISTINCT_DAYS} different days")
        if not retention_ok:
            blockers.append("passing the latest scheduled review")
        if recurring_misconception:
            blockers.append("resolving a recurring misconception")
        if blockers:
            state = MasteryState.PROFICIENT
            reasons.append("Advanced level demonstrated; mastery still needs " + ", ".join(blockers) + ".")
        else:
            state = MasteryState.MASTERED
            reasons.append("Advanced level demonstrated and retained across days.")
    if unverified_only:
        reasons.append("Part of this rests on AI evaluations without objectively graded evidence.")
    if inconsistent:
        reasons.append("Recent results are inconsistent.")

    return MasteryResult(
        state=state,
        demonstrated_level=demonstrated,
        unverified_only=unverified_only,
        knowledge_accuracy=knowledge,
        reasoning_score=reasoning,
        debugging_score=debugging,
        practical_score=practical,
        retention_score=retention,
        uncertainty=uncertainty,
        inconsistent=inconsistent,
        evidence_count=n,
        verified_count=sum(e.verified for e in ev),
        distinct_questions=len({e.question_id for e in ev}),
        distinct_sessions=len(sessions),
        successful_attempts=len(wins),
        last_evidence_at=ev[-1].observed_at if ev else None,
        last_success_at=wins[-1].observed_at if wins else None,
        levels=reports,
        reasons=reasons,
    )


# ---------------------------------------------------------------- spaced repetition (SM-2)

DUE_TOLERANCE = timedelta(hours=12)


@dataclass(frozen=True)
class CardState:
    repetitions: int
    interval_days: int
    ease: Decimal
    due_at: datetime
    lapses: int
    consecutive_lapses: int
    missed_reviews: int


@dataclass(frozen=True)
class ReviewOutcome:
    card: CardState
    quality: int
    was_due: bool
    overdue_days: int


def new_card(first_seen: datetime) -> CardState:
    # Due immediately, so the first piece of evidence acts as the first review.
    return CardState(0, 1, Decimal("2.50"), first_seen, 0, 0, 0)


def quality_for(e: Evidence) -> int:
    """Maps evidence to an SM-2 quality (0-5). Unverified evidence caps at 4."""
    if e.source is EvidenceSource.SELF_REPORT or e.said_dont_know:
        return 0
    if e.verified:
        if e.success:
            return 5 if e.hints_used == 0 else 4
        # Practical work that passed most hidden tests is a near miss, not a blank.
        return 2 if e.dimension is EvidenceDimension.PRACTICAL and e.score >= 0.5 else 1
    if e.success:
        return 4 if e.hints_used <= 1 else 3
    return 2 if e.score >= 0.4 else 1


def _next_ease(ease: Decimal, q: int) -> Decimal:
    delta = Decimal(str(0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    return max(Decimal("1.30"), (ease + delta).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apply_review(card: CardState, q: int, at: datetime) -> ReviewOutcome:
    """SM-2 with two guards against gaming and loops:

    * practice before the due date never lengthens the interval (no cramming),
      but a failure still counts as a lapse;
    * a failed review is rescheduled for tomorrow, not immediately.
    """
    was_due = at >= card.due_at - DUE_TOLERANCE
    overdue_days = max(0, (at - card.due_at).days) if was_due else 0
    missed = card.missed_reviews + (1 if overdue_days >= 1 else 0)

    if q >= 3 and not was_due:
        return ReviewOutcome(replace(card, missed_reviews=missed), q, False, 0)

    if q >= 3:
        reps = card.repetitions + 1
        interval = 1 if reps == 1 else 6 if reps == 2 else max(1, round(card.interval_days * float(card.ease)))
        return ReviewOutcome(
            CardState(reps, interval, _next_ease(card.ease, q), at + timedelta(days=interval),
                      card.lapses, 0, missed),
            q, was_due, overdue_days,
        )

    lapsed = card.repetitions > 0 or card.consecutive_lapses > 0 or card.lapses > 0
    return ReviewOutcome(
        CardState(0, 1, _next_ease(card.ease, q), at + timedelta(days=1),
                  card.lapses + (1 if lapsed else 0),
                  card.consecutive_lapses + 1, missed),
        q, was_due, overdue_days,
    )
