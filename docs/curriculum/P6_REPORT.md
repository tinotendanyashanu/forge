# P6: React, FastAPI, testing, security and engineering foundations

Date: 2026-11-08. **Validated locally; NOT DEPLOYED. Separate user approval is required for P6 deployment.**

P5 was successfully deployed at **`f26daf2`** after a fresh uploaded encrypted backup, with 158 active questions, 25 lessons, 45 subskills, unchanged prerequisite relationships and matching learner-history fingerprints. All ten new pages and their 37 assessment associations were verified. Production remains private/local-only with the coding sandbox disabled. See [P5 deployment result](P5_DEPLOYMENT.md) and [preservation evidence](validation/p5-deployment.json).

P6 adds **ten original lessons, 11,968 words**, filling the next ten existing curriculum subskills. The batch follows the requested priority order: React lists/effects, FastAPI dependencies/async handlers, testing doubles/reliability, security injection/secrets, then Git commits and Linux filesystems. It introduces no new skill, question, prerequisite edge in the curriculum graph, application feature, UI change or mastery rule.

All ten are `reviewed`: AI-assisted writing, independent advisory critique and technical validation. **None is human-verified.** No P6 seed, restart, checkout or configuration change was performed on production.

## Lessons and exact mappings

| Lesson | Curriculum skill / subskill | Entry level | Existing assessment links |
| --- | --- | --- | --- |
| [React lists: identity, local state and derived data](../../api/app/seed/lessons/26-react-list-identity-and-derived-data.md) | react / lists | beginner | 2 |
| [React effects: synchronization, cleanup and stale results](../../api/app/seed/lessons/27-react-effects-and-request-lifetimes.md) | react / effects | intermediate | 4 |
| [FastAPI dependencies: composition, lifetime and test overrides](../../api/app/seed/lessons/28-fastapi-dependency-lifetimes-and-overrides.md) | fastapi / dependencies | intermediate | 3 |
| [FastAPI async handlers: event-loop safety and bounded work](../../api/app/seed/lessons/29-fastapi-async-handlers-and-bounded-work.md) | fastapi / async-handlers | intermediate | 3 |
| [Test doubles: fixtures, contracts and patching the right name](../../api/app/seed/lessons/30-test-doubles-fixtures-and-patching.md) | testing / test-doubles | intermediate | 4 |
| [Reliable tests: time, shared state and execution order](../../api/app/seed/lessons/31-reliable-tests-time-state-and-order.md) | testing / reliability | beginner | 3 |
| [Injection defenses: keeping data out of interpreter control](../../api/app/seed/lessons/32-injection-safe-data-boundaries.md) | security / injection | beginner | 3 |
| [Secrets: storage, rotation and exposure response](../../api/app/seed/lessons/33-secrets-storage-rotation-and-exposure.md) | security / secrets | intermediate | 3 |
| [Git commits: the index, snapshots and object identity](../../api/app/seed/lessons/34-git-commits-index-and-object-identity.md) | git / commits | beginner | 3 |
| [Linux filesystems: paths, permissions and open-file lifetime](../../api/app/seed/lessons/35-linux-filesystem-paths-and-permissions.md) | linux / filesystem | beginner | 3 |

Each lesson has explicit objectives and prerequisite knowledge, a basic mental model, a complete worked example, practical engineering context, common misconceptions, production considerations and trade-offs, three reasoning questions with feedback, an exercise with acceptance criteria and authoritative resources. Advanced extensions build on the stated entry level; they are not presented as knowledge a beginner must already possess.

There are **31 new associations to existing assessments** and **37 lesson-resource associations**. Every check resolves to an active seed question under the exact same skill and subskill. Existing assessment IDs, options and contents are unchanged. The existing assessment launcher selects skill and difficulty; it does not guarantee that every listed check appears in one session. Some subskills, including React lists and testing reliability, still lack their own advanced bank item; these lessons do not claim to solve that assessment-depth gap.

## Technical validation

All **12 fenced executable blocks across the ten lessons** were exercised. Three blocks form the test-doubles example's separate modules/tests, so they are validated together rather than incorrectly executed as independent scripts.

