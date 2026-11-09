# P7 independent advisory review

Date: 2026-11-08. Reviewer: **gpt-oss:120b**, using the existing configured provider. Only the ten lesson drafts were submitted. No learner data, credentials, production snapshots, or release configuration was included.

Ten reviews were retained. All returned `ready: true`, with **50 findings: 9 labeled error, 9 important, and 32 suggestion**. These labels are the model's judgments. One scaling response was malformed JSON, discarded, and that lesson was reviewed again successfully. Draft hashes, every finding, and a disposition are in [p7-review.json](validation/p7-review.json). Final hashes are in [p7-manifest.json](validation/p7-manifest.json).

**No lesson is human-verified.** Two findings asked the provenance line to claim subject-matter expert sign-off. Those were rejected. Advisory review does not change `reviewed` into `verified`.

## Disagreements kept because of a run or a manual

- **CPython 3.14.** Seven findings said 3.14 does not exist and asked for 3.12 or 3.13. The examples ran on **CPython 3.14.7** on 2026-11-08. The version string stays.
- **Shell-form SIGTERM.** The container review said `/bin/sh` would exit and the sample should print `shell_state exited`. On Docker **29.8.1** and `python:3.12-slim`, SIGTERM left that container **running** 0.8 seconds later, and the Python handler did not print. The text fence keeps `shell_state running` and `shell_signal absent`. The lesson does not claim this is every init system or a full stop-grace measurement.
- **Bash guard status.** The shell review said `bash -c` still returns 1, and that 127 means command-not-found. On **Bash 3.2.57**, executing the file prints `nounset 1` and `required_guard 1`. Passing the same text to `bash -c` prints **127** for both. The fence is the file execution. The prose records the other invocation. The failure is non-zero either way.
- **`--pull` flags.** The container script's builds use `--pull=false`. Its runs use `--pull=never`. Both executed against the image that was already local. The flags were not rewritten.
- **`--preserve-root=all`.** The shell lesson quotes the GNU coreutils **9.12** rm manual: the `all` form rejects an argument that is not on the same file system as its parent. The default form refuses to remove `/` recursively. Neither form was executed. A paraphrase about mount points was not swapped in for that sentence.
- **Random floats across Python versions.** The reliability lesson keeps the caveat that another interpreter might draw different floats from `random.Random(7)`. Only 3.14.7 was run. The formula is the part the lesson tells the reader to trust.

## Wording changed after review

- The observability opening now separates the story's 120 ms dashboard from the sample that prints 128.4 ms.
- The reliability rule now says a parallel group fails only when every replica in it has failed, which is what `0.001 ** 2` computes. The exercise says to bin delays with `floor(delay / 0.1)`.
- The consistency paragraph no longer mentions a real-time value of 130. That number is not in the script. The later story edit is the one stamped 90, and the rule keeps clock 100.
- The messaging opening now says the consumer never acknowledges the delivery, so the broker delivers it again.
- The Git lesson names `git init --initial-branch=main`, added in Git 2.28, instead of a vaguer "asks init for the name main."

The executable fences were not edited for these sentences. [p7-examples.json](validation/p7-examples.json) is the run of the final files.

## Findings already covered by the draft

The percentile lesson already says index 98 is a nearest-rank teaching definition and that histograms estimate a different number. The scaling lesson already says 0.094 is close to 1/11, that close is not identical, and that the script does not invent a peak multiplier. The consistency lesson already names reading the primary, waiting for a write position, and sticking a session to a copy that has the write. The incident lesson already limits `startswith`, already sequences the column drop as expand then migrate readers then contract, and already calls the numeric rule one scenario. The Git lesson already defines `git revert -n`. The shell lesson already documents `>|` while `noclobber` is set, and it already forbids executing the expanded removal. The container trade-off already says a single-process exec form does not forward signals to workers.

## Deferred on purpose

Optional additions were left out: a second build-log parser, an image-digest line, a SQLite idempotency table, a Kafka transactional producer, `PIPESTATUS`, a feature-flag code sample, and a PostgreSQL lag query. The lessons point at the manuals for those mechanisms and do not pretend the local scripts demonstrate them. Prerequisite fields stay as existing lesson slugs. `git-force-pushed-main` stays a free-text assessment link. The lesson does not perform a force-push and does not describe that check as an automated rejection.

## Limits

The review shows the model can be confidently wrong about versions and about outputs that were measured on this machine. Dispositions prefer the run or the cited manual. The retained JSON is the record of that judgment. It is not a learner-outcome study, and it is not human verification.

## November 9 follow-up

The existing ten reviews and all 50 dispositions were checked against their recorded final hashes. A subsequent accuracy pass corrected the container practice: cache-friendly ordering is a single build stage, while a multi-stage build uses multiple `FROM` instructions. The executable fences were unchanged. [Docker's definition](https://docs.docker.com/build/building/multi-stage/) supports the correction.

The same independent model reviewed the corrected final lesson. Three malformed JSON responses were discarded; the retained follow-up is plain text, with the model, timestamp, exact input hash and all three dispositions in [p7-review.json](validation/p7-review.json). Its overall recommendation asks for minor fixes, but its findings require evidence checks: the cache inspection it requests is already supplied by `layer_result` and the expected stdout; the fixed timing observation is already scoped to the tested image and explicitly excludes a full stop timeout; the proposed volume example is an optional extension. None establishes a remaining blocking defect. These limitations remain visible in the report, and no advisory label is represented as human approval.

All final executable examples passed again, including an added unprivileged Linux Bash 5.2.37 run of the shell fence. The final manifest records the corrected lesson hash. **All ten lessons remain `reviewed`, and none is human-verified.**
