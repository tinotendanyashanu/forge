# FORGE OPS: production engineering simulator (Milestone 7)

Learners work realistic incidents. They inspect logs, metrics, traces,
deployments and diagnostics; record hypotheses; take investigation and
mitigation actions; verify recovery; write a root-cause analysis and a
blameless postmortem.

Two kinds of grading are kept separate:

* **Verified outcome:** graded deterministically by the scenario's rules.
* **AI incident commander:** challenges the reasoning, and its reviews are advisory.

**Everything is simulated.** No endpoint runs commands, touches infrastructure
or uses real credentials. The console is a strict allowlist of read-only
queries over scenario data.

## Pieces

| Area | Where |
| --- | --- |
| Scenario schema and validation (seed time) | `api/app/ops/scenario.py` |
| Rubric, mistake catalog, postmortem sections, modes | `api/app/ops/catalog.py` |
| Deterministic engine (state machine, metrics, visibility, scoring, console parser) | `api/app/ops/engine.py` |
| Scenario library (8 TOML files) and seeding | `api/app/ops/scenarios/`, `api/app/ops/library.py` |
| AI commander and reviewers | `api/app/ops/commander.py` |
| Sessions, audit, evidence, resolution, postmortems, replay, dashboard | `api/app/ops/service.py` |
| HTTP API | `api/app/api/routes/ops.py` |
| Migration | `api/migrations/versions/0006_production_engineering_simulator.py` |
| Web | `web/src/app/ops/**`, `web/src/components/ops/**` |

## Incident library

| Level | Scenario | Teaches |
| --- | --- | --- |
| Beginner | `postgres-pool-exhaustion` | Connection leak vs load; pg_stat_activity; flag vs rollback |
| Beginner | `fastapi-500-after-deploy` | ResponseValidationError from a response-model / data mismatch |
| Intermediate | `redis-outage-latency` | TTL-less keys, OOM kills, cold-cache stampede |
| Intermediate | `memory-leak-crashes` | Unbounded in-process cache; heap profiles; stopgaps vs fixes |
| Advanced | `payment-timeout-duplicates` | Non-idempotent retries on timeouts; retry amplification |
| Advanced | `worker-queue-backlog` | Poison messages, infinite requeue, dead-letter queues |
| Senior | `zero-downtime-migration` | Contract migration before old readers retire; expand/contract |
| Senior | `auth-abuse` | Rate limits lost in a gateway migration; credential stuffing; injected log text |

Each scenario defines:

* the business context, services and dependencies;
* initial symptoms and customer impact;
* the condition model and its metrics (pre-incident history included);
* logs, traces, deployments and diagnostic artifacts, each available always or only after a specific action;
* investigation and mitigation actions, with preconditions, discovery rules, transitions and outcomes;
* learner-facing symptoms for every condition, and spoiler terms for the commander;
* the rubric focus, skills, competencies and learning outcomes.

These parts stay hidden until the attempt ends:

* root-cause candidates (one correct), with explanations;
* key evidence, contributing factors and misleading signals;
* the investigation path, the explanation and prevention steps;
* each action's quality, mistake tag and teaching note.

Validation at load time rejects unknown references, a missing correct root
cause or correct mitigation, unknown competencies, and console commands outside
the allowlist. A content change creates a new immutable version (the hash
includes the rubric version). Sessions keep the version they started with.

## Engine (deterministic, server-authoritative)

* **State:** `{status, condition, minute, history[(minute, condition)], performed[(action, minute)]}`.
* **Statuses:** created → investigating (first action) → mitigating (first
  mitigation) → monitoring (the condition starts recovering) → resolved (recovery
  verified, root-cause analysis submitted) → postmortem. Also `abandoned` (End
  attempt). If the condition regresses, monitoring goes back to mitigating.
* **Actions** take simulated minutes. Conditions can auto-transition after N
  minutes (for example, a restart buys time and then the leak resumes).
* **Rejected actions** (closed incident, repeated one-time action, unmet
  preconditions) are recorded in the audit log and never applied.
* **Metrics:** every point is `f(scenario model, condition timeline, minute)`.
  The model forms are constant, linear, sawtooth and ramp, with jitter from a
  hash of `(slug, series, minute)`. The same state always renders the same
  numbers, and nothing is invented at runtime.
* **Recovery verification:** the condition must be in the `recovered` phase for
  at least `verify_minutes`.
