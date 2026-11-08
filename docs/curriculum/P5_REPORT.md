# P5: Subskill lesson completion — first batch

**Date:** 2026-11-08. **Status: validated locally; NOT DEPLOYED. Deployment requires user approval.**

Ten original lessons, about 12,666 words in total, are ready for review. They fill ten previously uncovered subskills without changing the application architecture, UI, question bank, mastery engine, curriculum version or existing prerequisite relationships. Each lesson is `reviewed` (AI-assisted writing plus independent AI critique). **None is human-verified.**

## Audit and prioritization

The production audit used GET requests, file hashes and a read-only PostgreSQL transaction. Production has **15 skills, 45 subskills, 21 prerequisite edges, 158 active questions, zero inactive questions and 15 active lessons**. It has 44 lesson-check links and 49 lesson-resource rows. Deployed curriculum, question files and the 15 lesson files match the repository baseline byte for byte. See [production baseline evidence](validation/p5-production-baseline.json).

Exactly 30 subskills lack a dedicated lesson. All have some assessment coverage; coverage by a broad neighboring lesson is not counted as a dedicated lesson. The complete initial gap set consists of the ten selected subskills below plus the twenty remaining subskills listed later in this report.

Priority is based on prerequisite centrality, transfer to later engineering work and the difference between incidental mention and deliberate instruction. It is a curriculum judgment, **not an inference from learner failure rates**: the production audit found only three recorded answers. The root programming skill supports every other skill; Python, HTTP and SQL feed several later branches; TypeScript's runtime and generic contracts underpin reliable React and API integration.

The first ten highest-priority gaps were:

1. **Core data structures** — choose representations from order, duplicate, lookup and removal requirements before studying algorithms or services.
2. **Complexity** — reason about growing work and memory instead of memorizing container labels; prerequisite for responsible optimization.
3. **Python data model** — nested ownership, equality, hash keys and iterator lifetime are only partly covered by the tracing lesson.
4. **Python functions and scope** — predictable call contracts and callbacks support FastAPI, tests and asynchronous work.
5. **SQL querying and joins** — correct result grain and NULL handling must precede performance and concurrency work.
6. **SQL indexing and plans** — connect a real access pattern to physical work, rather than prescribing indexes without evidence.
7. **TypeScript type-system boundaries** — ingress validation and aliasing prevent a passing build from creating false confidence in external data.
8. **TypeScript generics** — preserve caller information without hiding assertions or weakening contracts with any.
9. **HTTP caching** — separate storage, freshness and validation before application-cache and scaling lessons.
10. **HTTP browser security** — distinguish request delivery, credentials and response access before cookie-authenticated API work.

Git commits and Linux permissions are important next candidates, but their existing broad lessons already teach part of those gaps. The selected batch first completes the five prerequisite-heavy programming, Python, TypeScript, SQL and HTTP skills at the **subskill** level. It does not claim complete instruction at every difficulty level.

### Architecture and mastery findings

- `curriculum.json` remains version **2026.11.2**, with 15 skills and 45 topics. The same-subskill lesson mapping and new lesson prerequisite graph validate without cycles.
- `app/seed/lessons.py` already supports the required objectives, prerequisite lesson links, misconception summaries, resources and question associations. No migration or schema change is needed; Alembic remains at 0009.
- The full seed upserts questions and lessons by slug. It regenerates resource/link surrogate rows, so idempotency is assessed by logical associations plus stable lesson, question and option IDs; learner fingerprints include every stored field.
- The mastery algorithm is **mastery-v1.5**. Lesson reads remain engagement only. They create no mastery evidence. Existing distinct-session, distinct-question, verified-evidence and retention rules remain unchanged.
- Lesson recommendations use the first unread lesson at or below a target difficulty. The existing recommendation test now verifies progression from tracing to data structures, and that the intermediate complexity lesson is not recommended as a beginner lesson.
- A lesson's assessment button selects the skill and difficulty, rather than guaranteeing every listed question is served. Lessons explain how to reach higher-difficulty linked checks. The two existing generics checks do not amount to comprehensive advanced generics assessment coverage.
- Historical narrative in `docs/mastery.md` still contains older coverage counts. Runtime code, current curriculum and the deployed database were used for this audit rather than those historical counts.

