# FORGE Career: senior engineer readiness (Milestone 8)

FORGE Career answers one question: **what can this learner demonstrably do,
measured against a versioned engineering competency framework?** It composes
the existing modules into assessments: AI interviews (M3), the verified coding
sandbox (M5), the system design lab (M6) and FORGE OPS incidents (M7). It adds
engineering-judgment scenarios and take-home projects.

The readiness engine is explainable and gated, and it never averages away a
failure. When the evidence is thin, it says so:

> Insufficient evidence to determine readiness.

FORGE does not issue certificates or employer endorsements, and it does not
claim external accreditation. Every report carries this note: professional
seniority also depends on workplace impact, ownership, collaboration and
sustained responsibility, and FORGE cannot observe any of those.

## Pieces

| Area | Where |
| --- | --- |
| Competency framework: 18 dimensions; 3 tracks × 4 levels; rules and reliability | `api/app/career/content/framework.toml` |
| Judgment scenarios (9), assessment templates (6), take-home projects (6) | `api/app/career/content/{judgment,templates,projects}.toml` |
| Content models, cross-reference validation, digests | `api/app/career/content.py` |
| Versioned content sync (run by the seed loader) | `api/app/career/library.py` |
| Evidence collection and mapping to dimensions | `api/app/career/evidence.py` |
| Readiness engine (pure functions) | `api/app/career/readiness.py` |
| AI reviewer for judgment answers and project write-ups | `api/app/career/reviewer.py` |
| Attempts, sections, timers, finalisation, reports | `api/app/career/service.py` |
| Roadmap generator | `api/app/career/roadmap.py` |
| Job description analysis | `api/app/career/jobs.py` |
| HTTP API | `api/app/api/routes/career.py` |
| Migration | `api/migrations/versions/0007_career_readiness.py` |
| Web | `web/src/app/career/**`, `web/src/components/career/**` |
| Tests | `api/tests/test_career.py` |

## Integrations reused (nothing re-implemented)

| Section kind | Reuses | Evidence produced |
| --- | --- | --- |
| `interview` | M3 `start_interview` (grill mode), with the existing objective grading and AI rubric | `knowledge_objective`, `rubric_ai` |
| `coding` | M5 challenges, run in the verified sandbox worker | `coding_objective` |
| `design` | M6 `create_project`, evaluation, constraint-change drills | `architecture_ai` |
| `incident` | M7 `start_session` (interview mode, fresh scenario state) | `simulation` (deterministic outcome), `architecture_ai` (AI RCA) |
| `judgment` | New: scenarios reviewed by `reviewer.py` through the shared LLM `_call` (validation, repair, quote verification) | `communication_ai` |
| `take_home` | New: project brief and write-up review. Verified only through the project's linked coding challenges | `rubric_ai` |

Also reused:

* the mastery evidence table (M4);
* the shared injection detector (`suspect_prompt_injection`, broadened in this milestone);
* delimiter neutralising;
* the Ollama Cloud provider layer.

Credentials stay server-side in `api/.env`.

**Coding safety.** A coding section calls `execution_status()` first. If the
sandbox is not verified (no live worker heartbeat or no security check), the
section is marked **unavailable** with a reason. The template's critical
coding requirement then registers as a critical failure. Code never runs on
the application host.

## The competency framework

Version `2026.11-1` is stored in `career_content_versions`. Each attempt and
report pins the framework version and digest it used, so old reports stay
reproducible after the framework changes.

**Dimensions (18):**

1. Programming fundamentals
2. Python & backend engineering
3. JavaScript & TypeScript
4. React & Next.js
5. API design
6. Database engineering
7. Concurrency & consistency
8. Testing & software quality
9. Debugging
10. Performance optimisation
11. Security
12. System architecture
13. Distributed systems
14. DevOps & deployment
15. Production reliability
16. Technical communication
17. Code review & maintainability
18. Engineering judgment

Each dimension defines:

* why it matters;
* what is expected for knowledge, implementation, debugging and architecture;
* a description of each level;
* what counts as a critical gap;
* how existing FORGE evidence maps to it: skills, coding areas, design and incident competencies, judgment tags, critical incident mistakes.

