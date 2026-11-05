# Content batch P1 (pilot): report

**Date:** 2026-11-05 · **Status:** validated locally, **not yet imported into production**.

## What was produced

35 new assessment questions for the five curriculum skills that had none. Each skill gets 2 scored single-choice questions at every level plus one advanced free-text question, so all 15 of these skill-levels become verifiable under `mastery-v1.5`.

| Skill | Beginner | Intermediate | Advanced (scored + free-text) | Topics covered |
| --- | --- | --- | --- | --- |
| programming-fundamentals | 2 | 2 | 2 + 1 | control-flow, data-structures, complexity |
| security | 2 | 2 | 2 + 1 | auth, injection, secrets |
| devops | 2 | 2 | 2 + 1 | ci-cd, containers, observability |
| distributed-systems | 2 | 2 | 2 + 1 | consistency, messaging, partial-failure |
| senior-practices | 2 | 2 | 2 + 1 | code-review, decision-making, incidents |

Question styles: code tracing (3 executed-output questions), diagnosis of a described failure, scenario-based judgement, code review of a snippet or pull request, and free-text design, threat-model and incident-leadership tasks. Senior and advanced items test judgement and trade-offs rather than definitions. Every question has a hint, a rubric of 3–5 criteria, expected concepts, misconceptions and 1–3 authoritative references. QA metadata (`api/app/seed/meta/`) adds the learning objective, prerequisites, a rationale for every distractor, follow-up questions, version, status and provenance.

**Provenance:** AI-assisted draft (Claude), self-reviewed, then blind-reviewed by a second model. **No human subject-matter review has taken place**, so the status is `reviewed`, not `verified`.

## Validation performed

| Check | Result |
| --- | --- |
| Seed schema and loader rules | Pass, 13 files, 75 questions |
| Code-output questions executed | 3/3 stated outputs match; the quadratic `list.pop(0)` claim was also timed (5× slower at 2× n, `deque` flat) |
| QA gate (`python -m app.seed.qa --check-urls`) | 0 errors; all 107 resource URLs return 200 (one 404 found and replaced during authoring) |
| Guessability by length | 3 pilot questions flagged and fixed; 0 remaining |
| Correct-answer position (pilot) | a 4, b 10, c 11, d 5 |
| Near-duplicates | 1 pilot pair flagged (`pf-alias-vs-copy` / `py-equality-vs-identity`, 0.64): false positive caused by shared "What does this program print?" boilerplate |
| Blind second-model review, single-choice | First pass 29/30 agreement; the disagreement exposed an ambiguous prompt (`devops-canary-criteria`), which was reworded. Second pass **30/30 agreement, 0 flagged ambiguous** |
| Blind review, free-text references | Four accurate corrections adopted: synchronous replication needs `remote_apply` for read-your-writes; indexed heaps can update keys; reset-token entropy; offset commit after the database transaction. Remaining "omissions" were extra topics, not errors |
| API test suite | **389 passed** (2 existing assertions updated because DevOps is now assessable and the recommender now prefers objective questions for programming fundamentals) |
| Import rehearsal | Scratch database seeded from the production commit, 12 learner answers created through the API, then the new content imported twice: active questions 40 → 75, 0 deactivated, and the fingerprint of answers, sessions, mastery evidence and evaluations was **identical before and after both imports**. Re-import left every question row unchanged |

## Not done in this batch

- **Lessons.** FORGE has no lesson model or UI. Adding one is a product change; see the decision below.
- **The second scored intermediate question and two scored advanced questions** for each of the 8 original skills (16 skill-levels still unverifiable).
- **Coding, design, incident and project expansion.** These need executable verification, and the coding sandbox is disabled in production, so new executable exercises cannot be verified there.
- **Production import.** Waiting for approval.

## Coverage after the pilot (assessments only)

| Measure | Before | After P1 |
| --- | --- | --- |
| Skills with assessment questions | 8 / 13 | 13 / 13 |
| Scored questions | 24 | 54 |
| Skill-levels verifiable through assessments | 8 / 39 (21%) | 23 / 39 (59%) |
| Requested Level 0–5 topics with at least one assessment | 12 / 88 (14%) | about 30 / 88 (34%), judgement-based |

## Cost of further expansion

AI-assisted authoring and the blind review run inside the existing Ollama Cloud subscription: about one review call per question, so roughly 40 calls per batch at the current hourly cap of 120. No Azure cost changes. The real constraint is review time: the honest bottleneck for `verified` status is human subject-matter review.
