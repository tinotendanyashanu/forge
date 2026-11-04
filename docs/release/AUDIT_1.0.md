# FORGE 1.0 release audit (2026-11-04)

What was checked, how, and what was found. Every result below came from a
command or a browser session run during this audit. Nothing is estimated.

## Milestone status

| # | Module | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Foundation (Next.js, FastAPI, PostgreSQL, design system) | **Functional** | Production build; `/health` checks the database; migrations 0001 to 0008 run down and up on every test run |
| 2 | Assessment engine | **Functional** (multiple choice graded). Written answers are saved and **never scored, by design** | Browser: Python beginner diagnostic, correct and incorrect paths, grounded feedback. Misleading "awaiting AI evaluation" copy fixed |
| 3 | AI interviewer (Ollama Cloud) | **Functional** | Real smoke test: answer evaluated in 5.7 s with a targeted follow-up. Fake-provider tests cover malformed output, timeouts and injection. **Per-learner rate limit was missing (fixed)** |
| 4 | Adaptive mastery and spaced repetition | **Functional** | Browser: the learning path updated after diagnosis with explicit missing-evidence reasons. Tests: independence rules, review scheduling, gaps |
| 5 | Coding lab and sandbox | **Functional for local single-user** | Real sandbox: probe checks, hostile-code tests, every challenge verified. Real Ollama review identified both planted bugs. Hostile multi-tenant isolation: **not available** |
| 6 | System design lab | **Functional (fake-provider tested)** | 28 API tests. Not smoke-tested against the real model in this audit |
| 7 | FORGE OPS incidents | **Functional (fake-provider tested)** | 34 tests; deterministic scenario outcomes. Not smoke-tested against the real model in this audit |
| 8 | Career readiness | **Functional** | Browser: a new learner gets "Insufficient evidence to determine readiness" with coverage and confidence. Gates are tested |
| 9 | FORGE Workspace and PR simulator | **Functional** | Full browser journey in M9 with a real sandbox and real Ollama reviews. Three projects verified |

**Content gaps (labelled in the UI, not hidden):** DevOps, Distributed Systems
and Senior Engineering Practices have no assessments. Programming Fundamentals
and Security are assessed only through coding challenges (10 of 13 skills are
assessable). The workspace library has three
projects.

**Missing:**

* authentication;
* browser-automated end-to-end tests (journeys are covered at the API level and were walked manually in Chrome);
* an accessibility audit with assistive technology (only keyboard and semantic checks were done).

## Critical issues found and fixed