| Area | Execution and outcome |
| --- | --- |
| React lists | Actual React/ReactDOM 19.3.0 in headless Chromium: stable keys retain the correct draft after reordering; the index-key comparison reproduces the wrong-row draft; filtering unmounts a row and resets its local draft on return. |
| React effects | Original timer/mock paths cover success, failure and empty input. Controlled promises verify fast-before-slow completion, obsolete-result suppression and cleanup on unmount. Development StrictMode produces two setups with one permitted publication. No browser page errors. |
| FastAPI dependencies | Exact stdout confirms per-request sharing, registered-callable override, restoration of prior overrides, cleanup on normal completion and a 409 exception path. |
| FastAPI async | An event gate proves two requests are in flight without elapsed-time guesses; the sync route runs off the live loop thread; measured AnyIO limiter is 40 tokens. |
| Test doubles | Four pytest cases pass, including safe wrong-namespace demonstration and autospec rejection of an invented argument. |
| Test reliability | Five pytest cases pass, including exact expiry equality and fresh state. Both pytest labs pass in normal order, reverse order, and another hash-seed/timezone environment: **9 unique cases, 27 case executions**. |
| Injection | In-memory SQLite verifies tenant-scoped value parameters, literal treatment of SQL-shaped input and rejection of an unapproved sort fragment. HTML text encoding matches the stated output. No network or real credentials. |
| Secrets | Exact output confirms repr redaction, explicit public-field export, ordinary serialization's secret-field inclusion, safe missing-setting error and decoded 32-byte token representation. No generated token value is logged. |
| Git | Git 2.55.0 in a disposable repository verifies the index snapshot, unchanged tracked status after an ignore rule, blob/tree/commit types and distinct commit identity with the same tree. No remote or global settings changed. |
| Linux | Unprivileged Linux UID/GID 65534 verifies mode 640, name enumeration without search, denial of leaf lookup without search, known-name reads without enumeration, and a readable open handle after unlink. |

The security and Linux examples run in an existing local Python 3.12 image without host mounts, network, capabilities or a writable root filesystem. The environment is an explicit minimal allowlist. Limits: 128 MiB memory, 0.5 CPU, 32 processes, 16 MiB scratch tmpfs, 1 MiB file-size limit and a 20-second in-container timeout. This content-validation setup does **not** enable FORGE's coding sandbox.

The API examples ran on CPython 3.14.7 with FastAPI 0.162.0, Starlette 1.10.0, AnyIO 4.16.0 and httpx 0.28.1. Pytest is 9.2.0. React examples ran on Chrome 156.0.8078.4. Version-sensitive statements are scoped to the tested behavior and linked documentation, rather than adopting the advisory model's obsolete version assumptions.

Evidence: [non-browser execution](validation/p6-examples.json), [React browser scenarios](validation/p6-browser.json).

## Content gate and resource validation

The existing gate passes with **0 errors and 30 warnings**. Its warning list is identical to P5's unchanged assessment-bank warnings; no P6 lesson warning was introduced. All **253 distinct question/lesson resource URLs return 200** in the final complete pass.

One intermediate pass saw a 503 from an unchanged Ubuntu tutorial. The resource subsequently returned 200, and the entire gate was rerun successfully. No source was changed to hide the transient failure and no gate exception was added. See [complete QA result](validation/p6-qa.json).

Technical sources include the current React and FastAPI documentation, Starlette's documented limiter, versioned Python language/library references, pytest's official fixture/flakiness guides, OWASP injection/secrets/password/logging guidance, Git's official book/manuals and Linux man-pages. The lesson text, scenarios and examples are original educational writing rather than copied tutorial prose.

## Independent advisory review

**gpt-oss:120b independently reviewed all ten drafts.** Ten valid reviews report ready, with 56 advisory findings: 4 error, 13 important and 39 suggestion. One malformed response was discarded and retried. Every retained finding has an individual resolution in [p6-review.json](validation/p6-review.json), with the consequential disagreements and accepted refinements explained in [P6_REVIEW.md](P6_REVIEW.md).

Useful changes include preserving pre-existing dependency overrides, simplifying unnecessary prerequisites, improving exercise contracts, making placeholder and hash-seed behavior explicit, and adding a safe configuration export. Several confidently stated review errors were rejected using actual execution or primary documentation: React 19.3 exists, FastAPI exposes dependency scopes, directory names can be enumerated without search permission, and live thread identifiers cannot be recycled from a thread that is still running.

The draft hashes record what the model saw; the final manifest records the refined files. Changed executable examples were rerun after refinement. No model response was treated as human verification or accepted merely because it was labeled error.

## Integration, preservation and test results

