# System Design & Architecture Lab (Milestone 6)

Learners design architectures on a canvas, explain and record their decisions,
and defend them against an AI interviewer. A diagram is not evidence that a
design works. FORGE evaluates the **reasoning**: the flows, the trade-offs and
the failure analysis, grounded in the learner's own diagram and words.

## Pieces

| Area | Where |
| --- | --- |
| Graph schema and validation, diff, prompt rendering | `api/app/design/graph.py` |
| Rubric (12 criteria), competencies, failure scenarios | `api/app/design/catalog.py` |
| Versioned challenge library (17 challenges, 4 levels) | `api/app/design/challenges/*.toml`, loader `challenges.py` |
| Interviewer and evaluators (provider-agnostic) | `api/app/design/interviewer.py` |
| Projects, versions, ADRs, reviews, drills, recommendations | `api/app/design/service.py` |
| HTTP API | `api/app/api/routes/design.py` |
| Migration | `api/migrations/versions/0005_system_design_lab.py` |
| Web | `web/src/app/design/**`, `web/src/components/design/**` |

## Workspace

`/design/projects/[id]` is a three-panel workspace:

* **Left:** the challenge brief (requirements, hypothetical scale, reliability,
  security, constraints), the component library, the written explanation and ADRs.
* **Centre:** a React Flow canvas (`@xyflow/react`).
* **Right:** AI review (mode, conversation, hints, evaluations), failure drills
  and versions.
* **Mobile:** the same panels behind three tabs (Challenge, Canvas, Review).

Canvas features:

* 18 component types. Each has a name, responsibility, up to 12 properties and
  optional capacity and reliability assumptions.
* Labelled, directed connections: HTTP, WebSocket, RPC, events, DB queries,
  cache and replication.
* Drag from the library or press to add. Connect by dragging from a node edge
  onto another node, or use the inspector's "Connect to" (keyboard accessible).
* Move, rename, duplicate and delete; zoom, pan and fit; undo and redo (100 steps).
* Keyboard shortcuts (press `?`): ⌘Z, ⇧⌘Z or Ctrl+Y, ⌘D, Delete, ⌘S, F, Esc,
  and arrow keys move the focused node.

Saving and recovery:

* **Autosave:** 1.2 s after the last change, with a save indicator.
* **Optimistic concurrency:** every save sends `base_revision`, and a stale tab
  gets 409. The UI then offers "Keep my version" or "Load latest".
* **Local recovery:** a local copy is written to `localStorage` before each
  save and on unload. On reopen, unsaved local work is offered back. It is never
  applied silently.
* **Snapshots:** named and immutable. Evaluations and failure drills snapshot
  automatically, reusing an identical latest version. Versions can be viewed
  (read-only canvas), compared (structural diff) and restored. Restoring
  snapshots the current design first, so nothing is lost.

## Challenge library

TOML, validated by Pydantic at seed time (`python -m app.seed`). Each challenge has:

* business context, functional and non-functional requirements;
* scale assumptions (at least one line must start with "Hypothetical");
* reliability, security, constraints, prerequisites, competencies, hints and
  suggested failure scenarios.

Hidden fields (`expected_concepts`, `rubric_focus`, `common_mistakes`,
`follow_ups`) are never served before the learner's first completed
evaluation of that challenge. After that, `/challenges/{slug}/learner` and
`/notes` reveal them.

A content change creates a new immutable version. The content hash includes the
rubric version, so projects keep the version they started with.

Challenges by level:

* **Beginner:** URL shortener, file upload, authentication service, basic booking.
* **Intermediate:** e-commerce checkout, real-time notifications, delivery
  tracking, booking without double reservations.
* **Advanced:** distributed payments, messaging, scalable API architecture, multi-tenant SaaS.
* **Senior:** settlement engine, globally distributed system, zero-downtime
  migration, financial ledger, event-driven recovery.

## AI interviewer (Ollama Cloud through the existing provider layer)

