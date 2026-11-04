# FORGE API

FastAPI + async SQLAlchemy 2 + PostgreSQL. Serves the curriculum and questions,
runs assessments (deterministic grading) and AI interviews (validated LLM
evaluation), and computes evidence-based mastery, reviews and recommendations.

- AI interviewer and LLM configuration: [`../docs/interviewer.md`](../docs/interviewer.md)
- Mastery algorithm, curriculum graph and scheduling: [`../docs/mastery.md`](../docs/mastery.md)
- Coding lab, sandbox security model, worker and env vars: [`../docs/coding-lab.md`](../docs/coding-lab.md)
- FORGE Workspace (engineering projects, PR simulator): [`../docs/workspace.md`](../docs/workspace.md)

## Setup

```bash
docker compose up -d                 # from the repo root: Postgres 16 on 127.0.0.1:5434
cp .env.example .env                 # local credentials (gitignored)
python -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/alembic upgrade head
venv/bin/python -m app.seed          # curriculum + questions; idempotent
venv/bin/uvicorn app.main:app --reload --port 8000
venv/bin/python -m app.coding.worker # execution worker (only if FORGE_SANDBOX_BACKEND != disabled)
venv/bin/python -m pytest            # uses FORGE_TEST_DATABASE_URL; sandbox tests need Docker
```

All configuration comes from `FORGE_*` environment variables (see `.env.example`).
Database credentials stay server-side; the web app talks to this API from its
own server, and the browser never receives the API URL or database details.

## Endpoints (`/api/v1`)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` (no prefix) | Includes a live database check; 503 if the DB is down |
| GET | `/skills`, `/skills/{slug}` | Skills, topics, question counts per difficulty |
| POST | `/learners` | Creates an anonymous learner (see Identity) |
| GET | `/learners/me` | |
| POST | `/assessments` | `{skill_slug, difficulty, question_count?}` |
| GET | `/assessments`, `/assessments/{id}` | Learner's sessions |
| POST | `/assessments/{id}/next` | Current unanswered question; idempotent until answered |
| POST | `/assessments/{id}/answers` | `{item_id, selected_option_key \| response_text}` → feedback |
| GET | `/assessments/{id}/items/{item_id}/feedback` | 404 until an answer exists |
| GET | `/answers?limit=&skill=&session=` | Answer history |
| GET | `/progress` | Raw per-skill counts |
| GET | `/llm/status` | Provider, model, reachability (no credentials) |
| POST | `/interviews` | `{skill_slug, difficulty, mode, challenge_count}` |
| GET | `/interviews`, `/interviews/{id}`, `/interviews/{id}/summary` | |
| POST | `/interviews/{id}/answers`, `/dont-know`, `/hints`, `/continue` | Idempotent on `client_turn_id` |
| POST | `/interviews/{id}/evaluations/{eid}/retry` | Re-run a failed evaluation |
| GET | `/curriculum`, `/curriculum/skills/{slug}` | Public: graph, levels, objectives |
| GET | `/mastery`, `/mastery/{slug}` | Evidence-based mastery and level reports |
| POST | `/mastery/recalculate` | Idempotent sync |
| GET | `/recommendations`, `/reviews`, `/gaps`, `/progress/history` | |
| GET/PUT/DELETE | `/goals`, `/goals/{slug}` | |
| GET | `/coding/status`, `/coding/challenges`, `/coding/challenges/{slug}` | Public; never hidden tests or references |
| GET/PUT/POST | `/coding/challenges/{slug}/state`, `/draft`, `/hints` | Learner drafts (optimistic revisions) and hints |
| POST/GET | `/coding/jobs`, `/coding/jobs/{id}` | Queue run/submit (idempotency key); poll results |
| GET/POST | `/coding/submissions`, `/{id}`, `/{id}/review` | History, results, AI review |
| GET | `/coding/progress` | Practical progress per skill |
| * | `/workspace/...` | Engineering projects, workspaces, jobs, reviews, simulated PRs; see `docs/workspace.md` |

## Grading

- **Single choice** → graded deterministically against the stored correct
  option (`method: deterministic_choice`, `score` 0 or 1).
- **Free text** → saved with `status: pending_ai_evaluation`; `is_correct`,
  `score` and `method` are null. No keyword or length heuristics are used.
  Written assessment answers stay unscored; AI evaluation happens in
  interviews (see `docs/interviewer.md`).

Answer material (correct option, explanation, rubric, expected concepts,
misconceptions, resources) is only returned by the feedback endpoints, after
an answer has been saved.

## Identity

There is no authentication. Learner routes only accept loopback clients
(`FORGE_LOCAL_ONLY`). `POST /learners` returns an opaque UUID that
clients send as `X-Learner-Id`. It identifies a learner but does not prove
who they are: anyone with the id can act as that learner. Replace with real
auth before any shared deployment.

## Data model

`skills → topics → questions → (question_options, rubric_criteria, learning_resources)`;
`learners → assessment_sessions → session_items → answers → evaluation_results`;
`skill_progress (learner, skill)` holds counters updated in the same
transaction as each submission.

Integrity is enforced in the database, not just in code: composite foreign
keys tie an answer's option to its question and its question to the session
item; one answer per item; at most one correct option per question; CHECK
constraints on evaluation states, counters, slugs and URLs. Session rows are
locked (`SELECT … FOR UPDATE`) while serving and submitting.

## Seed content

`app/seed/content/*.json` — 8 skills, 24 topics, 40 questions (24 single
choice, 16 free text). Every question has a rubric, expected concepts,
misconceptions and learning resources; `app/seed/schema.py` rejects content
that doesn't. The loader upserts by slug and deactivates (never deletes)
questions removed from the seed.