## Lessons created

| Lesson | Exact curriculum mapping | Entry level | Existing check links |
| --- | --- | --- | --- |
| [Choosing data structures from the operations you need](../../api/app/seed/lessons/16-choosing-data-structures.md) | programming-fundamentals / data-structures | beginner | 4 |
| [Reasoning about time and space complexity](../../api/app/seed/lessons/17-reasoning-about-complexity.md) | programming-fundamentals / complexity | intermediate | 3 |
| [Python objects: identity, equality, copying and iteration](../../api/app/seed/lessons/18-python-objects-equality-and-copying.md) | python / data-model | beginner | 4 |
| [Python functions: contracts, scope and closures](../../api/app/seed/lessons/19-python-functions-scope-and-closures.md) | python / functions | beginner | 3 |
| [SQL queries: joins, NULL and the grain of a result](../../api/app/seed/lessons/20-sql-querying-joins-and-nulls.md) | sql / querying | beginner | 4 |
| [PostgreSQL indexes: from predicates to execution plans](../../api/app/seed/lessons/21-postgres-indexes-and-query-plans.md) | sql / indexing | intermediate | 5 |
| [TypeScript boundaries: what types prove and what they cannot](../../api/app/seed/lessons/22-typescript-runtime-boundaries.md) | typescript / type-system | beginner | 5 |
| [TypeScript generics that preserve relationships](../../api/app/seed/lessons/23-typescript-generics-that-preserve-relationships.md) | typescript / generics | intermediate | 2 |
| [HTTP caching: storage, freshness and validation](../../api/app/seed/lessons/24-http-caching-and-validation.md) | http / caching | beginner | 4 |
| [Browser security: origins, CORS, cookies and CSRF](../../api/app/seed/lessons/25-browser-origins-cors-and-csrf.md) | http / browser-security | intermediate | 3 |

All ten contain objectives, explicit prerequisite knowledge, basic mental models, advanced extensions, a complete executable example, a practical engineering scenario, common mistakes, production trade-offs, at least one hands-on task with acceptance criteria, three reasoning questions with feedback and authoritative references. Advanced sections build from the entry concepts rather than changing the learner's required starting level.

The UI's existing knowledge-check area provides **37 new associations to unchanged assessments**. Every association is validated against both the question's skill and topic. No new question or option IDs are introduced, and no assessment explanation is copied into a lesson as substitute instruction.

### Duplication review

Each new lesson fills a distinct previously uncovered `(skill, topic)` pair. No duplicate slugs, bodies, or target mappings were found. A body-similarity scan over pairs involving a new lesson found a maximum SequenceMatcher ratio of approximately 0.079; this is an editorial signal, not proof of originality or quality. Manual scope review separates the intentional overlap: tracing follows state; data structures selects representations; Python objects examines nested ownership and protocols; functions examines call boundaries. HTTP caching covers protocol caches, while the existing system-design lesson covers application cache architecture.

## Technical validation

| Check | Result |
| --- | --- |
| Six Python worked examples | Executed on CPython 3.14.7; every stdout line matches the lesson. Examples are written for the documented 3.12-or-later scope. |
| Two TypeScript worked examples | Strict TypeScript 5.9.3, additionally with noUncheckedIndexedAccess; compiled JavaScript executed on Node 26.10.0; exact output matches. |
| Deliberate TypeScript errors | All four expected invalid operations reject when expectation comments are removed. The comments also compile as active expected-error checks. |
| SQL querying example | PostgreSQL 16.15: exact customer summaries, child counts, NULL match and empty equality result verified. |
| SQL indexing example | PostgreSQL 16.15: all three result sets match, including both keyset pages. Both EXPLAIN ANALYZE outputs are retained; plan text and timings are not treated as portable guarantees. |
| Review disagreement probes | Transactional temporary DDL rollback, primary-key grouping, rejection of invalid grouping, expression indexing under case-sensitive C collation, and TypeScript property narrowing all verified. |
| Browser protocol experiments | Headless Chromium 156.0.8078.4: a denied simple POST reaches the server but has an unreadable response; denied preflight prevents the JSON POST; explicit credentialed CORS succeeds; credential mode include with wildcard origin fails. |
| Cookie experiment | Explicit Lax cookie absent on the tested cross-site POST, present on a top-level GET. Local cross-site setup uses localhost versus 127.0.0.1; ports alone are not mislabeled as different sites. |
| Browser cache experiment | Second default fetch uses fresh cached body with no new origin request; forced validation sends the ETag, receives a network 304 and supplies the stored body. |
| Content gate | **0 errors, 30 warnings**; every warning belongs to unchanged existing questions. No new lesson warnings. |
| Resource reachability | **239 / 239 unique question and lesson resource URLs return HTTP 200**, including redirects followed by the existing gate. Two unavailable Starlette URLs were replaced by reachable official starlette.dev pages. |
| Mapping and prerequisites | All ten exact subskill mappings, all 37 same-subskill check links and the complete lesson prerequisite DAG pass. |

