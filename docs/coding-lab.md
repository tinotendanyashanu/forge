# Coding lab (Milestone 5)

Learners solve hand-written challenges in a Monaco editor. Public tests run on
demand; submissions run every test, including hidden ones, in an isolated
sandbox. Verified results feed the mastery engine as **practical** evidence. An
optional AI review comments on the code but never decides correctness.

## Architecture

```
browser ──► Next.js server ──► FastAPI (never executes code)
                                   │  INSERT coding_jobs (queued)
                                   ▼
                              PostgreSQL ◄──── worker: python -m app.coding.worker
                                                 │ claims a job (FOR UPDATE SKIP LOCKED + lease)
                                                 │ stages files in a fresh temp dir
                                                 ▼
                                    docker run --network none --read-only … (one container per job)
                                                 │ prints raw outputs only
                                                 ▼
                                    worker grades outputs against expected values (trusted)
```

**Trust boundary.** The sandbox receives the learner's code, a harness and the
test *inputs*. Expected values never enter it. The worker's comparator grades the
raw outputs. So code that tampers with the harness or prints fake results can't
forge a pass: producing the correct output *is* solving the problem. Hidden-test
error messages are reduced to the exception type before storage.

## Security model

| Control | How |
| --- | --- |
| Separate process | Only `app.coding.worker` runs code; the API only queues jobs |
| No network | `--network none`; probe confirms only `lo` is up and outbound connects fail |
| No privileges | `--cap-drop ALL`, `--security-opt no-new-privileges`, user `65534:65534` (nobody) |
| Filesystem | `--read-only` root; job files bind-mounted **read-only**; `/tmp` tmpfs `noexec,nosuid,nodev`, sized to the challenge's memory limit (16–128 MB, counted against the same cgroup) |
| Resources | `--memory` = `--memory-swap` (no swap), `--cpus 1`, `--pids-limit 64`, `nofile=64`, `fsize=8MB`, per-test timeout, wall-clock kill, stdout cap |
| No secrets | No host env passed, no Docker socket, no DB access, no other mounts; probe checks env and socket |
| Ephemeral | `--rm`, unique name, temp dir deleted after each run, `--log-driver none` |
| Self-verification | Before taking jobs, the worker runs a probe *inside* the sandbox for each image and refuses jobs (status `blocked`) if any check fails |

**Limitation.** This is container isolation on the standard `runc` runtime. It is
**not** adequate for hostile multi-tenant workloads. The Docker backend refuses
to run unless `FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true` acknowledges a
local, single-user deployment. Before any shared deployment, run the worker
under a stronger boundary: gVisor (`runsc`), Kata or Firecracker microVMs, or a
managed sandbox service, on hosts with nothing else of value.

## Backends

| `FORGE_SANDBOX_BACKEND` | Behaviour |
| --- | --- |
| `disabled` (default) | Job creation returns 503. Learners can read challenges and save drafts. |
| `mock` | Jobs go through the real queue, but **nothing executes**. Every test is `not_executed`, submissions are `executed=false`, and nothing becomes evidence. The UI says so. |
| `docker` | Hardened container per job, as above. Requires the acknowledgement flag and a passing self-check. |

## Environment variables (API and worker)

| Variable | Default | Purpose |
| --- | --- | --- |
| `FORGE_SANDBOX_BACKEND` | `disabled` | `disabled`, `mock` or `docker` |
| `FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION` | `false` | Must be `true` for the docker backend (single-user acknowledgement) |
| `FORGE_SANDBOX_PYTHON_IMAGE` | `forge-sandbox-python:2` | Built from `api/sandbox/python-lab` (Python 3.12, FastAPI, httpx, psycopg, a private PostgreSQL); never auto-pulled |
| `FORGE_SANDBOX_NODE_IMAGE` | `node:24-alpine` | JS/TS runtime (Node strips TypeScript types; types are **not** type-checked) |
| `FORGE_SANDBOX_MAX_OUTPUT_BYTES` | `65536` | stdout cap; the container is killed beyond it |
| `FORGE_SANDBOX_MAX_TIME_MS` | `10000` | Upper bound on any job's run time (plus 2.5 s startup allowance) |
| `FORGE_SANDBOX_MAX_MEMORY_MB` | `256` | Upper bound on any challenge's memory limit |
| `FORGE_SANDBOX_PIDS_LIMIT` | `64` | Max processes per container |
| `FORGE_WORKER_POLL_SECONDS` | `1.0` | Queue poll interval |
| `FORGE_JOB_LEASE_SECONDS` | `90` | Lease; expired leases are reclaimed by another worker |
| `FORGE_JOB_MAX_ATTEMPTS` | `3` | Infrastructure retries before a job fails |
| `FORGE_CODING_MAX_CODE_BYTES` | `65536` | Max code size for drafts and jobs |
| `FORGE_CODING_RUNS_PER_MINUTE` | `10` | Per-learner rate limit for public-test runs |
| `FORGE_CODING_SUBMITS_PER_HOUR` | `30` | Per-learner rate limit for submissions |
| `FORGE_CODING_MAX_ACTIVE_JOBS` | `2` | Per-learner concurrent queued and running jobs |

LLM settings for the AI review are the existing `FORGE_LLM_*` variables (see
`docs/interviewer.md`). Web: `FORGE_API_URL` only; Monaco is served from
`public/monaco`, which `npm run dev`/`build` copy there automatically.

## Running it locally

```bash
docker build -t forge-sandbox-python:2 api/sandbox/python-lab && docker pull node:24-alpine
cd api
export FORGE_SANDBOX_BACKEND=docker FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true
venv/bin/alembic upgrade head && venv/bin/python -m app.seed
venv/bin/python -m app.coding.verify_bank        # proves every challenge in the real sandbox
venv/bin/uvicorn app.main:app --port 8000 &      # API (same env vars)
venv/bin/python -m app.coding.worker             # the only process that runs code
```

