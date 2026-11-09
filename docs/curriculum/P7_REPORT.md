# P7: dedicated lessons for the last ten subskills

Date: 2026-11-09 (initial validation: 2026-11-08). **Deployed and verified** at `2e080e2468d9bc7cab15a969939709828537517d` after explicit user approval. See [P7 deployment result](P7_DEPLOYMENT.md). **None of the ten lessons is human-verified.** The validation sections below retain the preparation evidence.

P6 was the pre-release baseline at **`25c4b6f`**, with 158 active questions, 35 lessons, 45 subskills, 112 lesson-check links, 123 resources, and unchanged learner history. See [P6 deployment result](P6_DEPLOYMENT.md). The approved P7 release advanced that checkout to `2e080e2`; P6 was not redeployed.

The earlier November 9 [P6 recheck](validation/p6-recheck-20261109.json) confirmed the baseline without repeating its deployment. A separate fresh backup preceded P7. Production now has 45 lessons, 147 lesson-check associations and 157 resource associations, with unchanged question IDs, prerequisite edges and learner/mastery history. See [complete P7 release evidence](validation/p7-deployment.json).

P7 adds **ten original lessons, 18,261 words**, one for each subskill that still lacked a dedicated lesson. It introduces no new skill, question, curriculum prerequisite edge, application feature, UI change, or mastery rule.

All ten are `reviewed`: AI-assisted writing, independent advisory critique, and technical validation. **None is human-verified.**

The [November 9 validation summary](validation/p7-validation-recheck.json) ties the final manifest to the fresh example, QA, backend, frontend and import results. The earlier November 8 evidence remains available as the initial validation record.

## Lessons and exact mappings

| Lesson | Curriculum skill / subskill | Entry level | Existing assessment links |
| --- | --- | --- | --- |
| [Containers: image layers, writable state and process signals](../../api/app/seed/lessons/36-container-image-layers-and-signals.md) | devops / containers | beginner | 3 |
| [Observability: latency tails, traces and label cardinality](../../api/app/seed/lessons/37-observability-tails-traces-and-cardinality.md) | devops / observability | intermediate | 3 |
| [Scaling: stateless capacity, replicas and hot partitions](../../api/app/seed/lessons/38-scaling-capacity-replicas-and-hotspots.md) | system-design / scaling | intermediate | 5 |
| [Reliability: jitter, queues and availability math](../../api/app/seed/lessons/39-reliability-jitter-queues-and-availability.md) | system-design / reliability | intermediate | 3 |
| [Consistency: replica lag and conflict resolution](../../api/app/seed/lessons/40-consistency-replica-lag-and-conflicts.md) | distributed-systems / consistency | intermediate | 3 |
| [Messaging: delivery, outbox and partition order](../../api/app/seed/lessons/41-messaging-delivery-outbox-and-order.md) | distributed-systems / messaging | intermediate | 4 |
| [Technical decisions: records, reversibility and replacement](../../api/app/seed/lessons/42-technical-decisions-records-and-reversibility.md) | senior-practices / decision-making | intermediate | 4 |
| [Incidents: mitigation, roles and follow-up](../../api/app/seed/lessons/43-incident-response-mitigation-and-follow-up.md) | senior-practices / incidents | intermediate | 3 |
| [Git history: amend, revert and local recovery](../../api/app/seed/lessons/44-git-history-amend-revert-and-recovery.md) | git / history | intermediate | 4 |
| [Shell: redirection, pipeline status and expansion](../../api/app/seed/lessons/45-linux-shell-redirection-pipelines-and-expansion.md) | linux / shell | intermediate | 3 |

Each lesson has objectives, prerequisite lesson slugs, a mental model, a worked example, common mistakes, production use, trade-offs, three reasoning questions with feedback, and an exercise with acceptance criteria. Resources point at Docker, Prometheus, OpenTelemetry, Azure architecture patterns, the Amazon Builders' Library, the Google SRE book, Jepsen, PostgreSQL hot standby, Kafka, the transactional outbox description, AWS SQS standard queues, ADR guidance, the Git manual, the Bash manual, and GNU coreutils.

There are **35 new associations to existing assessments** and **34 new lesson-resource associations**. Every new check resolves to an active question under the same skill and subskill. Existing question and option IDs are unchanged. The same question may already be linked from an older lesson. Lesson 14 still links the observability percentile question, and lesson 10 still links the truncation question. Those older links stay.

The assessment launcher selects a skill and a difficulty. It does not promise that every linked check appears in one session. Four of the linked checks are free-text. Containers has no advanced question, reliability has no beginner question, and incidents has no beginner question. P7 does not add questions to close those bank gaps.

## Technical validation

Every fenced example was executed after the final wording edits. Each lesson has one executable fence and one text fence. The text fence matches stdout.

