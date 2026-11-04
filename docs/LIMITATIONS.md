# Limitations and release validation

This document preserves the boundaries reported in the user's [FORGE 1.0 release notes](release/RELEASE_NOTES_1.0.md). It is not an independent audit or a promise that later source changes preserve the same behavior.

## Local use and execution

- **No authentication.** Learner identity is an anonymous browser cookie. Use FORGE on one local machine for one learner; do not run it on a shared network or the internet.
- **Container isolation is limited.** The runc execution backend requires an explicit single-user acknowledgement. It is unsuitable for untrusted multi-tenant code execution. The report names gVisor, Kata and Firecracker as stronger isolation options for future work; it does not claim they are implemented.
- **AI limits are per API process.** Run one API process. A call-count setting is not a guarantee of a particular monetary spend.

## Curriculum and evidence

| Area | Reported scope |
| --- | --- |
| Question bank | 40 questions across 8 skills. Do not describe all 40 as multiple-choice questions. |
| Curriculum coverage | 10 of 13 skills are assessable across formats. Programming Fundamentals and Security are assessable only through coding challenges. |
| Missing assessments | DevOps, Distributed Systems and Senior Engineering Practices have no assessments. |
| Workspace library | Three multi-file projects. Simulated pull requests and collaboration exercises do not establish a hosted multi-user collaboration service. |
| Written assessments | Responses are saved, not scored. Written reasoning is evaluated through the AI interviewer. |
| Learner TypeScript | Types are stripped in the sandbox; there is no TypeScript type-checking there. |
| Workspace React | Tests do not render React components. |

The readiness report is evidence-backed learning feedback. The release establishes no hiring guarantee, independent credential or complete coverage of engineering practice.

## AI limits

AI reviews and evaluations are advisory, can be wrong, and never decide correctness, approval or verified mastery. Validating a response or checking a quote does not establish that every model judgment is correct.

Review leak filters are lexical; a model may paraphrase a fix despite filtering. Do not promise solution secrecy or describe advisory reviews as a security boundary.

## Reported validation

| Check | What the release report says |
| --- | --- |
| API-level learner journey | An API-level end-to-end learner journey test was added. |
| Real-model smoke tests | Covered interviewer, coding review and workspace reviews. |
| Design-lab, OPS and career AI | Tested with a fake provider only. Real-model behavior was not established for these calls in the report. |
| Browser-automated end-to-end tests | Not done. |
| Content-Security-Policy | Not done. Other security headers do not imply CSP is present. |
| Dependency vulnerability scan | Not done. Do not claim dependency clearance. |
| Screen-reader audit | Not done. Do not claim accessibility conformance. |

No new application tests, sandbox runs, model calls, dependency scans or audits were executed while preparing this documentation package. Setup commands were checked against local files; successful execution must still be established by the maintainer.

## Contribution opportunities

Additional content, browser coverage, accessibility work, CSP and dependency scanning are useful areas to discuss. They are not promised release dates or capabilities already delivered. Authentication, shared deployment and stronger execution isolation require broader design and review.