**404 backend tests passed in 123.74 seconds**, using only the fresh local `forge_p6_tests_20261108` database. No tests were skipped. Existing lesson-read tests cover the 35-lesson bank and continue to establish that reading creates no mastery evidence.

Frontend lint, TypeScript checking and the **production webpack build passed**. No frontend source, package manifest or lockfile changed for P6. The supported webpack path is used because the local default Turbopack build's port restriction was already established during P5; this batch does not alter build configuration or production runtime to work around it. There is no separate frontend test script in package.json.

The final source guard confirms **65 pre-existing files** are byte-identical to the P5 release: the prior seed/curriculum files and mastery algorithm. All 25 previous lessons are retained. The complete lesson prerequisite graph is acyclic; all ten new `(skill, topic)` pairs were previously uncovered and are unique. There are no identical lesson bodies. A comparison involving new bodies had a maximum SequenceMatcher ratio of approximately 0.111; this is only a screening signal. Manual scope review confirms that the new dedicated lessons deepen the existing broad introductions rather than replacing them.

The scratch rehearsal began with an empty `forge_p6_scratch_20261108` database, migrated to 0009, loaded P5's **25-lesson** baseline and created synthetic assessment, mastery/review and lesson-read history through the API. It then ran the full P6 seed **twice**.

Both runs produced 158 active questions, zero inactive questions, 35 lessons, 35 covered subskills, 112 lesson-check links and 123 resources. Fingerprints across all **60 tables in the FK closure from learners** remained identical, including all stored history timestamps. Protected question/option IDs and semantic contents, skill/topic IDs and prerequisite relationships were unchanged; existing lesson IDs and progress survived. Logical content and associations matched across both seed runs. The existing loader regenerates association/resource surrogate IDs; this is explicitly not described as physical row-ID idempotency for those rows.

Evidence: [backend log](validation/p6-backend-tests.txt), [production build](validation/p6-web-build.txt), [all seed snapshots](validation/p6-seed-rehearsal.json). The Python validation tools compile and `git diff --check` passes.

## Expected coverage after a separately approved P6 release

| Metric | Production now, after P5 | Proposed P6 |
| --- | --- | --- |
| Skills / subskills / curriculum prerequisite edges | 15 / 45 / 21 | unchanged |
| Active / inactive questions | 158 / 0 | unchanged |
| Lessons / dedicated subskills | 25 / 25 | 35 / 35 |
| Dedicated subskill coverage | 55.6% | 77.8% |
| Dedicated lesson gaps | 20 | 10 |
| Skills with all three subskills covered by dedicated lessons | 5 | 9 |

The proposed gain is **22.2 percentage points**, halving P5's remaining dedicated lesson gaps. It completes dedicated subskill instruction for React, FastAPI, testing and security, and fills one foundational gap each in Git and Linux. This metric counts instruction mapped to subskills; it does not claim complete advanced-level instruction, human verification or measured learning-outcome improvement.

The ten gaps remaining after P6 would be:

| Skill | Still without a dedicated lesson |
| --- | --- |
| devops | containers; observability |
| system-design | scaling; reliability |
| distributed-systems | consistency; messaging |
| senior-practices | decision-making; incidents |
| git | history |
| linux | shell |

## Release boundary and reproduction

The [P6 manifest](validation/p6-manifest.json) freezes all ten final lesson hashes, prerequisite/check mappings and expected counts. **P6 is not deployed.** A later approved release must verify that manifest, take a fresh uploaded encrypted backup, capture current preservation fingerprints, seed/restart through the established process and verify the ten new pages and assessment mappings. The P5 backup and fingerprints are historical evidence, not substitutes for that future release's fresh checks.

Run content validation from `api/` with the existing virtual environment:

```bash
venv/bin/python -m app.seed.qa --check-urls
venv/bin/python tools/validate_p6.py
venv/bin/python tools/rehearse_p6.py
venv/bin/python -m pytest -q
```

Use a fresh local `forge_p6_*` database in `FORGE_P6_DATABASE_URL` for rehearsal; the tool refuses existing public tables. Set a separate `FORGE_TEST_DATABASE_URL` for pytest, whose fixtures rebuild that designated test database. The browser verifier takes `FORGE_PUPPETEER_MODULE` and a Chromium executable and reads the installed React modules; no app dependency installation is required. From `web/`, run lint, typecheck and the supported production build.