**Tracks:** Full-Stack, Backend and Frontend. **Levels:** Foundation, Junior,
Mid-Level and Senior. Each track level has **gates** (must be met) and
**required** dimensions (gaps are reported but do not block).

Full-Stack Mid-Level, the first track built end to end:

* **Gates:** Python/backend (mid), React/Next.js (mid), API design (mid), database (mid), debugging (mid), testing (junior), security (junior).
* **Required:** JS/TS (mid); concurrency, performance, architecture, reliability, DevOps, communication and code review (junior).

## Scoring methodology

### 1. Evidence

Each item has a kind, a score in [0, 1], a difficulty, a timestamp, a session
and a set of dimensions. Reliability by kind:

| Kind | Reliability | Source |
| --- | --- | --- |
| `coding_objective` | 1.0 | hidden tests run in the verified sandbox |
| `simulation` | 1.0 | deterministic FORGE OPS outcome |
| `knowledge_objective` | 1.0 | deterministically graded questions |
| `rubric_ai`, `architecture_ai`, `communication_ai` | 0.5 | AI evaluations (advisory) |
| `self_report` | 0 | profile experience, shown as context only |

AI evaluations count as evidence only when they meet all three conditions:

* the model returned a valid response;
* confidence ≥ 0.6;
* every quoted point is found verbatim in the learner's answer.

When injection is suspected, confidence is capped at 0.3, so the evaluation is
excluded. When the model fails, the item is marked **ungraded** and the
learner may resubmit. No score is invented.

### 2. Dimension level

A level is met when **fresh** evidence (≤ 365 days old) at that level's
difficulty or harder passes every check below. Junior uses beginner evidence,
mid uses intermediate and senior uses advanced.

| Rule | Junior | Mid | Senior |
| --- | --- | --- | --- |
| Reliability-weighted mean | ≥ 70% | ≥ 70% | ≥ 70% |
| Total reliability weight | ≥ 1.5 | ≥ 2.0 | ≥ 2.5 |
| Independent sessions | 1 | 2 | 2 |
| Verified item, where the dimension is verifiable | n/a | required | required |
| Explained-reasoning item (AI-evaluated) | n/a | n/a | required |

**Foundation** needs a mean of at least 50% with weight 1.0 on any evidence.

Levels are contiguous. When a level is unmet, the reasons are listed, for
example "needs verified evidence".

A **demonstrated weakness** is weight ≥ 1.0 with a mean below 40%.

### 3. Track level: gates, no averaging

| Status | When |
| --- | --- |
| `insufficient_evidence` | Any gate has no fresh evidence, or under 60% of benchmark dimensions have evidence. Displays *Insufficient evidence to determine readiness.* |
| `ready` | Every gate and every required dimension is met. |
| `ready_with_gaps` | Every gate is met; some required dimensions are not. |
| `not_ready` | Some gate is unmet. |

A gate becomes a **critical gap** in either case:

* it shows a demonstrated weakness;
* an incident included an action that the scenario version rates harmful, and that action is listed in the dimension's `critical_mistakes`.

The **demonstrated level** is the highest ready level that is not contradicted
by a lower `not_ready` level. A lower level that is only missing evidence does
not block a higher one.

**Senior** additionally requires breadth across:

* architecture;
* implementation;
* production reasoning;
* security;
* reliability;
* communication;
* judgment.

### 4. Confidence

| Confidence | Requires |
| --- | --- |
| High | coverage ≥ 85%, verified share ≥ 50%, and at least 12 fresh items |
| Medium | coverage ≥ 60% and at least 6 items |
| Low | anything less |

Reports also list:

* dimensions supported only by AI judgments;
* stale evidence;
* the seniority note.

### Formal vs practice

**Formal attempts:**

* follow the template exactly;
* run on a server-authoritative deadline. `started_at + time_limit` is stored, every write calls `ensure_open`, and an expired attempt is auto-finalised. Refreshing the page or changing the client clock has no effect;
* allow one response per item;
* withhold scores and feedback until finalisation;
* snapshot the report. Repeated questions or scenarios are flagged.

