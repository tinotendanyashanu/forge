# FORGE Workspace: real-world engineering projects (Milestone 9)

Learners pick up a ticket in an unfamiliar, multi-file codebase, change it in a
browser IDE, prove the change with public and hidden tests in the isolated
sandbox, and take it through a simulated pull request with an AI senior
reviewer. Verified results feed the mastery engine and FORGE Career.

**Tests decide correctness. The AI reviewer never does.** A pull request is
approved only by deterministic, documented criteria. AI reviews and
collaboration write-ups are advisory, and they are never mastery evidence.

## Pieces

| Area | Where |
| --- | --- |
| Project library (immutable, content-hashed versions) | `api/app/workspace/projects/<slug>/` |
| Content models and validation | `api/app/workspace/content.py` |
| Version sync (run by `python -m app.seed`) | `api/app/workspace/library.py` |
| Path rules and safe staging (no traversal, no symlinks) | `api/app/workspace/paths.py` |
| Workspaces, files, snapshots, diffs, jobs | `api/app/workspace/service.py` |
| Sandbox execution and grading (worker only) | `api/app/workspace/execution.py`, `jobs.py`, `app/coding/sandbox.py` (`run_project`), `app/coding/harness/*_project_harness.*` |
| AI reviewer | `api/app/workspace/review.py` |
| PRs, decisions, collaboration exercises | `api/app/workspace/pr.py` |
| Competencies, recommendations, career portfolio | `api/app/workspace/progress.py` |
| HTTP API | `api/app/api/routes/workspace.py` |
| Migration | `api/migrations/versions/0008_forge_workspace.py` |
| Project verifier | `python -m app.workspace.verify_projects` |
| Tests | `api/tests/test_workspace.py` |
| Web | `web/src/app/workspace/**`, `web/src/components/workspace/**`, `web/src/lib/workspace-*.ts` |

## Projects

| Project | Level | Type | Stack | Tests (public/hidden) |
| --- | --- | --- | --- | --- |
| `task-api-status-codes`: Fix the Tasks API contract | Beginner | Bug fix | FastAPI | 3 / 6 |
| `invoice-discount-codes`: Ship discount codes across the stack | Mid | Feature | FastAPI + SQLite migration + TypeScript | 5 / 8 (two suites) |
| `payments-double-charge`: Stop double charges in the payment ledger | Senior | Bug fix | psycopg 3 + PostgreSQL (READ COMMITTED) | 4 / 6 |

Each project has:

