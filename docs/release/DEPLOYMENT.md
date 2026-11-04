# FORGE 1.0: deployment and operations

**Supported deployment: one machine, one learner, everything bound to
`127.0.0.1`.** FORGE 1.0 has no login. The learner is identified by an
anonymous, httpOnly cookie. Code execution uses container isolation, which is
acknowledged as single-user only. Don't expose FORGE on a network or the
internet; see "Not supported" below.

## Processes

| Process | Command | Listens on |
| --- | --- | --- |
| PostgreSQL 16 | `docker compose up -d` (repo root) | `127.0.0.1:5434` |
| API | `cd api && venv/bin/uvicorn app.main:app --port 8000` | `127.0.0.1:8000` (uvicorn default) |
| Execution worker | `cd api && venv/bin/python -m app.coding.worker` | none (polls the database) |
| Web | `cd web && npm run build && npm start` | `127.0.0.1:3000` (the `start` script binds it) |

Run **one** API process. The global AI budget is counted per process.

The worker is the only process that executes learner code. Run it only with
`FORGE_SANDBOX_BACKEND=docker`, and only after the sandbox image is built.

## First-time setup

```bash
docker compose up -d
docker build -t forge-sandbox-python:2 api/sandbox/python-lab && docker pull node:24-alpine   # only for code execution
cd api
cp .env.example .env                     # then edit: database URL, LLM settings
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/alembic upgrade head            # migrations 0001 to 0008
venv/bin/python -m app.seed              # curriculum, questions, challenges, scenarios, projects (idempotent)
venv/bin/python -m app.coding.verify_bank && venv/bin/python -m app.workspace.verify_projects   # proves content in the real sandbox
cd ../web && cp .env.example .env && npm ci && npm run build
```

## Environment variables

The API reads `FORGE_*` from the environment or `api/.env`. The web app reads
only `FORGE_API_URL`, server-side; it is never sent to the browser. Secrets
(`FORGE_DATABASE_URL`, `FORGE_LLM_API_KEY`) live only in `api/.env`, which is
gitignored, and are never returned by any endpoint.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FORGE_DATABASE_URL` | none (required) | `postgresql+asyncpg://…` |
| `FORGE_TEST_DATABASE_URL` | none | pytest only. **Dropped and recreated** by tests; must differ from the main database |
| `FORGE_ENVIRONMENT`, `FORGE_VERSION` | `development`, `1.0.0` | Reported by `/health` |
| `FORGE_CORS_ORIGINS` | localhost:3000 | The browser never calls the API directly |
| `FORGE_LOCAL_ONLY`, `FORGE_LOCAL_ONLY_ALLOWED_HOSTS` | `true`, loopback | Learner routes answer only loopback clients. Keep `true` |
| `FORGE_MAX_REQUEST_BYTES` | `2000000` | Larger request bodies get 413 |
| `FORGE_DEFAULT_SESSION_LENGTH` | `5` | Questions per assessment |
| `FORGE_LLM_PROVIDER` | `disabled` | `disabled`, `ollama` or `openai_compatible` |
| `FORGE_LLM_BASE_URL`, `FORGE_LLM_MODEL`, `FORGE_LLM_API_KEY` | none | Ollama Cloud: `https://ollama.com/v1`, `gpt-oss:120b`, your key |
| `FORGE_LLM_TIMEOUT_SECONDS`, `FORGE_LLM_MAX_RETRIES`, `FORGE_LLM_RETRY_BASE_DELAY`, `FORGE_LLM_RETRY_MAX_DELAY` | `60`, `2`, `0.5`, `4` | Per-call timeout and retries with backoff |
| `FORGE_LLM_MAX_OUTPUT_TOKENS`, `FORGE_LLM_TEMPERATURE` | `1200`, `0.1` | Some features request more output (reviews up to 2600) |
| `FORGE_LLM_STRUCTURED_OUTPUT`, `FORGE_LLM_MAX_REPAIR_ATTEMPTS` | `auto`, `1` | JSON-schema output, and one repair attempt for invalid output |
| `FORGE_LLM_MAX_CALLS_PER_HOUR` | `600` | **Global spending cap** across all learners and modules (0 disables it) |
| `FORGE_INTERVIEW_LLM_CALLS_PER_HOUR` | `60` | Per learner |
| `FORGE_DESIGN_LLM_CALLS_PER_HOUR`, `FORGE_OPS_LLM_CALLS_PER_HOUR`, `FORGE_CAREER_LLM_CALLS_PER_HOUR`, `FORGE_WORKSPACE_LLM_CALLS_PER_HOUR` | `60`, `60`, `40`, `30` | Per learner |
| `FORGE_SANDBOX_BACKEND` | `disabled` | `disabled`, `mock` (never executes) or `docker` |
| `FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION` | `false` | Must be `true` for `docker`; acknowledges single-user isolation |
| `FORGE_SANDBOX_PYTHON_IMAGE`, `FORGE_SANDBOX_NODE_IMAGE` | `forge-sandbox-python:2`, `node:24-alpine` | Never auto-pulled by jobs |
| `FORGE_SANDBOX_MAX_OUTPUT_BYTES`, `FORGE_SANDBOX_MAX_TIME_MS`, `FORGE_SANDBOX_MAX_MEMORY_MB`, `FORGE_SANDBOX_PIDS_LIMIT` | `65536`, `10000`, `256`, `64` | Hard caps per container |
| `FORGE_WORKER_POLL_SECONDS`, `FORGE_JOB_LEASE_SECONDS`, `FORGE_JOB_MAX_ATTEMPTS` | `1.0`, `90`, `3` | Queue behaviour |
| `FORGE_CODING_MAX_CODE_BYTES`, `FORGE_CODING_RUNS_PER_MINUTE`, `FORGE_CODING_SUBMITS_PER_HOUR`, `FORGE_CODING_MAX_ACTIVE_JOBS` | `65536`, `10`, `30`, `2` | Per learner; also apply to Workspace jobs and coding AI reviews |
| `FORGE_API_URL` (web) | `http://127.0.0.1:8000` | Where the Next.js server reaches the API |