* Uses `app.state.llm`, the same `build_provider(settings)` used by M3 and M5.
  Configure `FORGE_LLM_PROVIDER`, `FORGE_LLM_BASE_URL`, `FORGE_LLM_API_KEY` and
  `FORGE_LLM_MODEL` in `api/.env` (see `docs/interviewer.md`). Keys stay on the
  API server.
* The diagram is validated as a `GraphDocument` and then rendered into a
  compact list of `node:<id> [type] name=…` and `edge:<id> node:a -> node:b via …`
  lines. Nothing else is sent: no ids of other learners, no secrets.
* **Modes:** guided, interview, senior review and failure review. Depth runs
  1–3 and moves up or down from the model's `depth_signal`. The interviewer asks
  exactly one question per turn.
* **Hints:** progressive hints come from the challenge (server-written, labelled
  "Hint n of m"). More than one hint means an evaluation can't count as a success.
* **Injection defence:**
  * All learner content (labels, properties, explanation, ADRs, answers) sits
    inside `<learner_content>`, with delimiters neutralised.
  * The rules say it is data.
  * Instruction-like text sets `injection_suspected`, caps confidence at 0.3
    and blocks mastery eligibility.
  * Labels are NFC-normalised and stripped of control and bidi characters.
* **No answer leaks:** a question or reply sharing a 6-word run with the hidden
  notes is replaced by a neutral question.
* **Failures:** a timeout or other error leaves the learner's message saved and
  posts a system notice. Nothing is invented.

## Evaluation

* There are 12 criteria, each scored 0–2 with evidence that must be a real node
  id, a real edge id or a verbatim quote from the learner's text.
  * Criteria with no verified evidence are `inferred` and score 0 in the total.
  * The model's own total is stored separately.
* Each evaluation records:
  * per-criterion score, evidence and rationale;
  * risks, missing requirements, incorrect assumptions and improvements;
  * follow-up questions and confidence;
  * tokens and attempts;
  * `evaluation_version`, `rubric_version`, the challenge version, the model and
    the architecture version.
  * Approximate cost is `null`, since no pricing data is available.
* Quotes are matched verbatim after folding only typography (curly quotes,
  non-breaking or en/em dashes, NBSP, NFKC); gpt-oss re-types `-` as U+2011.
  Quotes elided with "..." count only if every piece is verbatim, substantive
  and in order. Rejected quotes are kept (`rejected_quote`) and shown to the learner.
* Output budgets per call (2,000 / 6,000 / 3,500 tokens for turn / evaluation /
  drill) because reasoning models spend tokens before the JSON. Under the 1,200
  default, gpt-oss truncated evaluations, which then came back ungraded.
* Output must validate against typed Pydantic schemas and cover all 12 criteria,
  with one repair attempt.
  * Otherwise the evaluation is `ungraded` with an `error_code` and **no score**.
  * A stale `pending` evaluation (older than 10 minutes) is closed as `abandoned`.
* **Rate limit:** `FORGE_DESIGN_LLM_CALLS_PER_HOUR` (default 60) per learner,
  enforced under an advisory lock. It counts messages, evaluations and drills.

## Failure drills (educational)

The 10 scenarios are:

* PostgreSQL down, Redis down, 10× traffic, payment timeout, duplicate delivery;
* worker crash, queue backlog, incompatible schema, region outage, auth overload.

Each drill runs as follows:

1. Snapshot the design.
2. Present the failure.
3. The learner writes the **impact**, then the **mitigation and recovery**.
4. The AI scores impact analysis, mitigation and residual risk (0–2 each,
   verbatim quotes required).
5. It returns gaps, remaining risks and one follow-up question.

FORGE does not simulate infrastructure and never reports latency, throughput or
recovery figures. Ungraded drills can be resubmitted; evaluated ones are final.

## Mastery integration (algorithm `mastery-v1.3`)

* Mastery-eligible design evaluations and failure drills become **unverified
  reasoning** evidence (weight 0.5) on the challenge's primary skill, under the
  documented algorithm (`docs/mastery.md`). Nothing writes mastery directly.
