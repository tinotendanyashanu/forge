# Contributing to FORGE

FORGE 1.0 is a local, single-user engineering learning platform. Contributions should preserve honest evidence, clear limits and the local-only safety boundary.

**License:** FORGE is released under the [MIT License](LICENSE). By submitting a contribution, you agree that it is licensed under the same terms. Only contribute material you wrote or have the right to share under MIT, and keep any required third-party notices. There is no separate contributor license agreement or copyright assignment.

## Before you start

Read the [README](README.md), [security policy](SECURITY.md), [limitations](docs/LIMITATIONS.md) and [Code of Conduct](CODE_OF_CONDUCT.md). Follow [DEVELOPMENT.md](docs/DEVELOPMENT.md) for local setup and testing.

For a substantial change, open an issue describing the problem, expected behavior and scope before investing in an implementation. Small documentation fixes can use a focused pull request. There is no promised review or response schedule.

**Security vulnerabilities belong in private reports.** Follow `SECURITY.md`; do not post exploit details, credentials or learner data in public issues.

## Useful contribution areas

- Improve question quality, rubrics, misconceptions and resources, or propose coverage for the currently unassessed skills.
- Add carefully scoped coding challenges, incident scenarios or multi-file projects, with meaningful deterministic checks.
- Add regression coverage, including the reported gap in browser-automated end-to-end testing.
- Improve keyboard and screen-reader accessibility; a screen-reader audit remains outstanding.
- Improve setup instructions, error messages and explanations of learning evidence.
- Propose security improvements through the appropriate reporting route. Public or multi-user support requires a separately reviewed design; it is not an existing 1.0 capability.

These are suggested areas, not assigned tasks or delivery commitments.

## Working on a change

1. Fork or clone the source and create a branch for one coherent change.
2. Keep configuration private. Use sanitized `.env.example` values and keep model keys, database backups and learner histories out of commits.
3. Make the smallest change that solves the problem. Explain any change to evidence, scoring, execution or AI behavior.
4. Run checks appropriate to the affected area using `docs/DEVELOPMENT.md`. Report the exact commands, outcomes and skipped checks.
5. Update relevant documentation and open a pull request using the provided template.

## Behavioral expectations

- Preserve the distinction between deterministic results and advisory AI feedback. Do not treat model approval as test correctness or verified mastery.
- Do not label a saved written assessment answer as scored unless that behavior has actually been implemented and validated.
- Keep one-API-process assumptions, loopback bindings and execution acknowledgements visible.
- Do not weaken sandbox verification or silently count mock execution as evidence.
- Do not claim TypeScript type-checking or rendered React testing where the existing sandbox does not provide it.

## Curriculum and exercise changes

Explain the skill, difficulty, learning objective and misconception the material addresses. Include a reasoned expected answer and useful resources. Use original material or material you have permission to contribute, and retain necessary attribution.

For coding and workspace content, verify that reference solutions pass and starter implementations fail at least one hidden check. The real-container verification commands are in `docs/DEVELOPMENT.md`; they execute code in Docker containers even if the normal sandbox setting is disabled.

Treat hidden tests as part of local assessment behavior, not as a secrecy guarantee for an open-source repository. Avoid exposing answers in user-facing hints or advisory reviews.

## Testing and review

Use a disposable test database distinct from your learner database: the API test suite resets the configured test database. Never point `FORGE_TEST_DATABASE_URL` at data you need to keep.

A useful pull request explains the problem and resulting behavior, includes relevant validation, and states remaining uncertainty. Identify fake-provider tests, real-model checks, mock execution and real-container checks accurately. For visible UI changes, include actual sanitized captures and short captions; screenshots alone do not establish functional correctness.

The maintainer may request changes, narrow scope or decline a proposal. Code acceptance does not imply a support commitment or permission to expose FORGE as a public service.