**Practice** (diagnostic and job-targeted) attempts are untimed. Ordinary
module practice outside an attempt also feeds readiness through mastery
evidence, marked `context = practice`.

## API

Public routes, read-only content:

* `GET /career/framework` (includes `assessment_coverage`)
* `GET /career/templates`
* `GET /career/templates/{slug}`
* `GET /career/projects`

Local-only routes, which require `X-Learner-Id`. Each object is checked
against its owner and returns 404 otherwise.

| Method & path | Purpose |
| --- | --- |
| `GET/PUT /career/profile` | Target track, level and goal; self-reported experience (context only) |
| `GET /career/dashboard?track&level` | Live readiness and recent reports |
| `POST /career/snapshots` | Save a readiness snapshot report |
| `GET/POST /career/attempts` | List attempts, or create one (resumes an open attempt for the same template; `client_id` idempotent) |
| `GET /career/attempts/{id}` | Attempt state with server time and deadline (auto-finalises if expired) |
| `POST /career/attempts/{id}/start` | Start the clock (idempotent) |
| `POST /career/attempts/{id}/sections/{key}/start` | Provision the section through the owning module |
| `POST /career/attempts/{id}/sections/{key}/responses` | Submit a judgment or project answer (idempotent `client_id`; rate-limited) |
| `POST /career/attempts/{id}/sections/{key}/complete` | Close the section and compute its result from evidence inside the attempt window |
| `POST /career/attempts/{id}/finalize` | Finalise (idempotent) and write the report |
| `POST /career/attempts/{id}/abandon` | Abandon |
| `GET /career/reports`, `GET /career/reports/{id}` | Reports |
| `GET /career/reports/{id}/compare?with={id}` | Per-dimension before and after |
| `GET /career/roadmap` | Latest roadmap (404 if none) |
| `POST /career/roadmap` | Snapshot readiness and build a roadmap |
| `POST /career/jobs`, `GET /career/jobs`, `GET /career/jobs/{id}` | Job description analysis |
| `POST /career/jobs/{id}/assessment` | Create a targeted practice assessment from the gaps |

AI calls are limited to `career_llm_calls_per_hour` (default 40) per learner.
The limit is enforced with an advisory lock and returns 429 when exceeded.

### Job descriptions

Pasted text is treated as **untrusted data**:

* size-limited;
* delimiter-neutralised;
* never followed as instructions;
* scanned for injection, which only raises a flag.

Requirements are extracted by keyword rules, plus an optional AI pass that may
only return known dimension keys. Each requirement is mapped as one of:

* **match**: demonstrated at the inferred seniority;
* **gap**: evidence exists but falls short;
* **untested**: no evidence.

The mapping comes from the learner's own evidence, never from the job text.
FORGE does not scrape employer sites or submit applications.

## Migration

`0007_career_readiness` creates these tables:

* `career_profiles`
* `career_content_versions` (versioned framework, templates, judgment, projects)
* `career_attempts`
* `career_sections`
* `career_responses`
* `career_reports`
* `career_jobs`
* `career_roadmaps`

Constraints:

* unique idempotency keys;
* at most one response per item;
* CHECK constraints on status and kind.

The migration cycles cleanly: `alembic downgrade -1 && alembic upgrade head`.
`alembic check` shows no drift.

## UI routes

| Route | Content |
| --- | --- |
| `/career` | Dashboard: readiness headline, benchmark gates, competency matrix, recent reports |
| `/career/assessments` | Templates (formal and practice) |
| `/career/assessments/[slug]` | Template intro: sections, objectives, time limit, rules |
| `/career/attempts/[id]` | Workspace: server-offset countdown, section navigation, embedded module links, judgment and project editors with local drafts, two-step finalise |
| `/career/reports/[id]` | Printable report with an optional comparison; PDF through the browser's Print → Save as PDF |
| `/career/roadmap` | Prioritised roadmap with activities and completion criteria |
| `/career/jobs`, `/career/jobs/[id]` | Job matcher and results |
| `/career/framework` | Public framework browser, showing which dimensions each assessment covers |

