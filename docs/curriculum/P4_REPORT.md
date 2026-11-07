# Content batch P4: Git and Linux skills, deeper question bank, lessons for every skill

**Date:** 2026-11-07 · **Status:** validated locally; deployment recorded below.

## Summary

| | Before P4 | After P4 |
| --- | --- | --- |
| Curriculum skills | 13 (version 2026.11.1) | 15 (version 2026.11.2) |
| Active questions | 99 | 158 |
| Scored questions per skill-level | 2 | 3, for all 45 skill-levels |
| Lessons | 10 (Git and Linux filed under DevOps) | 15, at least one per skill |

All new content is AI-assisted and AI-reviewed (`status: reviewed`). **None of it is human-verified**; that step needs a person and cannot be done by the authoring pipeline.

## P4a: Git and Linux as curriculum skills

Two Foundations skills, both with `programming-fundamentals` as their prerequisite. They are appended to the curriculum, so existing skills keep their positions, and no existing prerequisite changed, so current learners' recommendations are unaffected.

| Skill | Subskills | Questions |
| --- | --- | --- |
| git | commits, branching, history | 9 scored (3 per level) + 1 advanced free-text |
| linux | processes, filesystem, shell | 9 scored (3 per level) + 1 advanced free-text |

The two existing lessons moved to these skills (`git-version-control` → git/branching, `linux-processes-files-permissions` → linux/processes; version 2), and their knowledge checks now use the new Git and Linux questions. The web track explorer gains a "Git & Linux" group and icons.

## P4b and P4c: a third scored question per level

39 single-choice questions, one per level for each of the 13 existing skills, chosen to cover topics that had no question at that level (for example FastAPI dependency overrides, PostgreSQL expression indexes, CORS with credentials, SSRF, consistent hashing, Kafka per-partition ordering, ADRs).

## P4d: five new lessons

| Lesson | Skill / topic | Level | Checks |
| --- | --- | --- | --- |
| Python concurrency: asyncio, threads and processes | python / concurrency | intermediate | 3 |
| Caching and scaling reads | system-design / caching | beginner | 3 |
| Timeouts, retries and idempotency | distributed-systems / partial-failure | intermediate | 3 |
| Shipping safely: pipelines, rollouts and observability | devops / ci-cd | intermediate | 4 |
| Code review that finds risk | senior-practices / code-review | beginner | 3 |

## Validation

| Check | Result |
| --- | --- |
| Claims executed | Git 2.x in a scratch repository (staging snapshot, fast-forward, tracked file ignored, reflog recovery, rebase changes all hashes); Bash (750 mode, `>` truncation, pipeline status with and without `pipefail`, exit 137/143, unset-variable expansion shown with `echo` only); Python (sort returns None, generator exhaustion, 9 calls for `fib(4)`, 10/11 keys move under modulo hashing, plain mock vs `autospec`); TypeScript 5.9 (generic inference, `as const` union, `never` exhaustiveness error); FastAPI (422 for a missing query parameter, `patch` vs `dependency_overrides`, AnyIO limiter = 40 tokens); PostgreSQL 16 (GROUP BY error, sequential scan for a 60%-selective predicate, expression index used only after creation, lost update reproduced at 70 vs 40) |
| Lesson code | Every Python example in the new lessons runs with the documented output; the pipeline YAML parses; the canary queries are illustrative |
| QA gate | 0 errors; 208 question URLs and all lesson URLs return 200; nine new guessable-by-length options rebalanced; one inaccessible reference (ACM, 403) replaced |
| Blind second-model review (gpt-oss:120b) | 57/57 single-choice agree, 0 flagged ambiguous; 2/2 free-text reference answers judged correct. Two wording issues it raised were fixed (`git-hash-chain` prompt, `re-fetch-race` option). One objection was rejected after testing: it claimed FastAPI's thread pool default is 5 × CPUs; the AnyIO limiter was measured at 40 tokens |
| Existing content | All 99 existing questions are byte-identical and in their original positions |
| Tests | 404 passed (four assertions updated for 15 skills, curriculum version 2026.11.2 and three Python beginner questions) |
| Web | lint, typecheck and production build clean |
| Idempotency | Local database migrated to 0009 and seeded twice: 158 questions, 15 lessons, 15 skills, learner-history fingerprint unchanged |

### Issue found during authoring

A new question initially reused the slug `sql-lost-update`, which belongs to an existing free-text question; the batch writer upserts by slug, so it would have replaced it. This was caught before commit by diffing against the previous commit. The original was restored and the new question was replaced by a different topic (`sql-expression-index`). `CONTENT_WORKFLOW.md` now requires checking new slugs against the existing bank.

## Known limitations

- No content is human-verified.
- Three scored questions per level is still a small bank; repeated assessments will reuse questions.
- Several pre-existing questions still carry QA warnings (length tells, near-duplicates); they are tracked, not changed, because learners have answered them.