* **Verified outcome**, graded on both the final answer and the decisions made
  along the way (weights 0.30 / 0.20 / 0.20 / 0.20 / 0.10):
  * root cause chosen correctly (final answer);
  * key evidence pinned;
  * safety (−0.5 for each harmful action, −0.15 for each risky one);
  * **decision quality**, the mean of:
    * *diagnosed first*: the share of mitigations made after a useful investigation;
    * *mitigation precision*: correct or helpful changes score 1, changes with no
      real effect or only temporary relief 0.5, risky or harmful ones 0, so trial
      and error lowers it even when the incident is eventually fixed;
    * *investigation focus*: useful checks score 1, low-yield ones 0.5 (ruling
      things out is legitimate but costs time);
  * efficiency (minutes to the recovery that lasted, against the target).

  Success means the right root cause, recovered, no harmful actions and a score
  of at least 0.7. The result includes a chronological **decision review** (each
  decision's assessment and teaching note) and **flags** such as "changed the
  system before any useful investigation" or "trial and error". The AI root-cause
  reviewer receives this verified sequence so its efficiency and safety judgements
  are grounded in it.

## Investigating without knowing the answer

* **Symptoms, not diagnoses:** while an attempt is open, the status line and the
  condition timeline show symptom text only, as monitoring would show it (each
  condition has an authored `symptom`). Internal condition names and descriptions
  appear only in the debrief and in the post-incident replay.
* **Discoverable fixes:** targeted mitigations, such as a specific flag, a hotfix
  or a dead-letter policy, are hidden and rejected as "Unknown action" until an
  investigation that would reveal them has been done (`discovered_by`). Generic
  options (rollback, restart, scale, throttle) are always available, and so are
  some tempting but harmful ones. Their immediate outcomes describe only what
  you'd observe; the explanations come in the debrief.
* **Shuffled options:** root-cause options are shuffled per attempt.
* **Commander replies are withheld** if they:
  * share a 6-word run with the root-cause text;
  * use a distinctive root-cause phrase the learner hasn't seen yet;
  * use an authored `spoiler_term` (for example "unbounded" or "idle in transaction")
    before it appears in evidence the learner has unlocked, in any UI text they can
    see, or in their own writing.

  The learner is told the reply was withheld; it is never silently rewritten.
* **Console:** the allowlist is `logs`, `metrics`, `traces`, `deployments`,
  `service-status` and `database-status`. Arguments are parsed with `shlex`, only
  known flags are accepted, and values are regex-checked. `database-status` runs
  the scenario's mapped investigation action.

## AI incident commander (Ollama Cloud via the existing provider)

* **Inputs:** the backend supplies everything the model sees:
  * the brief;
  * the authoritative state and metric values computed by the engine;
  * the evidence the learner has unlocked, as one-line summaries;
  * the full content of pinned evidence;
  * the audit trail, hypotheses, notes and conversation.
* **Untrusted data:** evidence (which can contain attacker-controlled strings,
  see `auth-abuse`) and learner text are delimited as
  `<simulated_evidence>` / `<learner_content>`, and the delimiters are
  neutralised in the content.
* **Root-cause protection:** the root cause sits in confidential reviewer notes
  marked `DO NOT REVEAL` until the attempt ends. Replies sharing a 6-word run
  with the root-cause text are replaced.
* **Cited evidence:** filtered to ids the learner can see.
* **Modes:** guided investigation, production interview, senior incident
  commander, postmortem review.
* **Root-cause review:** 8 criteria, each 0–2:
  * diagnostic accuracy, evidence quality, troubleshooting efficiency, safety of mitigation;
  * technical reasoning, reliability awareness, communication, long-term prevention.

  Each needs a visible evidence id or an exact quote. Field labels the prompt
  showed are stripped, and the remaining pieces must be verbatim and in order.
* **Postmortem review:** summary, gaps, blameless issues and 1–3 follow-up
  questions. It is never scored.
* **Failures:** model failures are recorded as ungraded with an `error_code`, and
  reviews can be retried.
* **Usage tracking:** token counts are kept; approximate cost is `null` because
  there is no pricing data.
* **Rate limit:** `FORGE_OPS_LLM_CALLS_PER_HOUR` per learner (default 60), under
  an advisory lock.

## Mastery (`mastery-v1.4`)

* **Resolved attempts:** become `incident_simulation` evidence, **verified**, in
  the `practical` dimension, with score = the outcome score. It goes to the
  scenario's primary skill.
* **AI root-cause reviews:** eligible ones (validated output, evidence, confidence
  of at least 0.6, no suspected injection) become `incident_review` evidence,
  **unverified** (weight 0.5), in the `debugging` dimension.
* **Abandoned attempts:** produce no evidence.
* **Levels:** still need the engine's diverse-evidence rules (2+ sessions and
  2+ subjects), so one incident never awards mastery.
