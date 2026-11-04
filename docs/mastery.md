# Adaptive mastery engine (Milestone 4)

Algorithm version **`mastery-v1.1`**. Code: `api/app/mastery/algorithm.py` (pure
rules), `api/app/mastery/service.py` (database), `api/app/curriculum/graph.py`.

**Changelog.** `v1.1`: a skill's first exposure no longer counts toward
retention (it measured nothing learned). Bumping the version changes every
evidence hash, so existing snapshots recompute on the next sync without
creating duplicate history events.

## Curriculum graph

`api/app/curriculum/curriculum.json` is the source of truth for skills. It is
versioned (`version`, plus a SHA-256 checksum recorded in `curriculum_versions`).
Changing the file without bumping the version is rejected on load.

Each skill has a category, summary, learning objectives, subskills (stored as
`topics`) and, per difficulty level, an objective and a measurable competency
criterion (`skill_levels`). Prerequisites are directed edges
(`skill_prerequisites`). Loading validates that:

- every prerequisite exists, no skill requires itself, and slugs are unique;
- the graph is acyclic (Kahn's algorithm; the error names the skills in the cycle);
- each content file's topics exactly match its skill's subskills.

```
programming-fundamentals ─┬─ python ─────┬─ fastapi
                          │              └─ testing ──┬─ devops
                          ├─ typescript ─┬─ react      │
                          ├─ http ───────┘ (+fastapi, react, security, devops, system-design)
                          └─ sql ─────────┬─ security ─┐
                                          └─ system-design ─┬─ distributed-systems
                                                            └─ senior-practices (+testing, security)
```

13 skills; 8 have questions. Programming Fundamentals, Security, DevOps,
Distributed Systems and Senior Practices have no questions yet. They are
**unassessable**, are shown as such, and never block the skills after them.

## Evidence

Evidence is normalised into `mastery_evidence`, unique per `(source, source_id)`:

| Source | From | Verified | Weight |
| --- | --- | --- | --- |
| `objective_assessment` | graded single-choice answers (M2) | yes | 1.0 |
| `ai_interview` | a completed interview challenge's final evaluation, only if `mastery_eligible` (M3) | no | 0.5 |
| `self_report` | challenge finished with "I don't know" and no evaluation | no | 0.5, counts only against |
| `design_evaluation` | a `mastery_eligible` system design evaluation (M6), on the challenge's primary skill | no | 0.5 |
| `failure_scenario` | a `mastery_eligible` failure-drill evaluation (M6), on the challenge's primary skill | no | 0.5 |
| `incident_simulation` | the deterministic outcome of a resolved FORGE OPS incident (M7), dimension `practical` | **yes** | 1.0 |
| `engineering_task` | a FORGE Workspace project submission executed in a verified sandbox (M9), dimension `practical`; session = workspace | **yes** | 1.0 |
| `incident_review` | a `mastery_eligible` AI review of the incident's root-cause analysis (M7), dimension `debugging` | no | 0.5 |

Design evidence uses the dimension **reasoning**, its subject key is `d<challenge id>`,
and its session is the design project. Senior design challenges count as `advanced`.
Since `mastery-v1.3`, `reasoning_score` averages interview, design and failure-drill
evidence (previously interviews only). Being unverified, design evidence alone can never
verify a level where verified evidence exists.

Since `mastery-v1.4`, FORGE OPS incident outcomes are verified practical evidence
(graded by scenario rules, like objective questions), and active incident
scenarios make their primary skill's level verifiable. Subject key `i<scenario id>`;
the session is the incident attempt. Abandoned attempts produce no evidence.

Ungraded answers, low-confidence evaluations, evaluations without verified
quotes, and suspected prompt injections produce **no** evidence. Weights decay
with a 45-day half-life for averages; level rules use counts, not decayed weights.

A success is a correct objective answer, or an AI score of at least 0.7 with at
most one hint and no "I don't know".

## Mastery rules

A level is **demonstrated** when, at that level:

1. successes come from at least **2 independent sessions** and **2 distinct questions**;
2. the latest 4 attempts are at least **75 %** successful (recent failures withdraw a level);
3. if objectively gradable questions exist at that level, at least one success is
   **verified**. Otherwise the level is marked `unverified_only`.

Levels count only from beginner upwards, with none skipped. States:

| State | Rule |
| --- | --- |
| `not_started` | no evidence |
| `insufficient_evidence` | fewer than 3 items or 1 session, nothing demonstrated |
| `learning` | more evidence, nothing demonstrated |
| `developing` | beginner demonstrated |
| `proficient` | intermediate demonstrated, or advanced without retention |
| `mastered` | advanced demonstrated **and** advanced successes on 2 different days, the latest due review passed, no recurring misconception |

Displayed metrics are null unless evidence of that kind exists:
`knowledge_accuracy` (verified only), `reasoning_score` and `debugging_score`
(AI, unverified), `retention_score` (share of due reviews passed, excluding the first exposure, so it stays null until a real review happens),
`uncertainty` = 1/√(1 + effective evidence weight), and `inconsistent` (last 4
attempts split at least 2 to 2). `practical_score` is always null: verified
practical tests don't exist yet.

**Idempotency.** `sync_learner` holds a per-learner advisory lock. It ingests
with `ON CONFLICT DO NOTHING`, writes one review event per evidence row, and
recomputes a snapshot only when its evidence hash changes. It writes a
`mastery_events` row only on a state or level change, and that row is unique per
hash. Running it repeatedly changes nothing. It runs after every assessment
answer and interview action, and on every mastery read.

## Spaced repetition (SM-2)

One `review_cards` row per learner and skill, created at first evidence. Each
evidence row is a review with SM-2 quality: verified correct 5 (4 with hints),
verified wrong 1, AI success 4 (3 with 2 or more hints), AI partial 2, AI low 1,
"I don't know" 0. The intervals follow SM-2 (1, 6, then interval × ease; the
ease factor never drops below 1.3), plus three guards:

- **No cramming.** Passing before the due date doesn't lengthen the interval.
- **No same-day loop.** A failure is rescheduled for tomorrow, and skills reviewed
  today are left out of today's queue.
- **Bounded queue.** At most 5 reviews a day, most overdue and weakest first.
  After 3 consecutive lapses the review becomes a guided Tutor relearn.

Reviews taken a day or more late count as `missed_reviews`, and
`overdue_days` is recorded for each one.

## Knowledge gaps

Gaps are computed on read, each from at least 2 pieces of evidence:
recurring misconceptions (`misconception_events`, grouped by known misconception),
missing prerequisites behind recent misses, inconsistent performance at a level,
repeatedly missed questions, and concepts that AI evaluations repeatedly found
missing (labelled unverified).

## Recommendations

One activity per skill, ranked by priority. Every recommendation lists its reasons.

| Kind | When | Base priority |
| --- | --- | --- |
| `review` / `relearn` | SM-2 card due (relearn after 3 lapses) | 80 + overdue/weakness/lapses |
| `prerequisite` | recent misses and an undemonstrated assessable prerequisite | 75 |
| `remediate` | other gaps | 70 + occurrences |
| `practice` | insufficient evidence or learning | 55 |
| `advance` | next level, unless gaps show instability | 50 |
| `start` | not started, with prerequisites met; earlier in the graph first | 40 − 0.5 × topological index |

Goals add 20 (the goal skill) or 12 (any skill on its prerequisite path). A
goal whose path is blocked recommends its first startable prerequisite.
Activities prefer objective assessments, which give verified evidence; they
fall back to AI interviews where only written questions exist. Advanced
levels use Grill mode, or Architect for System Design.

## Schema (migration `0003`)

`curriculum_versions`, `skill_prerequisites`, `skill_levels`, `skills.category`,
`skills.learning_objectives`, `mastery_evidence`, `skill_mastery`,
`mastery_events`, `review_cards`, `review_events`, `learner_goals`. Constraints
enforce, among others: no self-loops; only objective evidence may be verified;
the score range; the ease floor; one review event per evidence row; and one
mastery event per evidence hash.

## Testing the full learning flow

```bash
cd api && venv/bin/python -m pytest tests/test_mastery_algorithm.py tests/test_mastery_api.py
```

To test by hand in the app:

1. Open **Learning path**. A new learner sees "Start" recommendations in
   prerequisite order (Python, TypeScript, HTTP, SQL); React and FastAPI are locked.
2. Launch the Python beginner assessment and answer correctly. **Progress**
   shows *Not enough evidence*: one answer never grants a level.
3. Start a second Python beginner assessment. A different question is served;
   answer it correctly. Python becomes **Developing (beginner)**, **Progress
   history** shows both transitions, and the top recommendation becomes
   "Level up: Python intermediate".
4. **Skill graph**: Python is filled in; FastAPI shows *Locked* until HTTP reaches Developing.
5. **Review**: nothing is due today. The first review is due tomorrow (with `curl`
   you can see `review.due_at` in `GET /api/v1/mastery/python`).
6. Answer TypeScript questions wrongly in two sessions. **Gaps** shows
   *Repeatedly missed question*, and the path recommends remediation.


**`mastery-v1.5`**: FORGE Workspace project submissions (`engineering_task`) are verified practical evidence; active projects make their skill and difficulty verifiable. See `docs/workspace.md`.