* a description, architecture notes and setup instructions;
* a ticket with acceptance criteria;
* starter files;
* reference overrides;
* trusted public and hidden checks;
* competency tags on every test;
* a versioned rubric, misconceptions and hints;
* collaboration exercises (requirement changes, deployment plans, stakeholder updates, reviewing a teammate's code).

All three are verified in the real sandbox. Every reference passes every test.
Every starter fails at least one hidden test, for the intended reason:

* An edited `001` migration fails exactly the legacy-upgrade test.
* Python's `round()` fails exactly the half-up test.
* A fix that makes the debit atomic but keeps check-then-insert on the
  idempotency key fails exactly the double-charge tests.
* The concurrency tests gave identical results in 5 of 5 repeated runs, for
  the starter, the half-fix and the reference.

### Adding a project

1. Create `projects/<slug>/` with `project.toml`, `starter/`, `reference/` and
   `checks/{public,hidden}.{py,mjs}`.
2. Checks return raw observations. Put expected values in `project.toml`.
3. Run `python -m app.workspace.verify_projects <slug>`, then `python -m app.seed`.
4. Any content change creates a new version. Existing workspaces keep theirs.

## Execution and security model

Reuses the Milestone 5 sandbox and worker unchanged in every security-relevant
respect. That means:

* `--network none`, read-only root, non-root user 65534, `cap-drop ALL`, `no-new-privileges`;
* memory, CPU, PID, file-size and output limits;
* a wall-clock kill;
* no host environment, no Docker socket, no database access;
* one ephemeral container per run;
* a self-verification probe before any job runs.

Additions for projects:

* **Only the worker executes code.** Project jobs are claimed by the same
  `python -m app.coding.worker` process, with leases, fencing and retries.
* **Public and hidden checks run in separate containers.** A public run never
  contains the hidden checks file or hidden inputs. So learner code can't read
  hidden inputs and echo them through a public result.
* **Expected values never enter the sandbox.** The worker grades raw outputs.
  Hidden failures show no actual values. An exception type is shown only if it
  is a built-in name, so learner-defined exception class names can't carry
  data out.
* **Path safety.** Paths must be relative, at most 6 levels deep, use safe
  characters and an allowed extension, and contain no `.`/`..` or dot-files.
  Staging writes regular files with `O_NOFOLLOW | O_EXCL` under a fresh
  directory, and the files are mounted read-only.
* **Quotas.** At most 60 files, 64 KB per file and 512 KB per workspace; at
  most 200 snapshots.
* **Rate limits.** The coding limits apply: runs per minute, submits per hour
  and active jobs. AI calls are capped by `FORGE_WORKSPACE_LLM_CALLS_PER_HOUR`
  (default 30).
* **Audit log.** `eng_audit_events` records:
  * file create, update and delete;
  * reset, snapshot and restore;
  * jobs and hints;
  * reviews and PR actions.

A real-sandbox test runs hostile learner code. From inside the sandbox it
observed: network blocked, writes denied, no hidden checks file, no secrets,
uid 65534.

**Limitation (unchanged from M5).** This is container isolation on `runc`,
acknowledged for a local, single-user deployment
(`FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true`). It is not adequate for
hostile multi-tenant use. Use gVisor, Kata or Firecracker first. The node suite
strips TypeScript types; it does not type-check, and it does not render React.

## Workspaces, concurrency and versioning

* One workspace per learner and project. Opening a project again resumes it.
* Workspace files live in the database. Every file has a revision. A save must
  send the revision it edited, so a stale tab gets a 409, and the UI offers
  *Load saved version* or *Keep my version*.
* Reset and restore require the current workspace revision. Both take a safety
  snapshot first, so nothing is lost.
* Snapshots are immutable. Every run and submission snapshots the workspace
  first, so results always point at the exact code that ran.
* Diffs compare against the original project or any snapshot.

## Jobs, submissions, idempotency

* Every job carries a client `idempotency_key`. A retry returns the original
  job.
* Submitting an unchanged workspace again returns the earlier submission, so
  it can't create duplicate evidence.
* Submissions record public and hidden pass counts, hints used, whether code
  was executed, and whether the sandbox was verified.
* The reference solution unlocks only after a verified all-pass.

## AI senior reviewer

There are four modes: Guided Mentor, Strict Code Reviewer, Senior Engineering
Review and Technical Lead Review.

**What the model sees:**

* the ticket, acceptance criteria and numbered rubric;
* misconceptions and architecture notes;
* real test outcomes (public details; hidden test names only);
* the diff and the changed files with line numbers;
* the PR description and the learner's replies.

Code, the PR description and replies are delimited untrusted data.

**What the model never sees:** the reference solution, hidden inputs, or
expected values.

**Server-side rules after schema validation:**

* Findings are **proven failures**, **potential concerns** or **suggestions**.
* A "proven" finding must cite a test that actually failed. Matching forgives
  formatting only (case, quotes, typography); otherwise it is downgraded.
* With any failing test, "approve" is overridden to "request changes".
* Unknown paths and out-of-range lines are dropped.
* Until a verified all-pass, text sharing an 8-token run with the reference
  solution's changes is removed (`leak_blocked`).
* A server-written grounding line states the real test result.
* Suspected prompt injection is flagged.
* Failures are stored as `ungraded` and can be retried.
* Reviews are idempotent per (submission, mode).
* Prompt version `eng-review-v2`. Each review records its rubric version.

## Pull request simulator

The PR is internal and educational: **nothing is pushed anywhere**.

* **Opening** a PR snapshots the workspace and runs every test. There is one
  open PR per workspace, and opening is idempotent.
* **Revisions** are new snapshots plus full test runs. A revision with no
  changes is refused.
* **Inline comments** sit on lines of the latest revision.
* **AI reviews** become reviewer comments. Proven failures, major or blocker
  findings, requested changes and questions are requests that need a response.
* **Responses** are threaded under the reviewer comment.

**Approval criteria** (`pr.decide`, shown in the UI):

1. The latest revision ran in the **verified** sandbox (never the mock runner).
2. **All** public and hidden tests pass.
3. An AI review of the latest revision is completed. This is waived, and
   labelled as waived, when no LLM provider is configured.
4. Every reviewer request has a learner response.

Otherwise the PR is set to *changes requested*, and the unmet criteria are
listed. The learner can close a PR without merging. The AI's recommendation is
displayed and never gates approval.

## Mastery and career integration

* **Mastery `mastery-v1.5`.** Adds source `engineering_task`: verified,
  practical evidence on the project's skill.
  * Score is the share of hidden tests passed.
  * Success means all tests pass with at most one hint.
  * The workspace is the session, so a level needs successes on **two
    different projects**.
  * Mock or unverified runs and AI reviews never count.
* **Career.**
  * Engineering tasks map to `coding_objective` on the project's declared
    framework dimensions.
  * Eligible collaboration-exercise reviews map to `communication_ai`
    (unverified), by exercise kind.
  * The career dashboard and saved snapshots include an **engineering
    portfolio**: task complexity, verified outcomes per attempt, review
    history, revisions required and completion.
  * These are labelled as simulated work. They do not establish senior
    readiness by themselves.
* **Recommendations** (`/workspace/progress`) are based on:
  * tests failing in the latest verified submission, grouped by competency tag;
  * the same test failing in two or more submissions (repeated bugs);
  * major architecture concerns from reviews;
  * prerequisite skills not yet demonstrated.

## API (`/api/v1/workspace`)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/status` | Public. Sandbox, worker, AI availability |
| GET | `/projects`, `/projects/{slug}` | Public. Hidden checks and inputs are never included |
| POST | `/projects/{slug}/workspace` | Open or resume (201 or 200) |
| GET | `/workspaces`, `/workspaces/{id}` | Learner-owned only; others get 404 |
| GET | `/workspaces/{id}/files/{path}`, `/original/{path}` | |
| PUT | `/workspaces/{id}/files` | `{path, content, base_revision\|null}`; 409 when stale |
| POST | `/workspaces/{id}/files/delete` | `{path, base_revision}` |
| GET | `/workspaces/{id}/diff?against=` | vs original or a snapshot |
| GET/POST | `/workspaces/{id}/snapshots`, `/snapshots/{n}`, `/snapshots/{n}/restore` | |
| POST | `/workspaces/{id}/reset`, `/hints` | |
| GET | `/workspaces/{id}/history` | Audit log |
| POST/GET | `/workspaces/{id}/jobs`, `/jobs/{id}` | `{kind, idempotency_key}` |
| GET | `/workspaces/{id}/submissions`, `/submissions/{id}` | |
| POST | `/submissions/{id}/reviews` | `{mode}` |
| GET/POST | `/pulls`, `/workspaces/{id}/pulls`, `/pulls/{id}` | |
| POST | `/pulls/{id}/revisions`, `/comments`, `/reviews`, `/decision`, `/close` | Idempotency keys or client ids |
| GET/POST | `/workspaces/{id}/exercises`, `/exercises/{slug}` | |
| GET | `/progress`, `/portfolio` | |

## Manual verification

```bash
cd api && venv/bin/alembic upgrade head && venv/bin/python -m app.seed
venv/bin/python -m app.workspace.verify_projects          # all three: ok
export FORGE_SANDBOX_BACKEND=docker FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true
venv/bin/uvicorn app.main:app --port 8000 & venv/bin/python -m app.coding.worker &
cd ../web && npm run dev
```

1. Open **Workspace**, go to **Project library**, choose **Fix the Tasks API
   contract**, then **Open workspace**.
2. Click **Run tests**: 1/3 public tests pass, with diagnostics.
3. Fix only the priority validation. Then **Open pull request**: about 4/9
   pass, in the verified sandbox.
4. Click **Review revision 1**. Findings show; respond to some.
5. **Request final decision**: it is not approved, and the unmet criteria are
   listed.
6. Fix the routes and repository, then **Push revision**: 9/9 pass. Review
   again, then answer every request.
7. **Request final decision**: approved.
8. Check **Competencies**, **Progress** and **Career**.