| Area | Execution and outcome |
| --- | --- |
| Containers | Docker 29.8.1, local `python:3.12-slim` (`sha256:02108f5d322d…`). Dependency layer cached, source layer rebuilt, the same container kept `photo`, a new container did not, exec-form PID 1 was `python` and exited after SIGTERM, shell-form PID 1 was `/bin/sh` and was still running 0.8 seconds later with the handler absent. Builds use `--pull=false`. Runs use `--pull=never`. |
| Observability | CPython 3.14.7. 100 requests, average 128.4 ms, nearest-rank p99 2400, user-label series 12,000,000, route and status series 60. |
| Scaling | Same interpreter. 10 million links in a 30-day month is 3.86 writes/s. A 100x read ratio is 385.8 reads/s. Five years at 500 bytes is 300.0 GB before indexes and copies. Modulo moves fraction 0.908 of 20,000 keys from 10 nodes to 11. A 100-vnode ring moves 0.094, beside 1/11 = 0.091. |
| Reliability | `random.Random(7)` delays print 0.82, 1.3, and 4.6 against base 1, 2, 4. Parallel B is 0.999999. The series path with A is 0.998999. These floats belong to this interpreter. |
| Consistency | The in-memory replica still shows Ada after the primary changes to Amina, then shows Amina after the copy. Last-write-wins keeps `dark` at clock 100 over `light` at clock 90. No database connection. |
| Messaging | First apply leaves balance 25. The redelivery leaves 25. The dual write that crashes before publish leaves `published` empty. The outbox commit stores `order-2`. The set is explicitly not durable. |
| Decisions | A record with only a decision reports gaps for context, alternatives, and consequences. A complete record reports none. The public-API flag prints false and the logging-library flag prints true. Those flags are constants. |
| Incidents | Inputs 0.08, 0.001, and 10 print `roll back the deployment`. The reminder sentence prints `not-a-system-fix`. The delayed column drop prints `system-fix`. The helper is not a deploy controller. |
| Git | Git 2.55.0 in a disposable repository. Amend keeps the tree, creates a new commit, and leaves the old tip as a commit object. Revert leaves three commits and restores the file text `one`. Reset drops to two commits. The reflog reset restores three and the subject `Revert bad line`. No remote and no push. |
| Shell | Bash 3.2.57, executed as a file. Truncation leaves one line, append keeps both, a plain pipeline reports 0, `pipefail` reports 1, the unset expansion prints `rm -rf /*`, both guards report 1, and `noclobber` reports 1. The same text under `bash -c` reports 127 for those two guards. `rm` runs only against the temporary directory. A separate probe with `BUILD_DIR` set to empty still prints `rm -rf /*` and exits 0 under `set -u`. |

The container run uses the local engine so it can build and signal containers. It is not FORGE's coding sandbox, and that sandbox stays disabled. The shell lesson never executes a removal of `/` or `/*`. GNU coreutils 9.12 is cited for `--preserve-root` and was not used as a test of that removal.

Evidence: [fresh worked examples](validation/p7-examples-recheck.json). The shell fence also passed unchanged on Linux Bash **5.2.37**, as UID/GID 65534, with no network, no host mounts, a read-only root, and bounded scratch space. Both file-based Bash 3.2 and Linux Bash 5.2 produced the displayed stdout. The container signal comparison observes state after 0.8 seconds; it is not a portable shutdown deadline or a full grace-period test.

## Content gate and resource validation

The existing gate passes with **0 errors and 30 warnings**. The warning list matches P6. No P7 lesson warning was introduced. The final URL pass checked **263 distinct resource URLs and all returned 200**.

An earlier pass reported `URLError` for three unchanged PostgreSQL documentation pages. Those pages were reachable on retry, and the full gate was run again. The November 9 recheck also saw transient request errors on three unchanged references (WHATWG Fetch, Fowler Circuit Breaker, and systemd.service); each returned 200 on investigation and the complete gate then passed. No gate logic or source URL was changed. See [fresh QA result](validation/p7-qa-recheck.json).

## Independent advisory review

**gpt-oss:120b reviewed all ten drafts.** One scaling response was malformed, discarded, and reviewed again. Ten retained reviews report ready, with **50 findings: 9 labeled error, 9 important, and 32 suggestion**. Six wording fixes were incorporated. The other findings were already covered, deferred as extra scope, or rejected because they contradicted an execution, a cited manual, or the rule that advisory review is not human verification. Detail is in [P7_REVIEW.md](P7_REVIEW.md) and [p7-review.json](validation/p7-review.json).

The November 9 accuracy pass corrected the container practice's use of “two-stage”: separate cache layers form a single build stage unless another `FROM` starts a new stage, as [Docker documents](https://docs.docker.com/build/building/multi-stage/). A focused independent follow-up reviewed that final file; its three findings and individual dispositions are retained in the same review record. Two concerns were already covered by the worked example or explicit timing limitation; a volume demonstration is deferred. Three malformed follow-up JSON responses were discarded before collecting a readable advisory review. This correction is outside the executable fences. All ten fences were rerun and still matched.

## Integration, preservation and test results

**404 backend tests passed in 108.71 seconds** on the fresh local database `forge_p7_tests_20261109`. No tests were skipped. Reading a lesson still creates no mastery evidence.

