# Content workflow

How FORGE assessment content is authored, checked and published. The goal is to grow the bank in small batches without lowering quality.

## Files

| Path | Purpose |
| --- | --- |
| `api/app/seed/content/NN-<skill>.json` | Question content loaded into the database. Strict schema (`app/seed/schema.py`). Topics must equal the skill's curriculum subskills, in order. |
| `api/app/seed/meta/NN-<skill>.meta.json` | QA metadata, not loaded into the database: version, status, provenance, learning objective, prerequisites, distractor rationale, follow-up questions. |
| `api/app/seed/qa.py` | The automated quality gate. |
| `docs/curriculum/AUDIT.md` | Coverage and quality baseline. |

Question slugs are stable identifiers. The seed loader upserts by slug and **deactivates** questions removed from the files; it never deletes them, so learner history is preserved.

## Statuses

`draft` → `reviewed` → `verified` → published, with `needs-improvement`, `rejected` and `archived` as side states. `reviewed` means the author and an automated second pass agree; `verified` additionally requires a human subject-matter review recorded in the metadata.

## Stages for every batch

1. **Plan the batch** from the gap list in `AUDIT.md`. Keep batches small (one or two skills, 10–40 questions).
2. **Author** content and metadata. Record provenance honestly, e.g. "ai-assisted draft".
3. **Execute code.** For every question whose answer depends on running code, run the snippet and compare it with the keyed answer.
4. **Run the gate:** `venv/bin/python -m app.seed.qa --check-urls`. Errors block the batch. Review every warning that refers to the new questions; warnings on unchanged content are tracked in the audit.
5. **Blind second pass (advisory).** Give a different model each single-choice question *without* the key and ask it to answer, flag ambiguity and list errors; for free-text, ask it to critique the reference answer. Investigate every disagreement and fix genuine issues. This is not human verification.
6. **Integration tests:** `venv/bin/python -m pytest -q` (includes `tests/test_content_qa.py`), then seed a scratch database twice to confirm the import is idempotent.
7. **Publish** (production):
   1. Run the nightly backup job on demand and confirm the encrypted copy uploaded.
   2. Record learner-history counts (`answers`, `assessment_sessions`, `interview_sessions`, `mastery_evidence`).
   3. Deploy the commit and run `python -m app.seed` once.
   4. Re-check the counts (must be unchanged) and the number of active questions (must increase by the batch size).

## Rules that protect learners

- Never edit the options of a question learners have answered in a way that changes which option key is correct. Create a new question (new slug) and remove the old one from the seed instead; it becomes inactive and its history stays valid.
- Single-choice questions are the only assessment content that produces verified mastery. Each skill needs **at least two scored questions per level** for that level to be verifiable.
- Free-text answers are saved, not scored. Use them for reasoning practice and interviews.
- AI review is advisory everywhere. It never decides correctness of keyed answers.

## Cost of AI-assisted review

A blind review pass costs one model call per question (about 300–900 tokens each). A 40-question batch is 40 calls, well within the deployed hourly cap of 120.
