# P6 independent advisory review

Date: 2026-11-08. Reviewer: **gpt-oss:120b**, distinct from the authoring model, using the existing configured provider. Only the ten lesson drafts were submitted; no learner data, credentials, production snapshots or release configuration was included.

Ten valid reviews were retained. All returned `ready: true`, with **56 findings: 4 labeled error, 13 important and 39 suggestion**. These labels are advisory judgments, not verified defects. One malformed async-handler response was discarded and that lesson was successfully reviewed again. The exact retained findings, draft input hashes and a disposition for every finding are in [p6-review.json](validation/p6-review.json). Final lesson hashes appear separately in [p6-manifest.json](validation/p6-manifest.json).

No confirmed blocking technical defect remains. The drafts were refined after review and every changed executable example was rerun. **No lesson is human-verified.** This review does not demonstrate learner transfer or retention.

## Consequential disagreements

- **React version.** Both React reviews claimed React 19 had not been released and requested a downgrade to 18. The repository actually has React/ReactDOM **19.3.0**, and the current [official React documentation](https://react.dev/learn/rendering-lists) identifies that version. All React examples ran against those installed packages in Chromium. The inaccurate downgrade was rejected.
- **FastAPI dependency scope.** The reviewer denied that function/request dependency scopes exist. FastAPI **0.162.0** exposes a scope parameter, and its [official yield-dependency guide](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope) documents both scopes and their cleanup timing. The lesson's version-sensitive explanation is retained. The reviewer's unsupported historical cutoff was not substituted for the documentation.
- **Directory read versus search.** The Linux reviewer claimed directory enumeration always needs execute permission. The unprivileged Linux example enumerates `note.txt` at directory mode **600** but cannot open the named leaf until search permission is restored. At mode **100**, it can open a known readable leaf but cannot enumerate names. Listing names and looking up/statting those names are different operations; [path_resolution](https://man7.org/linux/man-pages/man7/path_resolution.7.html) and the executed probe support the distinction. The example was expanded to show both results explicitly.
- **Live thread identifiers.** The async reviewer worried that the worker could reuse the event-loop thread's ID. [Python documents recycling after a thread exits](https://docs.python.org/3.12/library/threading.html#threading.get_ident); the loop thread remains alive during this probe. The measured sync route runs on another live thread. The suggested private loop attribute and nested unawaited offload call were not added.
- **Git hash flag.** A suggestion used a nonexistent `git init --hash` spelling and proposed an absolute restriction not required by the lesson. The [official init option is object-format](https://git-scm.com/docs/git-init#Documentation/git-init.txt---object-formatltformatgt). The lesson already avoids assuming a fixed object-ID format; no unsupported command was added.
- **FORGE context and misconceptions.** Several findings treated real lesson slugs or assessment IDs as placeholders. All prerequisites resolve in FORGE, and all 31 new check links match the exact skill/topic. The existing UI renders titles and explicitly labels the false metadata statements as “Misconceptions to avoid”; replacing those statements with truths would invert that purpose. No invented CLI commands or pytest markers were introduced to satisfy the review.

## Improvements incorporated

- Removed unnecessary TypeScript prerequisites from the plain-JavaScript list lesson and Python security lab; retained optional conceptual cross-references.
- Clarified that the list example correctly copies before reversing, and staged the injection lesson's SSRF/rich-text material as extensions.
- Restored the previous dependency-override mapping after the lab request, preserving unrelated or pre-existing overrides; clarified sub-dependency cache settings and recorded actual framework versions.
- Removed unnecessary function-level spec_set usage, explained the alternate module-import lookup path, and supplied an exchange-rate adapter interface for the exercise.
- Explained that hash-seed variation does not change dictionary insertion-order guarantees, and showed how sorting test results can hide a required-order defect.
- Made PostgreSQL driver placeholder styles explicit and corrected the injection exercise's already-present second tenant to a third-tenant extension.
- Added an explicit allowlist-based safe configuration export, permitted-process environment inspection, and a decoded token byte-count check. The check does not claim to measure randomness quality.
- Stated Git's minimum version for initial-branch and explained the tracking assertion's exit behavior.
- Added actual directory enumeration at mode 600 to resolve the Linux disagreement experimentally.

## Limits and deferred suggestions

Optional additions such as another memoization example, a second async dependency implementation, additional test-library scaffolding, a monotonic variant of the complete datetime cache, and an untracking lab were deferred to keep each lesson focused. Their underlying concepts are described and linked to authoritative references. The retained JSON explains each decision individually, including suggestions already addressed by the original text.

The review's 40-token observation is explicitly a measured/configurable framework default, not a language guarantee. Security examples do not probe deployed endpoints or networks: SQLite is in memory; credentials are dummy fixtures; Linux/security code runs without network, host mounts or capabilities in bounded unprivileged containers. The application's production coding sandbox remains disabled.
