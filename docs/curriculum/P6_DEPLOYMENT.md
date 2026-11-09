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

## November 9 production recheck

The new deployment request assumed that production was still on P5. A live check found the already completed P6 release at `25c4b6ff80b418b298d11f530f582072a240b617`, with all three services active. The historical November 8 record above confirms that P5 was the baseline before that release. **No checkout, seed, migration or application restart was repeated. P7 was not deployed.**

A fresh run of the established `forge-backup.service` succeeded at 10:41 UTC. The encrypted file **`forge-20261109T104123Z.dump.age`**, **620,964 bytes**, has an age v1 header. The off-VM blob returned HTTP 200 on HEAD with the same length; downloading the encrypted object for hashing produced the same SHA-256 as the VM file: `39e4c73faa7110c2a543e3b373afe509be28ac209471c88b6c2fa2dce3642cab`. No decrypted backup or learner rows were exported.

The final consistent, read-only database snapshots match the recorded P6 release exactly: 158 active and zero inactive questions, 35 active lessons, 45 subskills, 112 lesson-check links, 123 resource associations, and schema `0009`. All 60 learner-dependent table fingerprints, protected question/option IDs and contents, mastery evidence, 35 lesson IDs and contents, and existing lesson progress match. Lesson reads remain zero. The ten P6 source hashes match the manifest on the VM. All ten API details and web pages return 200 with the expected check lists and skill/difficulty assessment forms; API health reports `database: ok`. These checks created no learner, assessment or lesson-read event.

The investigation recovered the original lesson-fingerprint formula from the retained Azure release script: it hashes the lesson plus joined skill/topic slugs using Python's datetime/string serialization, excluding `updated_at`. An initial new probe omitted those details. The corrected probe reproduces every recorded hash; the apparent mismatch was in the probe, and no stored content was changed. The service environment was read directly with the settings parser to preserve its JSON values.

All protected configuration hashes and the accepted lockfile metadata difference remain unchanged. Azure infrastructure, Tailscale restrictions, coding-sandbox settings and database architecture were not changed. Detailed current evidence, including the matched per-table fingerprints and backup object verification: [p6-recheck-20261109.json](validation/p6-recheck-20261109.json).