* **Competencies:** reported only after verified outcomes from 2 different scenarios.
* **Recommendations:**
  * Retry any scenario with a best outcome under 50%.
  * Otherwise suggest an unlocked scenario that practises the skills tied to
    recurring mistakes (the catalog's remediation lessons link to skill tracks).
  * Otherwise suggest the next level.

## API (all under `/api/v1/ops`)

The public endpoints (no hidden content) are `GET /catalog`, `GET /scenarios`
and `GET /scenarios/{slug}`.

Learner routes are local-only, need `X-Learner-Id`, and are scoped to the owner
(other learners' sessions return 404). State-changing calls carry a
`client_action_id` or `client_message_id` (idempotent), lock the session row,
and write an audit entry and a snapshot.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/status`, `/dashboard`, `/sessions` | provider info (no keys), dashboard, history |
| POST | `/sessions` | `{scenario, mode, fresh}`; resumes an open attempt unless `fresh` |
| GET | `/sessions/{id}` | state, health, metric values, actions with availability, pins, hypotheses; root-cause options from monitoring; outcome and debrief after the end |
| POST | `/sessions/{id}/actions` | `{action_id, client_action_id}` |
| POST | `/sessions/{id}/commands` | allowlisted console |
| GET | `/sessions/{id}/logs?service&level&request_id&search&since&until` | |
| GET | `/sessions/{id}/metrics?keys&window`, `/traces`, `/deployments`, `/artifacts` | only what the learner has unlocked |
| POST | `/sessions/{id}/evidence` | pin or unpin visible evidence |
| POST | `/sessions/{id}/hypotheses` | |
| PUT | `/sessions/{id}/hypotheses/{n}` | |
| PUT | `/sessions/{id}/notes` | |
| GET, POST | `/sessions/{id}/messages` | AI commander |
| POST | `/sessions/{id}/resolve` | root-cause analysis + `client_action_id`; requires verified recovery |
| POST | `/sessions/{id}/review` | retry an ungraded AI review |
| GET | `/sessions/{id}/evaluations` | |
| POST | `/sessions/{id}/abandon`, `/sessions/{id}/reset` | reset ends the attempt (kept in history) and starts fresh |
| GET | `/sessions/{id}/replay?seq=` | audit log plus the state and metrics at any snapshot |
| GET, PUT | `/sessions/{id}/postmortem` | autosave with `base_revision` → 409 on conflict |
| GET | `/sessions/{id}/postmortem/revisions`, `/export` | the export is `text/markdown` |
| POST | `/sessions/{id}/postmortem/review` | |

## Schema (migration `0006`, additive)

New tables:

* `incident_scenarios`, `incident_scenario_versions`;
* `incident_sessions` (state JSONB, verified outcome);
* `incident_actions` (audit), `incident_snapshots`;
* `incident_evidence` (pins), `incident_hypotheses`;
* `incident_messages`, `incident_rcas`, `incident_evaluations`;
* `postmortems`, `postmortem_revisions`.

`mastery_evidence` gains `incident_scenario_id` and two sources. The
verified-source check now includes `incident_simulation`. No existing rows
change; the downgrade deletes only incident evidence.

## Manual test

1. Set `FORGE_LLM_*` (Ollama Cloud) in `api/.env`, then run
   `alembic upgrade head && python -m app.seed`. Start the API and the web app.
2. Open **FORGE OPS**, open the *Checkout requests hang* briefing and start in
   commander mode.
3. **Overview:** look at the latency pinned near 30 s and the low database
   latency. **Logs:** filter by level error, click `request_id=r-93f2`, open its
   trace, and pin the pool-timeout log.
4. **Notebook:** record a hypothesis. **AI commander:** argue for "database
   overloaded" and see it challenged with the evidence you have.
5. **Actions:** inspect PostgreSQL sessions, then pool stats, then the v3.14.0
   diff, pinning each diagnostic.
6. Try "Rolling restart" first to watch the leak come back, or go straight to
   "Disable feature flag", then the restart.
7. Wait and observe until recovery is verified. Use **Resolve**: choose the
   root cause, write the analysis, and see the verified outcome and the AI
   review side by side.
8. Use **Postmortem**: edit, watch the autosave, ask for the AI review, and
   export Markdown.
9. Check **Progress → DevOps** for the evidence. Back on the FORGE OPS dashboard,
   reopen the incident from history and use **Timeline & replay**.
