# Local setup and development

> [!WARNING]
> **LOCAL-ONLY · ONE LEARNER · ONE API PROCESS.** FORGE 1.0 has no authentication. Keep the web app, API and database on loopback, and do not expose them through a shared network, proxy or tunnel. Real code execution uses container isolation unsuitable for untrusted multi-tenant use. Read [SECURITY.md](../SECURITY.md) first.

These commands match the project's manifests, configuration and verification scripts. The migration, seed, test, verification and build commands were run during the 1.0 release audit; a from-scratch install on a fresh clone has not yet been rehearsed. Examples use a macOS/Linux-style shell. Start each named terminal at the repository root unless otherwise stated.

## Requirements

| Requirement | Evidence and purpose |
| --- | --- |
| Python `>=3.12` | Declared in `api/pyproject.toml`. Verify that your `python3` meets it. |
| Node.js and npm | The lockfile's installed Next.js entry declares Node `>=20.9.0`. Use a compatible toolchain; no Node version matrix was tested for this package. |
| Docker with Compose | The supplied Compose file runs PostgreSQL 16. Real sandbox checks additionally need Docker execution access and the documented images. |
| Source checkout | Must include `api/`, `web/`, `web/package-lock.json` and `docker-compose.yml`. |
| Optional model endpoint | Needed for real AI evaluations/reviews; cloud usage may incur provider charges. Start disabled if you only want the local non-AI setup. |

No GitHub owner, repository URL, private key or provider account is assumed. Obtain the source using the eventual repository's **Code** action and open the source root.

## 1. Start the local database

From the repository root:

```bash
docker compose up -d
docker compose ps
```

Wait for PostgreSQL to become healthy. The supplied file uses container `forge-postgres`, a persistent named volume and host port `127.0.0.1:5434`. Its example username/password are local development defaults; never reuse them for another service.

The initialization SQL creates the separate `forge_test` database only when a new database volume is initialized. If reusing an existing volume, check whether that test database exists. Do not delete a populated volume to force initialization.

## 2. Configure and initialize the API

In an API terminal:

```bash
cd api
cp -n .env.example .env
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

`cp -n` preserves an existing file. Edit your private `api/.env` before continuing. The example database URLs match the supplied local Compose configuration. Confirm:

- `FORGE_DATABASE_URL` points to the learner database you intend to use.
- `FORGE_TEST_DATABASE_URL` points to a **different, disposable database**.
- `FORGE_LOCAL_ONLY=true` remains enabled.
- `FORGE_LLM_PROVIDER=disabled` and `FORGE_SANDBOX_BACKEND=disabled` remain in place for the initial setup.

If this is an existing installation, take a database backup before the next commands. From `api/`:

```bash
venv/bin/alembic upgrade head
venv/bin/python -m app.seed
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep this terminal running. Start a single API process; do not add multiple workers.

## 3. Build and start the web app

In a second terminal, from the repository root:

```bash
cd web
cp -n .env.example .env
npm ci
npm run build
npm start
```

Keep `FORGE_API_URL=http://127.0.0.1:8000` in the private web environment. This is a server-side setting; provider and database credentials belong in the API environment, never in `NEXT_PUBLIC_*` values.