Authoritative validation used versioned Python language/library documentation and CPython source for growth/hash behavior; PostgreSQL 16 manuals for NULL, grouping, indexes and plans; the TypeScript Handbook and release notes for erased types and narrowing; RFC 9110/9111 for conditional requests and caching; WHATWG HTML/Fetch for origin and CORS semantics; and OWASP/MDN for CSRF and cookie behavior. Every lesson carries its own resource links. Writing and examples are original, not reproduced documentation prose.

Evidence: [example execution and probes](validation/p5-examples.json), [browser experiments](validation/p5-browser.json), [QA output](validation/p5-qa.json).

### Independent second-model review

**gpt-oss:120b reviewed all ten lessons independently.** The ten retained valid reviews report ready, with 54 advisory findings (2 labeled error, 10 important and 42 suggestion). All findings have documented dispositions in [P5_REVIEW.md](P5_REVIEW.md); the model's labels were not treated as ground truth.

Accepted improvements include staging the heap extension, making first-arrival priority policy explicit, explaining pathological hash costs, naming the shift-count helper as a model, clarifying ON's unknown result, describing unsupported deepcopy behavior, making callback exercise expectations explicit, explaining HTTP example setup, contrasting fresh reuse with validation, and adding must-revalidate and Age. Several proposed changes were rejected after execution or authoritative checks, including incorrect claims about rollback, primary-key grouping, TypeScript narrowing and default-Lax cookie behavior. No confirmed blocker remains, and no human-verification label was applied.

### Backend and frontend checks

- **404 backend tests passed**, in 127.81 seconds, using `forge_p5_tests_20261107`. The suite's destructive migration and truncation fixtures operated only on that new scratch database. There were no skipped tests in this run.
- `npm run lint` and `npm run typecheck` passed.
- **Production webpack build passed** using `npm run build -- --webpack`. There is no separate frontend test script in package.json.
- The default Turbopack build was attempted inside and outside the sandbox and failed when its CSS build worker attempted to bind a local port (`Operation not permitted`). This remains an environment limitation of that build path. No framework/configuration change was made to hide it; the supported webpack build validated the production bundle.
- Python validation tools compile; `git diff --check` passes.

Logs: [backend tests](validation/p5-backend-tests.txt), [successful production build](validation/p5-web-build.txt), [local Turbopack failure](validation/p5-turbopack-failure.txt). The final additive-content check also confirms all **54 pre-existing seed and curriculum files** are byte-identical to the P4 baseline.

## Safe integration rehearsal

The final rehearsal used the new local database `forge_p5_final_20261108`, starting empty. It migrated to 0009, seeded the P4 lesson baseline, then created synthetic history through the API: one learner, three assessment sessions/items/answers/evaluations, three mastery evidence rows, review history and an existing-lesson completion. It then ran the **full current seed twice**.

Both runs produced **15 skills, 45 subskills, 158 active questions, zero inactive questions and 25 active lessons**. There are now 81 lesson-check links and 86 resource rows. Exact same-subskill coverage is 25.

Full-row learner/history fingerprints, including timestamps, are identical before and after both runs. Existing question and option IDs/content, skill/topic IDs, all 21 skill prerequisites, existing lesson IDs and read progress are preserved. Logical lesson contents and associations after the two P5 runs are identical. The loader's existing recreation of association/resource surrogate IDs is accounted for explicitly; those IDs are not used as a false physical-idempotency promise.