| Severity | Issue | Fix |
| --- | --- | --- |
| High | **No spending cap across learners.** Per-learner limits could be bypassed by creating learners, and nothing bounded total model calls | `BudgetedProvider` wraps every real provider: `FORGE_LLM_MAX_CALLS_PER_HOUR` (default 600). Calls over budget fail as `provider_rate_limited`, before reaching the provider, and are never scored |
| High | **AI interviews had no per-learner limit** (every other AI module did) | `FORGE_INTERVIEW_LLM_CALLS_PER_HOUR` (default 60), checked before the answer is stored; returns 429 |
| High | **The web app listened on all interfaces** (`*:3000`). With no login, anyone on the LAN could create learners, run code and spend AI budget; the API's local-only check didn't help because requests are proxied | `dev` and `start` bind to `127.0.0.1` |
| Medium | Unlimited retries of ungraded coding-lab AI reviews | Capped per learner per hour |
| Medium | No request body size limit | ASGI limit (`FORGE_MAX_REQUEST_BYTES`, 2 MB). Checks Content-Length and streamed bytes; returns 413 |
| Medium | Misleading progress: written assessment answers labelled "Awaiting AI evaluation… which isn't available yet", implying they would be scored later | Copy now says they are saved, not scored, and points to the interviewer, which evaluates written answers |
| Low | Missing security headers; `X-Powered-By` exposed | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`; `poweredByHeader: false` |
| Low | Career profile keys not length-limited | Truncated to 64 characters |
| Low | Stale UI and docs text ("Preview build · Milestone 1"; coding-lab doc said no real provider was configured) | Updated |
| Low (from M9) | The workspace reviewer's "proven failure" matching was too strict for real model output | Formatting-tolerant matching that still requires the same words |

## Security review

| Area | Finding |
| --- | --- |
| Authentication | **None.** Anonymous learner per browser: an unguessable UUID in an httpOnly, SameSite=Lax cookie. The API serves learner routes to loopback clients only. Acceptable only for local single-user use |
| Authorization and ownership | Every learner query filters on the owner, and resources owned by others return 404. Tested for assessments, interviews, coding, design, ops, career and workspaces |
| Validation | Pydantic on every request: bounded strings and lists, `extra=forbid`, slug and UUID patterns, plus the body size limit |
| SQL injection | All queries use SQLAlchemy expressions or bound parameters. No string-built SQL found |
| XSS | React escaping throughout. No `dangerouslySetInnerHTML`. Markdown renderers emit text nodes only |
| Prompt injection | Learner text is delimited and neutralised. A shared detector lowers confidence and blocks credit. Quotes must be verbatim. Reference-leak filters run on reviews and follow-ups |
| Secrets | `api/.env` and `web/.env*` are gitignored. The API URL and key are server-side only. `/llm/status` never returns credentials |
| Code execution | Disabled by default. The docker backend needs explicit single-user acknowledgement and a passing in-sandbox self-check, and runs in a separate worker process. **Container isolation only.** Not safe for untrusted multi-tenant code |
| Path traversal | Workspace paths are validated; staging uses `O_NOFOLLOW` and `O_EXCL`; files are mounted read-only. Tested against `..`, absolute paths, dot-files and symlinks |
| Error leakage | Unhandled errors return a generic 500. Domain errors carry user-safe messages. The web error page shows an opaque digest. Hidden test failures are redacted |
| CSRF | Server actions use Next's built-in Origin check. The API is not browser-reachable |
| Not done | Content-Security-Policy (Monaco needs worker and blob allowances; not tuned). Dependency vulnerability scan (`npm audit` / `pip-audit`) not run in this audit |

## Learning quality

* **Content is checked by machine.**
  * Seed and content loaders reject questions without rubrics, misconceptions or resources.
  * Every coding challenge and workspace project is proven in the real sandbox: references pass, starters fail.
  * Targeted wrong solutions fail the intended hidden test.
* **Content spot checks** (by hand):
  * two Python diagnostic questions, mutable defaults and `==` vs `is` (correct);
  * the SQL lost-update interview question and the model's follow-up (correct and on-topic);
  * the merge-intervals review (correctly found both bugs).
* **AI never invents certainty.**
  * Ungraded or invalid output produces no score.
  * Credit needs verified quotes.
  * Tests override model approval.
  * Reviews carry a server-written grounding line with the real test result.
* **Mastery uses only recorded evidence.**
  * Verified evidence (objective answers, sandbox tests, incident outcomes) is weighted 1.0; AI judgments 0.5.
  * Mock or unverified execution is never evidence.
  * Levels need independent sessions and different questions.
* **Career reports name missing evidence.** They show "Insufficient evidence to determine readiness" instead of a guess.
* **The full journey works**, from diagnosis to learning path, practice, interview, review queue and reassessment. It is covered by `tests/test_journeys.py` and was walked in the browser.

## Reliability and performance (measured)

* API latency on the local stack, with a fresh learner, warm process:
  * `career/dashboard` 12 ms;
  * `mastery` 38 ms;
  * `recommendations` 37 ms;
  * `workspace/progress` 15 ms;
  * coding challenges 9 ms;
  * curriculum 11 ms.

  No database bottleneck was found at this scale.
* **`/llm/status` made a live call to Ollama Cloud on every interview page view** (~270 ms). It is now cached for 30 s; warm calls take about 1 ms.
* Real model latency: interview evaluation 5.7 s; coding review 3.4 s. Every call has a 60 s timeout and 2 retries with backoff. Slow calls run outside database transactions.
* Background jobs have:
  * `SKIP LOCKED` claims and leases;
  * fenced completion;
  * unique results per (job, test);
  * infrastructure-only retries.

  Learner-code failures are results, not retries.
* Backup and restore were verified with `pg_dump -Fc` and `pg_restore` into a scratch database: identical counts and migration version.