## Database migrations

* Before every upgrade, **back up** (see below), then run `venv/bin/alembic upgrade head` and `venv/bin/python -m app.seed`.
* `alembic check` must print "No new upgrade operations detected".
* The test suite runs `downgrade base` and `upgrade head` on the test database on every run.
* Content (questions, challenges, projects) is versioned by content hash. Seeding never deletes or rewrites history; removed items are deactivated.

## Health checks and monitoring

| Check | Healthy |
| --- | --- |
| `GET /health` | 200, `database: ok`, version `1.0.0`. Returns 503 if the database is down |
| `GET /api/v1/coding/status` (or `/api/v1/workspace/status`) | `worker_online: true`, `verified: true` when code execution is enabled |
| `GET /api/v1/llm/status` | `reachable: true` when AI is configured. Cached for 30 s |

Logs go to stdout and stderr through uvicorn's and Python's `logging`:

* The worker logs each claim failure, sandbox problem and job crash (`forge.worker*`).
* Mastery sync failures are logged (`forge.mastery`), never raised.
* Every workspace action is recorded in `eng_audit_events`.

Model failures are stored on each evaluation as `error_code` (`provider_timeout`, `provider_rate_limited`, `malformed_output` and so on). They are never turned into scores.

Things to watch:

* jobs stuck in `queued` (worker down);
* jobs in `blocked` (sandbox self-check failed);
* a high share of evaluations with `error_code = provider_rate_limited`, which means the AI budget is too low or the provider is limiting.

## Backup and restore (verified for 1.0)

```bash
# Backup (consistent snapshot while running)
docker exec forge-postgres pg_dump -U forge -d forge -Fc > forge-$(date +%F).dump

# Restore into a NEW database, check it, then switch FORGE_DATABASE_URL to it
docker exec forge-postgres psql -U forge -d postgres -c "CREATE DATABASE forge_restored"
docker exec -i forge-postgres pg_restore -U forge -d forge_restored --no-owner < forge-YYYY-MM-DD.dump
```

For the 1.0 audit, this exact procedure was run against the development
database. The restored copy had identical row counts (learners, mastery
evidence, workspace files) and migration version `0008`.

Keep the Docker volume `forge_forge-pgdata`. `docker compose down -v` deletes all data.

## Rollback

1. **Application only** (no schema change): stop the processes, check out the previous release, rebuild the web app and restart.
2. **Schema**: restore the backup taken before the upgrade. This is preferred; it loses only data written since the backup.
3. **Alembic downgrade** (`alembic downgrade 0007`) also works, but it deletes Milestone 9 data: workspaces, PRs, and engineering mastery evidence. Use it only on a copy.

## Not supported in 1.0

Public, shared or multi-user deployment. That needs, at least:

* real authentication (today anyone who can reach the web app can create learners and act as them);
* a stronger sandbox boundary (gVisor, Kata or Firecracker);
* a shared rate-limit store, so the global AI budget holds across processes;
* TLS;
* a Content-Security-Policy.
