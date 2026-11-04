# Architecture and trust boundaries

**Scope:** FORGE 1.0 on one machine for one learner. Product behavior and limitations follow the [release report](release/RELEASE_NOTES_1.0.md). Component names, paths and local ports below were checked against the accessible source tree; no application execution or architecture audit was performed for this document.

## Components

| Component | Responsibility | Source locations |
| --- | --- | --- |
| Next.js / React web app | Browser experience, anonymous learner cookie, server-side API requests and actions. | `web/src/app/`, `web/src/components/`, `web/src/lib/api.ts`, `web/src/lib/workspace-api.ts` |
| FastAPI API | Assessment and learning routes, module orchestration, request limits and local-access checks. | `api/app/main.py`, `api/app/api/`, `api/app/services/` |
| PostgreSQL / SQLAlchemy | Application persistence, including learning activity, evidence and execution jobs. Alembic manages schema migrations. | `api/app/db/`, `api/migrations/`, `docker-compose.yml` |
| Execution worker | Claims database-backed execution jobs and invokes the sandbox for coding and workspace checks. | `api/app/coding/worker.py`, `api/app/workspace/jobs.py` |
| Container sandbox | Runs code and test harnesses under the configured container backend; verification scripts check bundled content. | `api/app/coding/sandbox.py`, `api/app/coding/harness/`, `api/sandbox/python-lab/` |
| AI provider adapter | Connects configured model endpoints to advisory interview evaluations and module reviews. Includes fake-provider support for tests. | `api/app/llm/`, `api/app/interview/` and module review files |
| Mastery and curriculum | Organizes curriculum, evidence, recommendations, gaps and spaced review. The reported engine is `mastery-v1.5`. | `api/app/mastery/`, `api/app/curriculum/`, `api/app/seed/` |

Module-specific code lives in `api/app/design/`, `ops/`, `career/` and `workspace/`. The workspace's FastAPI and PostgreSQL exercises are learning content as well as examples of technologies used in the platform; they are not separate hosted customer services.

## Local request flow

1. The learner opens the local web app at `127.0.0.1:3000`.
2. The Next.js server reads the anonymous httpOnly learner cookie and makes server-side calls to FastAPI at `127.0.0.1:8000`. The web API client supplies `X-Learner-Id` for learner-scoped calls.
3. The API reads and writes PostgreSQL using SQLAlchemy. The supplied Compose file publishes the database only at `127.0.0.1:5434`.
4. Activities update the learning record and evidence used by the mastery features. AI review text remains advisory; it does not decide correctness, approval or verified mastery.

The learner identifier is **not authentication**. A local API restriction protects the intended deployment boundary, but does not supply accounts or authorization suitable for shared access. Exposing the web server can allow remote visitors to reach an API through that local server.

## Code-execution flow

1. A coding-lab or workspace action creates an execution job.
2. The separate worker claims the job from the database and calls the configured sandbox.
3. The real Docker backend verifies its environment and runs the test harness in a container. Hidden tests inform deterministic results; advisory AI review is a separate step.
4. Job results and progress are persisted and shown through the local application.

The normal configuration defaults to disabled execution; mock execution does not establish real correctness. The two content-verification entry points explicitly select Docker and the isolation acknowledgement internally. See [DEVELOPMENT.md](DEVELOPMENT.md#optional-enable-real-code-execution) before running them.

The release uses **runc container isolation** and requires a single-user acknowledgement. This does not establish a safe boundary for hostile or multi-tenant code. gVisor, Kata and Firecracker are future isolation options mentioned in the report, not implemented capabilities claimed here.

## AI boundary

The API owns provider configuration and keys. With a configured cloud endpoint, relevant prompts, answers or source content are sent to that provider for evaluation or review. Do not infer that all data stays on the machine from the phrase “local-only.”

`FORGE_LLM_MAX_CALLS_PER_HOUR` limits calls across modules **within an API process**. Run one API process. The configured cap is a call-count control; it does not guarantee a maximum bill in currency. Provider failure, fake-provider tests and advisory output must be distinguished from verified learning evidence.

## Content and schema

The source keeps seeded assessment material under `api/app/seed/content/`, coding exercises under `api/app/coding/bank/`, OPS scenarios under `api/app/ops/scenarios/`, and multi-file projects under `api/app/workspace/projects/`. Keep this content and its migrations in version control; do not blanket-ignore JSON, TOML or SQL files.

The report states migration head `0008` and no schema changes since Milestone 9. Back up before migrations or reseeding an existing learner database. Test fixtures downgrade and recreate the **test** schema; keep the test database separate.

## Boundaries that remain unresolved

The report does not establish public authentication, multi-user authorization, a shared rate-limit store, hardened multi-tenant execution or an audited public deployment. It also records no completed Content-Security-Policy, dependency vulnerability scan or screen-reader audit. Do not infer these capabilities from framework choices or container use.

See [SECURITY.md](../SECURITY.md), [LIMITATIONS.md](LIMITATIONS.md) and [local setup](DEVELOPMENT.md).
