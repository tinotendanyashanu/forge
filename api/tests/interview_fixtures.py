"""Deterministic evaluation fixtures.

Each fixture is an interview setup plus a strong answer where sentence *i*
evidences rubric criterion *i*. ``evaluation_json`` builds what a well-behaved
model would return, so tests control grading exactly.
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Fixture:
    area: str
    skill: str
    difficulty: str
    mode: str
    slug: str  # the question the engine is expected to serve first
    sentences: tuple[str, ...]

    @property
    def answer(self) -> str:
        return " ".join(self.sentences)


FIXTURES = [
    Fixture(
        "python", "python", "intermediate", "tutor", "py-shallow-vs-deep-copy",
        (
            "Assignment just binds another name to the same list object, so both names see every change.",
            "A shallow copy like a.copy() makes a new outer list but the inner lists are still shared.",
            "A deep copy with copy.deepcopy recursively copies the nested lists so nothing mutable is shared.",
            "With a = [[1], [2]] and b = a.copy(), a[0].append(9) makes b[0] equal [1, 9] as well.",
            "Deep copies cost more and are pointless when the contents are immutable.",
        ),
    ),
    Fixture(
        "fastapi", "fastapi", "advanced", "architect", "fa-db-session-dependency",
        (
            "Create the async engine once in the lifespan handler and dispose it on shutdown.",
            "Each request gets its own AsyncSession from a yield dependency that always closes it.",
            "The service commits at the end of the unit of work and rolls back on any exception.",
            "Tests override the get_db dependency to point at a separate test database.",
            "Never share an engine or pooled connections across different event loops.",
        ),
    ),
    Fixture(
        "react", "react", "advanced", "tutor", "re-fetch-race-condition",
        (
            "The response for A can resolve after the response for B even though it was sent first.",
            "Use the effect cleanup to ignore results from a stale request.",
            "Set let ignore = false, return a cleanup that sets ignore = true, and only call setUser when ignore is false.",
            "Also handle errors and loading state instead of only the happy path.",
            "TanStack Query keys requests by userId and handles this for you.",
        ),
    ),
    Fixture(
        "postgres-concurrency", "sql", "intermediate", "debug", "sql-lost-update",
        (
            "This is a lost update: both transactions read 100 and each writes its own result.",
            "READ COMMITTED does not tie the earlier SELECT to the later UPDATE.",
            "Do the arithmetic in one statement with SET balance = balance - 30.",
            "Or lock the row first with SELECT ... FOR UPDATE before computing.",
            "Serializable isolation also works but you must retry on serialization failures.",
        ),
    ),
    Fixture(
        "debugging", "react", "intermediate", "debug", "re-object-dependency",
        (
            "React compares dependencies with Object.is, so it checks identity.",
            "The options object literal is recreated on every single render.",
            "Depend on userId and build the options object inside the effect.",
        ),
    ),
    Fixture(
        "system-design", "system-design", "advanced", "architect", "sd-cache-invalidation-race",
        (
            "A slow reader loads the old row, the writer updates and deletes the key, then the reader writes the stale value back.",
            "Delete the key on write instead of updating it, because updates race too.",
            "Keep a short TTL so staleness is bounded even when invalidation is missed.",
            "Use versioned values or leases so an older value cannot overwrite a newer one.",
            "Pages that need read-your-writes can bypass the cache for that user.",
        ),
    ),
]

BY_AREA = {f.area: f for f in FIXTURES}


def evaluation_json(
    n_criteria: int,
    *,
    quotes: list[str | None] | None = None,
    scores: list[int] | None = None,
    complete: bool = True,
    follow_up: str | None = None,
    confidence: float = 0.9,
    misconceptions: list[dict] | None = None,
    feedback: str = "Clear, precise reasoning that covers the key mechanism.",
) -> str:
    scores = scores if scores is not None else [2] * n_criteria
    quotes = quotes if quotes is not None else [None] * n_criteria
    return json.dumps(
        {
            "criteria": [
                {
                    "criterion_id": i + 1,
                    "score": scores[i],
                    "evidence_quote": quotes[i] if scores[i] > 0 else None,
                    "rationale": "Assessed against the rubric.",
                }
                for i in range(n_criteria)
            ],
            "demonstrated_concepts": ["core mechanism"] if any(scores) else [],
            "missing_concepts": [] if complete else ["trade-offs"],
            "misconceptions": misconceptions or [],
            "answer_complete": complete,
            "feedback": feedback,
            "suggested_follow_up": follow_up,
            "confidence": confidence,
        }
    )


def strong(f: Fixture) -> str:
    return evaluation_json(len(f.sentences), quotes=list(f.sentences))