Open [http://127.0.0.1:3000](http://127.0.0.1:3000) on the same machine. The checked-in `start` and `dev` scripts bind to `127.0.0.1`. For web development, `npm run dev` can be used instead of the build/start pair. Run only one web instance on the selected port.

## 4. Check the initial setup

From another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/api/v1/llm/status
curl --fail http://127.0.0.1:8000/api/v1/coding/status
```

Check the actual responses rather than assuming startup means success. `/health` includes a database check. AI and execution status should reflect their disabled configuration; this is not evidence that AI or real code execution was tested.

## Optional: configure AI

In `api/.env`, use the variables already defined in `.env.example` and `api/app/core/config.py`:

- `FORGE_LLM_PROVIDER`: use `openai_compatible` for an appropriate compatible endpoint, or the documented `ollama` option.
- `FORGE_LLM_BASE_URL`, `FORGE_LLM_MODEL`, `FORGE_LLM_API_KEY`: use the endpoint, model and secret issued for your provider. No key is included in this package.
- `FORGE_LLM_MAX_CALLS_PER_HOUR`: process-wide call-count cap, default `600` in the inspected configuration; `0` disables the cap.
- `FORGE_INTERVIEW_LLM_CALLS_PER_HOUR`: per-learner interview limit, default `60` in the inspected configuration.

Restart the API after changing settings. Test the configured provider through the local app and status endpoint. AI is advisory and can fail or be wrong. Review what content goes to remote providers and monitor their billing separately; an hourly call limit is not a fixed monetary cap. The release's real-model coverage did not include design-lab, OPS or career AI calls.

## Optional: enable real code execution

Only proceed after accepting the local, single-user container boundary. Do not submit code from untrusted remote users.

From the repository root, build/pull the images used by the inspected configuration:

```bash
docker build -t forge-sandbox-python:2 api/sandbox/python-lab
docker pull node:24-alpine
```

In private `api/.env`, explicitly set:

```dotenv
FORGE_SANDBOX_BACKEND=docker
FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true
```

Keep the existing image settings unless you deliberately changed the build tags. Restart the API after the configuration change.

From `api/`, verify the bundled content:

```bash
venv/bin/python -m app.coding.verify_bank
venv/bin/python -m app.workspace.verify_projects
```

**These verification entry points select the real Docker backend and isolation acknowledgement internally.** Running them executes bundled starter/reference code in containers, even if the ordinary environment setting is disabled. A successful check requires reference solutions to pass and starters to fail at least one hidden check. Investigate failures rather than bypassing verification.

Then start the worker in a separate terminal, from the repository root:

```bash
cd api
venv/bin/python -m app.coding.worker
```

With the API and worker running, inspect `/api/v1/coding/status` and `/api/v1/workspace/status`. Confirm the real backend, sandbox verification and worker state before treating execution results as evidence. Read the existing `docs/coding-lab.md` and `docs/workspace.md` in the source for deeper implementation notes.

## Testing

> [!CAUTION]
> The API test fixtures **downgrade and recreate the configured test schema** and clear learner test records. Confirm that `FORGE_TEST_DATABASE_URL` resolves to a disposable database distinct from the learner database, including host and database name. Different URL strings alone are not sufficient protection. Back up valuable data first.

From `api/`, after confirming that separate test database exists:

```bash
venv/bin/python -m pytest
```

The full suite includes real-container tests, so prepare the images and review the execution boundary first. Missing test-database or sandbox prerequisites can produce skips or failures. Record the actual summary and skip reasons; do not describe unexecuted checks as passing.

From `web/`:

```bash
npm run lint
npm run typecheck
npm run build
```

The web app's type-check command does not change the release limitation that **learner TypeScript is stripped rather than type-checked in the execution sandbox**. A web build is not a browser-automated end-to-end test. Fake-provider coverage is not a real-model smoke test.

## Upgrading

1. Stop active learning/execution work and back up the learner database and any local material you need to keep. Keep backups outside the repository.
2. Review new optional settings in `api/.env.example` and merge them into your private configuration. Do not overwrite existing credentials.
3. From `api/`, run `venv/bin/alembic upgrade head`, then `venv/bin/python -m app.seed`.
4. From `web/`, install the locked dependencies if they changed and run `npm run build`.
5. Restart the local processes and check health/status and a representative local workflow.

The release reports no schema changes since Milestone 9 and migration head `0008`. If the source has moved beyond that release, review its migration history before upgrading.

## Stop and preserve data

Stop the API, web app and worker in their terminals. `docker compose stop` stops the database while keeping its volume. **Do not run `docker compose down -v` on learner data you need to keep; it deletes the Compose volumes.**

Review [SECRETS_CHECKLIST.md](SECRETS_CHECKLIST.md) before committing environment examples, diagnostics or screenshots.