* **Competencies:** the dashboard maps criteria to the 10 competencies. A
  competency is reported as `insufficient_evidence` until it has evaluations
  from at least 2 different challenges.
* **Recommendations:**
  * Retry a challenge whose best score is under 50%.
  * Otherwise pick an unattempted, unlocked challenge at or below the target
    level, preferring rubrics that focus on the learner's weakest criteria.
  * A challenge is unlocked if it is beginner level, or its prerequisite skills
    are mastered, or the learner scored at least 50% one level below.
  * The target level comes from the System Design learning goal.

## API (all under `/api/v1/design`)

Public, read-only, with no hidden content:

* `GET /catalog`: components, protocols, criteria, scenarios and limits.
* `GET /challenges`
* `GET /challenges/{slug}`

Learner routes are local-only and need `X-Learner-Id`. Every lookup filters on
the owner, so another learner's ids return 404.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/status` | provider, model, versions; no keys |
| GET | `/dashboard` | continue, challenges, reviews, weak criteria, competencies, recommendation |
| GET | `/challenges/{slug}/learner`, `/challenges/{slug}/notes` | notes return 403 until the first evaluation |
| POST, GET | `/projects` | create, list |
| GET, PUT | `/projects/{id}` | PUT needs `base_revision`; 409 if stale; graph validated (80 nodes, 160 edges, 200 KB) |
| GET, POST | `/projects/{id}/versions` | list, snapshot |
| GET | `/projects/{id}/versions/{n}` | |
| POST | `/projects/{id}/versions/{n}/restore` | `base_revision` |
| GET | `/projects/{id}/compare?from=&to=` | omit `to` to compare with the current design |
| GET, POST | `/projects/{id}/adrs` | |
| PUT | `/projects/{id}/adrs/{n}` | `base_revision` required; every edit kept |
| GET | `/projects/{id}/adrs/{n}/revisions` | |
| POST, GET | `/projects/{id}/reviews` | start with `mode`, list |
| GET | `/reviews/{id}` | messages and evaluations |
| POST | `/reviews/{id}/messages` | `client_message_id` makes it idempotent |
| POST | `/reviews/{id}/hint` | |
| POST | `/reviews/{id}/evaluate` | snapshots, then evaluates |
| GET | `/evaluations`, `/evaluations/{id}` | history |
| GET, POST | `/projects/{id}/failures` | |
| GET | `/failures/{id}` | |
| POST | `/failures/{id}/respond` | |

## Schema (migration `0005`, additive)

New tables:

* `design_challenges`, `design_challenge_versions`;
* `architecture_projects` (graph JSONB, revision), `architecture_versions`;
* `architecture_decisions`, `adr_revisions`;
* `design_reviews`, `design_review_messages`, `design_evaluations`, `failure_attempts`.

`mastery_evidence` gains `design_challenge_id` and two sources. Its
subject check becomes "exactly one of question, coding challenge, design
challenge". No existing rows change. The downgrade removes only design evidence.

## Manual acceptance test

1. Set `FORGE_LLM_*` for Ollama Cloud in `api/.env`.
2. Run `alembic upgrade head && python -m app.seed`, then start the API and the web app.
3. Open **Design lab**, choose *Design a URL shortener* and read the brief. Press **New design**.
4. Add a client, a backend service, PostgreSQL and Redis, then connect them.
   Set the Redis connection type to *Cache*.
5. Reload the page: the design is still there.
6. **Explain:** write how requests flow and why. Add an ADR.
7. **Versions:** snapshot "Baseline".
8. **AI review:** start *Interview simulation*, answer the question and answer
   a follow-up. Then press **Evaluate design** and inspect the criteria and evidence.
9. **Failure drills:** run *PostgreSQL becomes unavailable* and answer impact
   and mitigation.
10. Improve the design (for example, add a replica or a queue), snapshot it and
    compare v1 with the current design. Evaluate again.
11. Check **Progress**: the skill's evidence lists `design_evaluation` and
    `failure_scenario` as unverified reasoning. The Design lab dashboard shows the
    review history.
