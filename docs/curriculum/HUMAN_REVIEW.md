# Human verification checklist

Use a Markdown review record and a normal content pull request. No admin application is needed. Start with the [unsigned template](reviews/TEMPLATE.md). A human reviewer chooses the verdict and signs the exact revision; an agent may prepare evidence but must not invent a reviewer or sign-off. A deploy approval, passing QA gate or AI advisory review does not award human-verified status.

## Identify the artifact

- [ ] Record kind, stable slug, skill/subskill, difficulty, path, content version, commit and SHA-256. For a question, hash the complete question object from its seed file, including options, key, explanation, rubric and references; record the serialization used. For a lesson, hash the Markdown file. Include the metadata revision too.
- [ ] Name the human reviewer and their relevant experience. Keep authoring, AI advice and human review separately attributed. Review one named artifact at a time; a checked sample does not verify the entire bank.
- [ ] State whether the reviewer saw the answer first. For a choice question, solve it before revealing the key, then inspect the key and explanation.

## Technical correctness

- [ ] Execute code and commands in a disposable environment where applicable; save commands, actual output, runtime versions and the expected result. Do not use production data or enable FORGE's coding sandbox as a review shortcut.
- [ ] Check non-executable claims against the linked primary documentation, including version scope and important exceptions. Separate a measured demonstration from a production guarantee.
- [ ] For a question, establish one defensible correct choice under the stated assumptions. Check every distractor, the explanation and the free-text rubric. Do not infer a learner's misconception solely from a wrong option or an AI assertion.
- [ ] For a lesson, check the worked example, its stated output, failure cases and production trade-offs. Record untested claims and their evidence; unresolved material correctness issues block acceptance.

## Clarity and prerequisites

- [ ] The objective is specific and matches the actual skill/subskill and intended entry level. Define necessary vocabulary before using it; identify prerequisite lessons and confirm that those lessons teach the required knowledge.
- [ ] Remove ambiguity, hidden assumptions and answer clues. Options must work in shuffled order; no letter/position references, grammatical giveaways, or obviously absurd distractors. Read the rendered feedback, not only the key.
- [ ] Distinguish a beginner explanation from an advanced extension. Check examples for realistic engineering use, common mistakes and limits.

## Exercise and assessment usefulness

- [ ] Solve the exercise yourself. Acceptance criteria must be observable and achievable with the stated setup; test a plausible incorrect solution as well as a correct one.
- [ ] Check that reasoning feedback explains why, and that a transfer task requires choosing or applying the concept rather than copying a visible answer. For a standalone question, assess the reference reasoning and follow-up rather than requiring a separate lesson exercise.
- [ ] Check each lesson's assessment links against active same-subskill questions. Note that the current launch button selects skill/difficulty rather than exactly those links. Free-text assessment answers are practice, not objective scores.
- [ ] Record whether hints, previously seen items or memorized outputs could explain success. A mechanically correct answer and demonstrated transferable understanding are separate claims.

## References and sign-off

- [ ] Open each reference; verify that it supports the claim, is authoritative, names the relevant version and remains accessible. A 200 response alone does not establish reference accuracy.
- [ ] Record each issue, severity, correction and resolution evidence. Re-review changed material and refresh its hash. Mark deferred non-blocking limitations explicitly.
- [ ] The human supplies a dated `accept`, `revise` or `reject` verdict, scope and reviewer-authored sign-off. Link their review comment/commit or preserve their signed Markdown statement. A typed name inserted by an agent is not sign-off.

Only after a human accepts the final hash with no unresolved material issue may a maintainer change that item's existing status to `verified` in a separate reviewed content change. Link the review record in the existing provenance text; use the existing question metadata or lesson front matter rather than introducing new schema fields. Nothing in this checklist changes statuses automatically. The present 45 lessons and 118 question metadata entries remain `reviewed`; the other 40 questions need provenance work, not invented past review.

For any answered question, preserve its grading meaning and existing option IDs. A correction that changes the correct answer or meaning requires a new stable slug and a controlled content release; do not silently reinterpret history. A later substantive edit invalidates sign-off for that changed revision until a human reviews it again. Keep the old record.

`MasteryEvidence.verified` is a different field: it identifies deterministic grading/execution sources. It does not certify that a human reviewed the question or lesson. Do not use it to award editorial verification.
