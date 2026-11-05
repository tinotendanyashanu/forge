# Content batch P2 and lesson pilot (P3): report

**Date:** 2026-11-05 · **Status:** **deployed** to production at `5b03bc1` on 2026-11-05 (backup `forge-20261105T185417Z.dump.age` confirmed first; migration 0008 → 0009; 75 → 99 active questions, 10 lessons; learner history fingerprint unchanged).

## P2: scored questions for the eight original skills

24 new single-choice questions (11 in batch P2a, 13 in P2b), appended to the existing files without touching existing questions or their positions.

| Skill | Added | Scored per level after P2 (B / I / A) |
| --- | --- | --- |
| python | 1 intermediate, 2 advanced | 2 / 2 / 2 |
| fastapi | 2 advanced | 2 / 2 / 2 |
| typescript | 1 intermediate, 2 advanced | 2 / 2 / 2 |
| react | 1 intermediate, 2 advanced | 2 / 2 / 2 |
| sql | 1 intermediate, 2 advanced | 2 / 2 / 2 |
| http | 1 intermediate, 2 advanced | 2 / 2 / 2 |
| testing | 1 beginner, 1 intermediate, 2 advanced | 2 / 2 / 2 |
| system-design | 1 intermediate, 2 advanced | 2 / 2 / 2 |

All 39 skill-levels are now verifiable through assessments (was 23 after P1, 8 before). Two scored questions per level is the minimum the mastery engine needs to *verify* a level; it is not a claim of comprehensive coverage.

### Validation

| Check | Result |
| --- | --- |
| Claims executed | Python (gather timing, `__eq__` without `__hash__`), TypeScript 5.9 compiler (inferred type predicates, excess property checks, array covariance compile and runtime error), PostgreSQL 16 (`count(*)` with LEFT JOIN, concurrent write skew under REPEATABLE READ committing both, SERIALIZABLE aborting one), availability arithmetic |
| QA gate | 0 errors; 137 question URLs return 200; one guessable-by-length option found in the batch and fixed |
| Blind second-model review | P2a 10/11 agree. The disagreement (`ts-inferred-type-predicate`) gave the pre-TypeScript-5.5 answer; the keyed answer was confirmed by compiling with TypeScript 5.9. P2b 13/13 agree. 0 flagged ambiguous |
| Status | `reviewed` (AI-assisted, AI-reviewed), not human-verified |

## P0 follow-ups in content

With options shuffled per session item, content must never refer to options by letter or position. The QA gate now blocks that (`refers to an option by letter or position`), and the pilot's acceptance criteria quote the correct option's text instead of its letter. One pilot explanation that said "the last call" was rewritten.

## P3: in-app lessons

### What was built
- **Schema** (migration `0009`, additive only): `lessons`, `lesson_resources`, `lesson_questions` (links to existing questions used as knowledge checks) and `lesson_reads` (learner engagement). No existing table is altered. Upgrade, downgrade and re-upgrade tested; `alembic check` reports no drift.
- **Content format:** `api/app/seed/lessons/*.md`, TOML front matter plus Markdown. The loader validates skill and topic against the curriculum, prerequisite lessons (acyclic), check questions, https references and nine required sections, and upserts by slug (removed lessons are deactivated, not deleted). `python -m app.seed` loads lessons after questions.
- **API:** public `GET /api/v1/lessons`, `GET /api/v1/lessons/{slug}`; local-only learner routes `GET /api/v1/lesson-progress`, `POST /api/v1/lessons/{slug}/open`, `POST /api/v1/lessons/{slug}/complete`.
- **Adaptive path:** each recommendation can carry a `lesson` suggestion: the first unread lesson for that skill at or below the recommended level. The recommendation algorithm and the activity itself are unchanged.
- **Web:** `/lessons` (grouped by skill, read state), `/lessons/[slug]` (objectives, prerequisites, body with an "On this page" outline, misconceptions, references, knowledge check that launches a scored assessment, mark as read), a Lessons entry in the navigation, "Learn first" links on the learning path, and a Learn section on each skill page. Every lesson shows an **AI-reviewed** or **Human-verified** badge and its provenance.

### Reading is not mastery
Lesson reads are stored only in `lesson_reads`. A test completes every lesson for a learner and asserts that `mastery_evidence` is unchanged and every skill's evidence count stays 0.

### The 10 pilot lessons

| Lesson | Skill / topic | Level | Checks |
| --- | --- | --- | --- |
| Tracing program state | programming-fundamentals / control-flow | beginner | 3 |
| HTTP requests, methods and status codes | http / semantics | beginner | 2 |
| FastAPI: validation, responses and dependencies | fastapi / request-validation | beginner | 3 |
| PostgreSQL transactions and concurrency | sql / transactions | intermediate | 2 |
| React state and rendering | react / state | beginner | 3 |
| TypeScript unions and narrowing | typescript / narrowing | beginner | 3 |
| Unit tests that matter | testing / test-design | beginner | 3 |
| Authentication, authorisation and injection | security / auth | beginner | 3 |
| Git: commits, branches and safe history | devops / ci-cd | beginner | 2 |
| Linux: processes, files and permissions | devops / containers | beginner | 2 |

Each lesson has all nine sections (why it matters, mental model, how it works, worked example, common mistakes, in production, trade-offs and limits, check your understanding, practice), at least one code example, and 2–4 authoritative references (14 lesson URLs, all returning 200). Code claims were executed: Python examples, the testing lesson's tests under pytest (7 passed), the TypeScript narrowing and exhaustiveness examples with `tsc` 5.9, and the asyncpg API used in the retry example.

### Known limitations
- **Git and Linux are not curriculum skills.** They are filed under DevOps (CI/CD and containers) and linked to the closest existing questions; there are no Git- or Linux-specific assessment questions yet. Adding Level-0 skills is a curriculum change for a later batch.
- Lessons are AI-assisted and AI-reviewed; none is human-verified.
- `/lessons/<unknown>` renders the not-found page with HTTP 200, because `notFound()` runs inside a streamed Suspense boundary. Skill pages behave the same way.
- The UI records completion only when the learner clicks "Mark as read"; the `open` endpoint exists but the UI does not call it during render, to avoid side effects on GET.

## Tests run

| Suite | Result |
| --- | --- |
| API tests | 404 passed (including 7 option-shuffle tests, 8 lesson tests, 3 content-gate tests) |
| Web lint, typecheck, production build | clean; `/lessons` and `/lessons/[slug]` built |
| Migration | 0008 → 0009 → 0008 → 0009 on a scratch database; `alembic check` clean |
| Visual check | `/lessons`, a lesson page (tables, code, outline, knowledge check), mark-as-read and the learning-path suggestion, in Chrome against a local scratch instance |
| Deployment rehearsal | Database built from production commit `e8b9b72` with 12 learner answers; migrate to 0009 and import twice: 75 → 99 active questions, 10 lessons, history fingerprint identical before and after |

## Production readiness

Ready to deploy on approval. The deploy is: backup (confirmed upload), record history fingerprint, check out the new commit, `alembic upgrade head` (adds lesson tables only), `python -m app.seed`, rebuild the web app (new pages), restart both services, and re-check the fingerprint, counts and health.
