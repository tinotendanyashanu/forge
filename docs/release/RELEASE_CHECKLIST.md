# FORGE 1.0 release checklist

Tick each item on the machine you release on. ✅ marks items completed during the 1.0 audit (2026-11-04).

## Code and tests
- [x] ✅ `cd api && venv/bin/python -m pytest -q`: all pass, sandbox tests not skipped
- [x] ✅ `venv/bin/alembic check`: no pending operations (the test suite also runs downgrade base / upgrade head)
- [x] ✅ `venv/bin/python -m app.coding.verify_bank` and `venv/bin/python -m app.workspace.verify_projects` (also run inside pytest)
- [x] ✅ `cd web && npm run lint && npm run typecheck && npm run build`
- [ ] `npm audit` and `pip-audit` reviewed (not done in the 1.0 audit)

## Configuration
- [ ] `api/.env` created from `.env.example`; database URL and LLM key set; file not committed
- [ ] `FORGE_LOCAL_ONLY=true`; web started with `npm start` (binds 127.0.0.1)
- [ ] AI budgets reviewed: `FORGE_LLM_MAX_CALLS_PER_HOUR` fits your provider plan
- [ ] Code execution: either `FORGE_SANDBOX_BACKEND=disabled`, or `docker` with the image built and `GET /api/v1/coding/status` showing `verified: true`

## Data
- [ ] Backup taken before upgrading (`pg_dump -Fc`, see DEPLOYMENT.md)
- [ ] `alembic upgrade head` and `python -m app.seed` run
- [x] ✅ Restore procedure verified into a scratch database

## Smoke checks after start
- [ ] `GET /health` returns 200, version 1.0.0, database ok
- [ ] `GET /api/v1/llm/status` shows `reachable: true` (if AI is configured)
- [ ] One diagnostic answered; the learning path shows evidence-based reasons
- [ ] One interview answer is evaluated (or saved as ungraded with a reason if AI is off)
- [ ] One coding submission runs in the verified sandbox (if enabled)

## Release gate
- [x] ✅ Deployment target is local single-user. **Do not** publish to a network: no authentication, container-only isolation