`GET /api/v1/coding/status` reports the backend, whether a worker is online,
and its self-verification report.

## Jobs, retries and idempotency

* Every job carries a client `idempotency_key` (unique per learner); a repeated
  request returns the original job (`200` instead of `202`).
* Re-submitting **identical code** for the same challenge version returns the
  earlier submission, so it can't create duplicate evidence.
* Rate limits are checked under a per-learner advisory lock, so they can't be raced.
* The worker fences completion on `(status = running, worker_id)`. A worker whose
  lease expired can't overwrite a job another worker finished. Results are unique
  per `(job, test)`, so a retry can't double-record.
* Learner-code failures (errors, timeouts, crashes, memory) are **results**, not
  job failures. Only infrastructure failures are retried, up to
  `FORGE_JOB_MAX_ATTEMPTS`.

## Challenge bank

`api/app/coding/bank/*.toml`: 19 hand-written challenges across 13 areas
(foundations, algorithms, Python/FastAPI, JS/TS, React, SQL and transactions, API
design, auth, concurrency, testing/debugging, performance, security, production).
Each has starter code, a reference solution, public and hidden tests, limits, a
rubric, misconceptions and hints. Tests needing setup (SQLite databases, threads,
large generated inputs, frozen-state mutation checks) use a trusted *driver*
module. A content change creates a new immutable version; past jobs keep their version.

`python -m app.coding.verify_bank` runs every reference solution and every
starter through the real sandbox: references must pass everything, starters must
fail at least one hidden test. It runs in the test suite too.

### Challenges that need real infrastructure

* **`fastapi-users-endpoint`**: the learner builds a FastAPI app. Hidden tests
  send real HTTP requests through `TestClient` inside the sandbox (validation,
  422/404/409 paths, normalisation).
* **`postgres-concurrent-withdrawals`**: the driver starts a private PostgreSQL
  inside the container: a pre-initialised cluster copied to tmpfs, with a Unix
  socket only and no TCP. 8–12 connections withdraw concurrently; the balance
  must never go negative or lose an update. A racy read-then-write solution fails
  in every run, including when wrapped in a transaction.
* **`thread-safe-counter` (v2)**: the driver traces the learner's module and
  yields the interpreter between every executed line. That makes unguarded
  read-modify-write races deterministic, while correctly locked code is
  unaffected. (v1 relied on timing and could let a racy solution pass.)

## Acceptance checklist

1. `docker build -t forge-sandbox-python:2 api/sandbox/python-lab`
2. Set the coding env vars plus `FORGE_LLM_*` (Ollama Cloud) in `api/.env`; start
   the API, the worker and the web app.
3. `GET /api/v1/coding/status` → `verified: true, worker_online: true`.
4. For `merge-intervals`, `fastapi-users-endpoint` and `postgres-concurrent-withdrawals`:
   run the public tests, submit the starter (hidden failures, nothing leaked),
   submit a correct solution (all pass, *verified sandbox*), and request an AI review.
5. Check **Coding lab** → practical progress, then **Progress** and **Learning path**
   for the new practical evidence.

## Mastery integration

* Submissions executed by a **verified** sandbox become `coding_submission`
  evidence: verified, in the **practical** dimension, with score = share of
  hidden tests passed. Success means all tests passed with at most one hint.
  Mock and unverified runs never count.
* `practical_score` is reported separately from knowledge accuracy and from
  unverified AI judgments. AI code reviews are never evidence.
* Coding challenges make levels verifiable. That lets Programming Fundamentals
  and Security become assessable, and lets advanced Python, HTTP, System Design and
  Programming Fundamentals levels be verified.
* Recommendations add `practical_retry` (your last submission failed; it reports
  how many hidden tests passed) and `practical` (verified practice once knowledge
  is shown), respecting challenge prerequisites. Repeated hidden-test failures
  appear as knowledge gaps with the challenge's known misconception.
* Algorithm version `mastery-v1.2` (now `mastery-v1.3`, see `docs/mastery.md`): snapshots recompute automatically.

## AI code review

`POST /api/v1/coding/submissions/{id}/review` (idempotent; ungraded reviews can be retried):

* The model sees the challenge, rubric, misconceptions, test outcomes (public
  details; hidden counts and names only) and the code as delimited untrusted data.
  It never sees the reference solution or hidden inputs and expected values.
* Output is schema-validated (findings by dimension, severity and line;
  follow-up questions; at most 2 hints). Out-of-range line numbers are dropped.
  Any text sharing an 8-token run with the reference solution is removed, and the
  review records `leak_blocked`.
* A server-written grounding line states the hidden-test result and that the
  review doesn't prove correctness. Failures are stored as `ungraded`; nothing
  is invented.

## What's real, mocked or blocked

| Area | Status |
| --- | --- |
| Monaco editor, plain-text alternative, autosave, reset, hints, run and submit | **Working**, tested in Chrome |
| Python, JavaScript and TypeScript execution in the hardened container | **Working** locally, after explicit single-user opt-in |
| Hostile multi-tenant isolation (gVisor, microVMs) | **Not available here.** Required before any shared deployment |
| TypeScript type-checking | **Not done.** Node strips types and runs the code |
| AI code review | **Working.** Automated tests use a fake model; a FORGE 1.0 smoke test against Ollama Cloud (`gpt-oss:120b`) reviewed a real sandbox submission correctly |
| Mock runner | Labelled everywhere; never evidence |
| Authentication | **None.** Learner routes are local-only (`FORGE_LOCAL_ONLY`) |
