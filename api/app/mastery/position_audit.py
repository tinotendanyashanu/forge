"""Read-only audit of answer-position patterns in historical single-choice answers.

Before per-item option shuffling, options were shown in authored key order and
75% of correct options were authored as ``b``. A learner who mostly picked
``b`` could have earned verified mastery without understanding. This command
reports, per learner, how often each authored key was chosen and how much of
their verified evidence could be explained by position alone. It never
modifies or deletes evidence; review the output and decide manually.

Run from ``api/``::

    venv/bin/python -m app.mastery.position_audit
"""

import asyncio
import os
import sys

import asyncpg

# A learner is flagged if at least MIN_ANSWERS scored answers exist and one
# authored key accounts for at least SHARE_THRESHOLD of their choices.
MIN_ANSWERS = 6
SHARE_THRESHOLD = 0.7

QUERY = """
select a.learner_id::text as learner,
       o.key as authored_key,
       e.is_correct as correct,
       a.submitted_at
from answers a
join question_options o on o.id = a.selected_option_id
join evaluation_results e on e.answer_id = a.id
where a.selected_option_id is not null
"""


async def run(url: str) -> int:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(QUERY)
        evidence = {
            r["learner"]: r["n"]
            for r in await conn.fetch(
                "select learner_id::text as learner, count(*) as n from mastery_evidence "
                "where source = 'objective_assessment' group by learner_id"
            )
        }
    finally:
        await conn.close()

    by_learner: dict[str, list] = {}
    for r in rows:
        by_learner.setdefault(r["learner"], []).append(r)

    flagged = 0
    print(f"learners with scored answers: {len(by_learner)}")
    for learner, answers in sorted(by_learner.items()):
        keys: dict[str, int] = {}
        for a in answers:
            keys[a["authored_key"]] = keys.get(a["authored_key"], 0) + 1
        top_key, top_n = max(keys.items(), key=lambda kv: kv[1])
        share = top_n / len(answers)
        correct = sum(1 for a in answers if a["correct"])
        flag = len(answers) >= MIN_ANSWERS and share >= SHARE_THRESHOLD
        flagged += flag
        print(
            f"{'FLAG ' if flag else 'ok   '}learner {learner[:8]}…  answers={len(answers)} "
            f"correct={correct} authored-key share={dict(sorted(keys.items()))} "
            f"top={top_key}:{share:.0%} objective-evidence={evidence.get(learner, 0)}"
        )
    print(f"flagged: {flagged} (threshold: >= {MIN_ANSWERS} answers and >= {SHARE_THRESHOLD:.0%} on one key)")
    print("No evidence was changed.")
    return 0


def main() -> int:
    url = os.environ.get("FORGE_DATABASE_URL")
    if not url:
        print("FORGE_DATABASE_URL is not set", file=sys.stderr)
        return 2
    return asyncio.run(run(url))


if __name__ == "__main__":
    sys.exit(main())
