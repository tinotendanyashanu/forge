# P6 production deployment

Date: 2026-11-08. **Deployed and verified:** `25c4b6ff80b418b298d11f530f582072a240b617`, following explicit user approval. The [validated manifest](validation/p6-manifest.json) is retained unchanged as the preparation record.

All ten lesson files matched their manifest SHA-256 hashes before the release commit and again on the VM after checkout. The 65 pre-existing seed, curriculum and mastery-algorithm files remained byte-identical to the P5 release. No curriculum graph, question bank, mastery rule, service, access-control or coding-sandbox configuration changed.

A read-only probe before the release found production still on P5 commit `f26daf2d8e5f8d6fdec1db8334baeebd5a3ce61c`, with 158 active questions, 25 lessons, 81 lesson-check links, 86 resources, schema `0009`, and the same service and configuration hashes recorded for P5. The only checkout difference was the previously accepted `web/package-lock.json` metadata change.

The fresh encrypted backup **`forge-20261108T161744Z.dump.age`**, 588,727 bytes, was confirmed uploaded before the seed. The guarded release captured consistent read-only database snapshots, briefly stopped the web and API services, checked out P6, ran the established full idempotent seed, compared protected fingerprints, and restarted both services. PostgreSQL remained running. No migration was needed.

| Check | Before | After |
| --- | --- | --- |
| Skills | 15 | 15 |
| Subskills | 45 | 45 |
| Prerequisite edges | 21 | 21, identical fingerprint |
| Active / inactive questions | 158 / 0 | 158 / 0, IDs and semantic contents unchanged |
| Active lessons | 25 | 35 |
| Lesson-check links | 81 | 112 |
| Lesson resources | 86 | 123 |
| Lesson reads | 0 | 0 |

The FK closure from learners covered **60 learner-dependent tables**. All full-row fingerprints, including timestamps, matched before and after seeding. They also matched the fingerprints recorded at the end of the P5 release: there was no learner-history drift between the two releases. Nonempty history remained three learners, three assessment sessions, three answers, three evaluations, two interview sessions with six turns and two evaluations, and the existing mastery and review records. Existing lesson IDs and content were preserved. The ten new lessons added **31** active same-subskill question links.

An independent check after restart confirmed the same counts, production settings, local-only access, sandbox backend disabled, and container-isolation acknowledgment false. Configuration hashes were unchanged. All ten new API lesson details and web lesson pages returned 200, with the manifest titles, check titles and the skill/difficulty assessment launch control present. `/lessons`, the React, FastAPI, testing, security, Git and Linux track pages, and `/health` returned 200. These were read-only checks. No synthetic production learner or assessment was created.

`forge-api`, `forge-web` and PostgreSQL were active afterward. No networking, Tailscale, sandbox or database-architecture setting was changed.

The production checkout's pre-existing `web/package-lock.json` change remains root package version and license metadata only. No frontend source changed, so the existing web bundle was retained.

Detailed evidence: [p6-deployment.json](validation/p6-deployment.json).