See [all three snapshot fingerprints](validation/p5-seed-rehearsal.json). No production seed, migration, restart, backup job or deployment was executed for this batch.

## Expected coverage impact and remaining gaps

| Metric | Production baseline | After approved seed |
| --- | --- | --- |
| Skills / subskills | 15 / 45 | 15 / 45 |
| Active assessment questions | 158 | 158 |
| Dedicated lessons / covered subskills | 15 / 15 | 25 / 25 |
| Dedicated subskill coverage | 33.3% | 55.6% |
| Subskills without a dedicated lesson | 30 | 20 |
| Skills with all three subskills taught by dedicated lessons | 0 | 5 |

This adds **22.2 percentage points** of dedicated subskill coverage and removes one-third of the original gaps. It gives learners an instructional path into several existing assessments; improvement in transfer, retention or mastery still needs learner evaluation and is not asserted as a measured result.

Twenty gaps remain, two per skill:

| Skill | Remaining curriculum subskills |
| --- | --- |
| react | lists; effects |
| fastapi | dependencies; async-handlers |
| testing | test-doubles; reliability |
| security | injection; secrets |
| devops | containers; observability |
| system-design | scaling; reliability |
| distributed-systems | consistency; messaging |
| senior-practices | decision-making; incidents |
| git | commits; history |
| linux | filesystem; shell |

Suggested next batch: Git commits, Linux files/permissions, fixtures/test doubles, reliable suites, FastAPI dependencies/async handlers and React identity/effects, followed by the two dedicated security lessons. Existing broad lessons cover parts of Git/Linux, injection, observability and scaling, but those remain dedicated-lesson gaps.

## Deployment procedure — only after approval

The [batch manifest](validation/p5-manifest.json) records final lesson hashes and expected counts. Before deployment, confirm these are still the reviewed files and capture a fresh production snapshot; this report does not authorize deployment.

1. Run the established `forge-backup.service` job and confirm a **fresh encrypted backup was uploaded successfully**. Do not reuse P4's older backup confirmation.
2. Record current history fingerprints and counts for answers, sessions, evaluations, mastery/review data and lesson progress. Also record question/option IDs, lesson IDs and prerequisite relationships. Concurrent genuine learner activity must be reconciled before accepting a mismatch.
3. Deploy the approved commit. Confirm Alembic is already at 0009; this batch needs no migration. Run the established `python -m app.seed` with the production service's existing environment.
4. Restart through the established service process. No frontend source or design changed. If the established release procedure includes a web build, use its standard production build environment; a failed build is not a reason to modify production configuration ad hoc.
5. Recheck unchanged protected fingerprints; verify **158 active / 0 inactive questions, 25 lessons, 81 checks, 86 resources, 45 topics and 21 prerequisite edges**. Compare all ten API lesson mappings, resources, checks and bodies with the manifest, and verify all ten lesson pages plus `/lessons`, affected track pages and API health return 200.
6. Verify lesson read tracking and assessment launch behavior using the established safe smoke-test process, keeping any intentional test learner activity separate from pre/post preservation checks. Confirm service health and no lesson load errors.

If any preservation or content verification fails, stop the release and investigate before further seeding. Use the established backup/rollback procedure when needed; do not delete learner history or deactivate existing questions to make counts match.

## Reproducing local validation

Run from `api/`, using fresh local `forge_p5_*` databases and the existing virtual environment:

```bash
venv/bin/python -m app.seed.qa --check-urls
venv/bin/python tools/validate_p5.py
venv/bin/python tools/rehearse_p5.py
venv/bin/python -m pytest -q
```

Set `FORGE_P5_DATABASE_URL` for the example/rehearsal tools and a **different** `FORGE_TEST_DATABASE_URL` for pytest. The rehearsal refuses a database with public tables; pytest rebuilds its designated test database. The browser tool accepts `FORGE_PUPPETEER_MODULE` and a Chromium executable argument, so it needs no application dependency or package-lock change. From `web/`, run lint, typecheck and the production build. The default Turbopack limitation and validated webpack alternative are recorded above.