## Test results

* `pytest`: all suites pass with the mock LLM. `tests/test_career.py` has 17 tests:
  * pure readiness rules (gating, no averaging, insufficient evidence, senior breadth, freshness);
  * a full Full-Stack Mid journey through the real M3, M6 and M7 APIs;
  * the server-authoritative time limit;
  * AI failure leading to ungraded and resubmit;
  * injection handling;
  * privacy and ownership;
  * historical framework versions;
  * job mapping and targeted assessments;
  * verified-sandbox coding;
  * mastery feeding readiness;
  * the public framework.
* The sandbox suite (`tests/test_coding_sandbox.py`) runs separately because it needs Docker.
* `alembic check` (no drift), `tsc --noEmit`, `eslint` and `next build` are clean. Totals: 332 API tests and 11 sandbox tests pass.

**Live acceptance** used Ollama Cloud (`gpt-oss:120b`) and the verified Docker
sandbox, on a formal Full-Stack Mid attempt:

* **Interview:** 83% and 100%.
* **Coding:** 8/8, 9/9 and 2/5.
* **Design:** evaluation 0.79; 10× traffic drill 0.83.
* **Incident:** outcome 1.0, decisions 1.0, RCA 0.63. Flagged as a repeated scenario.
* **Judgment:** two answers, with feedback withheld until finalisation.
* **Timer:** refreshing kept the deadline.
* **Report:** honestly showed *Insufficient evidence*. Foundation was demonstrated, and Database engineering was a critical gap. The frontend interview had been skipped.
* **Roadmap:** solving the recommended atomic-transfer challenge (5/5), then rebuilding, moved Database engineering from "Not demonstrated" to Foundation in the comparison.
* **Job matcher:** an embedded "ignore your instructions" line did not change any status, and it is now flagged.

## Incomplete or limited

* **No authentication.** The local single-user restriction from earlier milestones still applies: local-only routes use `X-Learner-Id`, so do not expose the API publicly.
* **M3 grill reveals answers.** Grill mode shows the reference explanation after each graded question, even in formal attempts. The formal score is still computed server-side, but that feedback is not withheld.
* **Small question and scenario banks.** Repeats happen; they are flagged on the report, not prevented.
* **Judgment evidence stays in career tables.** It feeds readiness but is not written into mastery.
* **Take-home projects are not repository-verified.** FORGE does not clone or run learner repositories. Only the linked sandbox challenges are verified, and the write-up is AI-reviewed and advisory.
* **PDF** comes only from browser print. No server-side renderer is bundled.
* **Tracks beyond Full-Stack Mid** (Backend and Frontend Mid, Junior, Senior) have templates and benchmarks, but they were exercised only in tests, not live.
* **Mobile layout** was not visually verified.

## Manual testing

1. Run `docker compose up -d db`, then `cd api && alembic upgrade head && python -m app.seed`. Seeding syncs the career content.
2. Start the API (`uvicorn app.main:app --port 8010`) and the sandbox worker (`python -m app.coding.worker`). Start the web app (`cd web && npm run dev`).
3. Set `FORGE_LLM_*` in `api/.env` for Ollama Cloud.
4. Open `/career/framework` and check the 18 dimensions and the Full-Stack Mid gates.
5. On `/career`, set the target to Full-Stack, Mid-Level. With no evidence, the dashboard shows *Insufficient evidence to determine readiness.*
6. Open `/career/assessments/fullstack-mid` and start the formal attempt. Note the deadline, refresh the page and confirm the timer continues.
7. Work through each section in turn: interview, coding (sandbox must be verified, otherwise the section shows as unavailable), design and drill, incident, and judgment. Complete each section.
8. Finalise in two steps. Open the report and check:
   * gates;
   * critical gaps with reasons;
   * evidence summary;
   * limitations and the seniority note.
9. Use **Print** to save a PDF.
10. On `/career/roadmap`, build the roadmap, do one recommended activity, rebuild it, and compare the two reports.
11. On `/career/jobs`, paste a job description that includes an injection line. Check that it is flagged and the statuses are unaffected. Create the targeted practice assessment.
