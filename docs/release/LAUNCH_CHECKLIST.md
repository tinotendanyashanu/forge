# Manual GitHub launch checklist

This is a review checklist, not a statement that the checks have passed. It covers source publication for local use, not public application deployment.

## Identity, rights and policies

- [ ] Confirm the final repository owner/name and project description. Do not imply a hosted service or multi-user support.
- [x] License chosen: MIT. Full text in `LICENSE`; README, CONTRIBUTING and package metadata updated.
- [ ] Enable and verify GitHub private vulnerability reporting, or publish a monitored private security contact. Update `SECURITY.md` to describe the confirmed route.
- [ ] Replace the conduct contact slot in `CODE_OF_CONDUCT.md` with a working private route.

## Documentation and evidence

- [ ] Compare features and counts with `RELEASE_NOTES_1.0.md`; do not expand the launch beyond the supplied report without new evidence.
- [ ] Keep the LOCAL-ONLY warning prominent. Preserve no-authentication, runc isolation and one-API-process limitations.
- [ ] Verify the local setup on a clean copy. Record actual dependency installation, migration, seeding, build and health-check outcomes.
- [ ] Use a disposable test database; record executed tests and skipped checks accurately.
- [ ] Distinguish real-model, fake-provider, mock-execution and real-container validation.
- [ ] Preserve all reported omissions until actually resolved: browser-automated end-to-end testing, CSP, dependency vulnerability scanning and screen-reader audit.
- [x] Real captures replace the screenshot slots (`docs/assets/screenshots/`, 4 Nov 2026). Re-capture if the UI changes; never substitute invented product screens.
- [ ] Check Markdown, image alt text, relative links and mobile readability in GitHub's preview.

## Before the manual push

- [ ] Merge the `.gitignore` rules with existing project rules; preserve lockfiles, migrations and exercise content.
- [ ] Complete `docs/SECRETS_CHECKLIST.md`, including staged files, history and attachments.
- [ ] Review all differences before copying over existing files. Keep preparation notes outside the repository unless intentionally published.
- [ ] Check issue forms and the pull request template after the repository exists.
- [ ] Review the complete staged change and manually push using your own Git workflow.
- [ ] If creating a release, use the actual version/tag and the reviewed release report. No tag, release date or passing CI status is assumed by this package.

## Portfolio presentation

- [ ] Link to the source repository and actual screenshots or a recorded local walkthrough.
- [ ] Describe FORGE as local, single-user and evidence-oriented, with advisory AI.
- [ ] Avoid claims of production readiness, proven hiring outcomes, comprehensive senior-engineer coverage, authentication or secure multi-tenant execution.
- [ ] Do not expose the running application as a public portfolio demo.
