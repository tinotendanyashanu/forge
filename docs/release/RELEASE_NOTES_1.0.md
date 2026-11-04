# FORGE 1.0 release notes

FORGE 1.0 is a **local, single-user** engineering learning platform. It
measures what you can demonstrate and refuses to guess:

* multiple-choice diagnostics;
* an AI interviewer;
* an adaptive learning path with spaced review;
* a sandboxed coding lab;
* a system design lab;
* production incident simulations;
* engineering projects with simulated pull requests;
* an evidence-backed career readiness report.

## What's in 1.0

* **Assessments.** 40 questions across 8 skills, with rubrics, misconceptions and resources. 10 of the 13 curriculum skills are assessable; Programming Fundamentals and Security only through coding challenges.
* **AI interviewer** (Ollama Cloud or any OpenAI-compatible endpoint). Four modes. Answers get validated, quote-verified evaluations and targeted follow-ups.
* **Adaptive mastery engine** `mastery-v1.5`. Explains what evidence is missing. Includes spaced review, knowledge gaps and goals.
* **Coding lab.** 19 challenges in Python, JavaScript and TypeScript, with hidden tests in a self-verifying container sandbox, and an advisory AI review.
* **System design lab** with an AI architecture review and failure drills.
* **FORGE OPS.** 8 incident scenarios with deterministic outcomes and an AI root-cause-analysis review.
* **FORGE Career.** Versioned competency framework, assessments, roadmap, job description analysis.
* **FORGE Workspace.** Three multi-file projects (FastAPI bug fix, full-stack feature, PostgreSQL concurrency). Browser IDE, simulated PRs, AI senior reviewer in four modes, collaboration exercises.

## Changes in the 1.0 stabilization pass

* Global AI spending cap (`FORGE_LLM_MAX_CALLS_PER_HOUR`) and a per-learner interview limit.
* The web app binds to `127.0.0.1` by default; security headers added.
* Request body size limit (413).
* Coding-lab AI review retries are rate limited.
* Written assessment answers are now labelled honestly as "saved, not scored".
* The provider reachability check is cached, removing a ~270 ms remote call from page loads.
* An API-level end-to-end learner journey test was added.
* Release documentation: `DEPLOYMENT.md`, `AUDIT_1.0.md` and this file.

## Upgrading

Back up the database, then run `alembic upgrade head`, `python -m app.seed` and
`npm run build`. There are no schema changes since Milestone 9 (head is
`0008`). Add the new optional variables from `api/.env.example`.

## Known limitations

* **No authentication.** Identity is an anonymous browser cookie. Don't run FORGE on a shared network or the internet.
* **Code execution uses container isolation** (runc) with explicit single-user acknowledgement. It is not safe for untrusted multi-tenant use; that needs gVisor, Kata or Firecracker.
* **The global AI budget is per API process.** Run one API process.
* **Content coverage.** DevOps, Distributed Systems and Senior Engineering Practices have no assessments. The workspace library has three projects.
* **Written assessment answers are not scored.** Written reasoning is evaluated in the AI interviewer.
* **TypeScript is not type-checked** in the sandbox (types are stripped). React components are not rendered in workspace tests.
* **AI reviews and evaluations are advisory and can be wrong.** They never decide correctness, approval or verified mastery.
* **Leak filters on AI reviews are lexical.** A model can paraphrase a fix.
* **Not done:**
  * browser-automated end-to-end tests;
  * Content-Security-Policy;
  * a dependency vulnerability scan;
  * a screen-reader audit.
* **Real-model smoke tests in this release** covered the interviewer, coding review and workspace reviews. Design-lab, OPS and career AI calls were tested with a fake provider only.