Frontend lint, TypeScript checking, and the **production webpack build passed**. No frontend source, package manifest, or lockfile changed. The webpack path is the one already used for P6. Turbopack configuration was left alone.

The source guard confirms **75 pre-existing seed, curriculum, and mastery-algorithm files** are byte-identical to production commit `25c4b6f`. The curriculum checksum is unchanged: `4f4eb928bee1243b526cb3bfdbc725f0b894acb5b63fe8b8f6a9b0063fdc0941`. All 35 previous lessons remain. The lesson prerequisite graph is acyclic. The ten new `(skill, topic)` pairs were previously uncovered. A body comparison against the older lessons had a maximum SequenceMatcher ratio of 0.057. That is only a screen. The new lessons sit beside the broad introductions. They do not replace them.

The scratch rehearsal used an empty `forge_p7_rehearsal_final_20261109` database, migrated to 0009, loaded the 35-lesson P6 baseline from `25c4b6f`, and created synthetic history through the API. It then ran the full P7 seed **twice**.

Both runs produced 158 active questions, zero inactive questions, 45 lessons, 45 covered subskills, 147 lesson-check links, and 157 resources. Fingerprints across **60 learner-linked tables** stayed identical, including the synthetic answers, mastery rows, and the one lesson read. Protected question, option, skill, topic, and prerequisite fingerprints were unchanged. The 35 existing lesson IDs survived. The two seed runs matched each other. The loader still regenerates lesson-check and resource surrogate IDs. That is not physical row-ID idempotency for those rows.

Evidence: [fresh backend log](validation/p7-backend-tests-recheck.txt), [fresh production build](validation/p7-web-build-recheck.txt), [fresh seed rehearsal](validation/p7-seed-rehearsal-recheck.json).

## Coverage delivered by the approved release

| Metric | P6 baseline | Deployed P7 |
| --- | --- | --- |
| Skills / subskills / curriculum prerequisite edges | 15 / 45 / 21 | unchanged |
| Active / inactive questions | 158 / 0 | unchanged |
| Lessons / dedicated subskills | 35 / 35 | 45 / 45 |
| Dedicated subskill coverage | 77.8% | 100% |
| Dedicated lesson gaps | 10 | 0 |
| Skills whose three subskills each have a dedicated lesson | 9 | 15 |

**45/45 is instruction coverage.** It is not human verification, not a full beginner-through-advanced question bank on every subskill, and not a measured learning gain.

## Release boundary

The [P7 manifest](validation/p7-manifest.json) freezes the approved ten lesson hashes, mappings and expected counts. Its validation-time `NOT DEPLOYED` label is retained as a preparation record. The user's later explicit approval authorized release `2e080e2`, whose [deployment record](P7_DEPLOYMENT.md) confirms backup, exact counts, preservation and health. The manifest itself was not rewritten after approval. Further major features or content batches require separate approval; no post-curriculum proposal below changes production automatically.

Run the local checks from `api/` with the existing virtual environment:

```bash
venv/bin/python -m app.seed.qa --check-urls
venv/bin/python tools/validate_p7.py
venv/bin/python tools/rehearse_p7.py
venv/bin/python -m pytest -q
```

Use a fresh local `forge_p7_*` database in `FORGE_P7_DATABASE_URL` for rehearsal. The tool refuses a database that already has public tables. Point `FORGE_TEST_DATABASE_URL` at a different disposable database. From `web/`, run lint, typecheck, and `npm run build -- --webpack`.

## What to do after P7

Production, as recorded at the P6 release, has three learners, three answers, three mastery-evidence rows, three mastery events, and **zero lesson reads**. That history cannot yet say which lesson teaches well or which question is too easy. The next improvement should come from attempts that actually happen and from a human reading of instructional quality.

Use the attempts once they exist: which checks are missed, whether the linked lesson was opened, and whether the explanation matches the miss. Revise the example, the feedback, or the distractor that the attempts expose. A human pass over the existing lessons, especially incidents, shell expansion, and the container signal example, is a quality check on material that is already written. Another batch of lessons is not the next step. Dedicated coverage of this 45-subskill map is complete.

With more attempts, review first-attempt errors, repeated errors after reading, and later review answers for the same concept. Show attempt and learner counts beside each rate; this small baseline cannot support reliable rankings or causal claims about reading a lesson. Use failed transfer exercises and human review to choose revisions, then compare later attempts with the same limitations stated. Prioritize clearer worked examples, reasoning feedback and misleading distractors when that evidence points to a problem. No new content batch, tracking infrastructure or mastery-rule change is proposed here.

The subsequent [post-curriculum report](POST_CURRICULUM_REPORT.md) audits all seven requested learning measures against the actual models and workflows, documents the tiny production baseline, prioritizes gaps, and provides the next month's study/evaluation plan. Use the [human review checklist](HUMAN_REVIEW.md) for revision-specific sign-off; no human-verified status was awarded by this release.
