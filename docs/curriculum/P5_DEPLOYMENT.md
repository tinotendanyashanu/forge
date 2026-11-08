# P5 production deployment

Date: 2026-11-08. **Deployed and verified:** `f26daf2d8e5f8d6fdec1db8334baeebd5a3ce61c`, following explicit user approval. The [validated manifest](validation/p5-manifest.json) is retained unchanged as the preparation record.

All ten lesson files matched their manifest SHA-256 hashes before commit and again on the VM. All 54 pre-existing seed/curriculum files remained byte-identical to P4. No curriculum, mastery, service, access-control or coding-sandbox configuration changed.

The fresh encrypted backup **`forge-20261108T085914Z.dump.age`**, 555,497 bytes, was confirmed uploaded before the release. The guarded release captured consistent read-only database snapshots, briefly stopped the web/API services to prevent concurrent learner writes, checked out P5, ran the established full idempotent seed, compared protected fingerprints, and restarted both services. PostgreSQL remained running; no migration was needed (0009).

| Check | Before | After |
| --- | --- | --- |
| Skills | 15 | 15 |
| Subskills | 45 | 45 |
| Prerequisite edges | 21 | 21, identical fingerprint |
| Active / inactive questions | 158 / 0 | 158 / 0, IDs and semantic contents unchanged |
| Active lessons | 15 | 25 |
| Lesson-check links | 44 | 81 |
| Lesson resources | 49 | 86 |
| Lesson reads | 0 | 0 |

The FK closure from learners covered **60 learner-dependent tables**. All full-row fingerprints, including timestamps, matched before and after seeding and again after page verification. Nonempty history included three learners, three assessment sessions/answers/evaluations, two interview sessions with six turns and two evaluations, and the existing mastery/review/progress records. Existing lesson IDs and content were also preserved.

All ten new API lesson details and web lesson pages passed. The checks confirmed exact subskill mappings, **37 active same-subskill question associations**, displayed question titles and the correct skill/difficulty assessment launch controls. `/lessons`, the five affected track pages and API health returned 200. These were read-only checks; no synthetic production learner or assessment was created. Assessment execution remains covered by the scratch/API suite.

`forge-api`, `forge-web` and PostgreSQL were active afterward. Effective settings remain production, local-only access, sandbox backend disabled and container-isolation acknowledgment false. Hashes of the API environment, service units, curriculum and mastery algorithm matched. No networking or cost configuration was changed.

The production checkout's pre-existing `web/package-lock.json` change updates root package version/license metadata only. Dependencies are identical; the file was preserved byte for byte. No frontend source changed, so the existing web bundle was retained; its no-store API reads serve the new content after restart.

The first preflight stopped before backup or application changes because its Git-status comparator mishandled leading whitespace. That local release-script check was corrected after inspecting the metadata-only difference. The completed release reported no content, count or preservation mismatch; no production data was altered to force expected values.

Detailed evidence, including before/after fingerprints, configuration hashes, backup confirmation and all ten page results: [p5-deployment.json](validation/p5-deployment.json).
