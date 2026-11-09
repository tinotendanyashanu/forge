+++
slug = "technical-decisions-records-and-reversibility"
skill = "senior-practices"
topic = "decision-making"
difficulty = "intermediate"
title = "Technical decisions: records, reversibility and replacement"
summary = "Match the ceremony to how hard a decision is to undo, write down context and alternatives while they are still known, and replace a large system in slices that can ship."
estimated_minutes = 30
objectives = ["List the parts of a decision record that let a later reader judge whether it still holds.", "Spend more design time on a public, hard-to-reverse choice than on a local library choice.", "Prefer an incremental replacement when a full rewrite would hide the old behaviour until the end."]
prerequisites = ["code-review-that-finds-risk"]
misconceptions = ["A decision record is the meeting minutes, or only the winning sentence.", "A logging library and a public partner API deserve the same review because both are decisions.", "A rewrite is safer if the team stops features until the new system is complete."]
checks = ["sp-adr-contents", "sp-queue-choice-reasoning", "sp-one-way-door", "sp-rewrite-vs-incremental"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the record checker was executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Architecture decision records"
url = "https://adr.github.io/"
[[resources]]
title = "Amazon 2016 letter to shareholders, type 1 and type 2 decisions"
url = "https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders"
[[resources]]
title = "Martin Fowler: strangler fig application"
url = "https://martinfowler.com/bliki/StranglerFigApplication.html"
+++
## Why it matters

Two years later nobody remembers why the service uses PostgreSQL, the person who knew has left, and the team opens a migration to a document store because the record only says "we decided." The same week, a public API field is renamed because it was treated like an internal logging library. A rewrite that was going to take a year is still unfinished, and the old system gained features the new one does not have. Decision quality is mostly about reversibility, memory, and whether value ships before the end.

Prerequisites: the code-review lesson's habit of looking for risk rather than style. This lesson does not add a workflow tool. The script checks that a record has four fields. A complete record can still be a bad decision.

## Mental model

A useful architecture decision record answers four questions for a reader who was not in the room. What forces were in play. What was chosen. What else was considered and why it lost. What becomes true afterward, including the costs. It is short. It is not the schema, the meeting transcript, or a list of who argued. When the decision changes, write a new record that supersedes the old one. Editing history makes the old reasons impossible to find. The adr.github.io collection is a set of lightweight conventions for that shape, not a required template.

Reversibility decides the ceremony. A choice that other companies bind into generated clients, stored payloads, or contracts is expensive to undo. Give it alternatives, a review, and a record. A logging library inside one service can be wrapped and replaced next month. Decide it quickly, leave a note if you want, and do not block a week of design on it. Amazon's 2016 shareholder letter calls these type 1 and type 2 decisions. The letter is a management essay, not a proof. The engineering content is the cost of being wrong and the cost of changing your mind.

A rewrite that freezes the old system tries to rediscover its behaviour in a batch. Hidden rules show up late, and no user value appears until the cutover. An incremental replacement, the strangler fig, puts one capability in front of the old one, ships it, and keeps a way back. The old system stays the authority for what has not moved. The cost of not rewriting also stays visible: you are still paying to change the old code until each slice moves.

## How it works

Before the meeting ends, fill the four fields in sentences a new teammate can read. Context includes scale, skills, and constraints, not a slogan. Alternatives include the real runner-up. If nobody can say why the runner-up lost, the decision is not finished. Consequences include the bad ones: operational load, migration pain, and what you will do when the constraint changes. The example's checker only looks for non-empty fields. It will accept nonsense that is non-empty. Use it as a completeness gate, then read the words.

Match the time box to the door. For the public API, write the compatibility rule: what you can add, what you can never change, and how a version would work if you truly need a break. For the library, choose the one the team can operate, wrap it if replacement is likely, and move on. A team that has not operated Kafka does not have to operate Kafka for 50 messages a second. The decision record should say that the simpler queue was chosen because the team can run it, and what volume would force a revisit. That is a consequence, not a lack of ambition.

For a replacement, draw the seams. Pick one capability a user can see. Route that capability to the new code with a switch you can turn off. Leave the rest on the old path. Define the slice's done test before you start. A rewrite plan that says "and then we decide which capabilities move" has postponed the only decision that creates a milestone. Keep the old system shipping small changes, or the new system will chase a moving target with no intermediate release.

## Worked example

The checker is a teaching gate for missing fields. The two reversibility flags are constants in the example, not a measurement.

```python
required = ("context", "decision", "alternatives", "consequences")

def record_gaps(document):
    return [field for field in required if not document.get(field)]

weak = {"decision": "Use PostgreSQL"}
complete = {
    "context": "Orders need transactions and relational queries.",
    "decision": "Use PostgreSQL for the order service.",
    "alternatives": ["MongoDB"],
    "consequences": ["Operational familiarity; schema changes need migrations."],
}
print("weak_gaps", record_gaps(weak))
print("complete_gaps", record_gaps(complete))
print("public_api_reversible", False)
print("logging_library_reversible", True)
```

```text
weak_gaps ['context', 'alternatives', 'consequences']
complete_gaps []
public_api_reversible False
logging_library_reversible True
```

The one-line decision is incomplete. The four-field record passes the gate and still has to be read by a person. The public API is marked hard to reverse. The logging library is marked reversible. Executed with CPython 3.14. Nothing here queries a design repository.

## Common mistakes

- Filing the decision as a chat message and calling that a record. Chat does not state the rejected alternative.
- Recording who won the argument. The next reader needs the forces, not the score.
- Giving a type 2 choice a type 1 process so that everything feels careful. The urgent type 1 choice then waits behind it.
- Choosing a system because it is impressive at a scale the team does not have, and leaving no number that would trigger a revisit.
- Stopping all product work for a rewrite, then discovering a billing rule that lived only in the old code.

## In production

Keep records next to the code, in a path reviewers see when the relevant service changes. Link the record from the repository area it governs. Supersede by identifier. A search for the old decision should find the new one. Do not treat the record as approval to skip the compatibility review on the pull request that implements it.

When a decision is hard to reverse, add a small reversible experiment if you can: a feature flag, a second implementation behind an interface, or a limited partner. The point of naming a one-way door is to spend effort making it more reversible, not only to write a longer document. When it truly is one-way, the review should include someone who will operate the result.

For a strangler migration, publish the slice list and which slice is in front of users now. A dashboard of "percent rewritten" that is not tied to a routed capability is a mood. The rollback test is to send that capability back to the old path and show that it still works.

## Trade-offs and limits

A short record omits detail a design document would keep. That is acceptable when the link to the design document is in the consequences. A long record that nobody updates becomes fiction. Prefer a new superseding record over a rewrite of the old one.

Spending little time on a reversible choice can still pick a library with a painful license or a security record. Reversible is not the same as unimportant. It means you can correct it. Look once, decide, and leave the seam.

Incremental replacement can leave the system in a hybrid longer than a rewrite proposal promised. The hybrid is the cost of being able to stop. A full rewrite is still rational when the old system cannot be routed slice by slice and the business can carry the freeze. The lesson's default is the slice because the failure mode of the freeze is worse for most products. The checker cannot make that judgment. A human does.

## Check your understanding

1. What is missing from a record that only states the winning technology?
   - Feedback: the context, the alternatives that were rejected, and the consequences. A later reader cannot tell whether the choice still fits.
2. Why does a public partner API get a deeper review than an internal logging library?
   - Feedback: partners will bind to the API, so changing it later is expensive. The library can be replaced behind a local seam. Ceremony should follow the cost of reversal.
3. Why is a feature freeze until the new stack is finished a risky replacement plan?
   - Feedback: the old behaviour keeps being discovered late, and users get nothing until the end. Slices that route one capability at a time can ship and can roll back.

## Practice

Write a one-page record for a queue choice at a stated rate, including one alternative you reject and one measurement that would make you revisit it. Mark one real decision in your own work as hard to reverse and one as easy, with the reason. Outline a two-slice replacement of a system you know, naming the first user-visible capability and the rollback.

Acceptance criteria: the record contains context, decision, alternatives, and consequences, and a person other than the author can restate why the runner-up lost; the reversibility labels point at the cost of change, not at how interesting the technology is; the replacement has a first slice that can ship without the rest. Do not present the checker script as approval. As a transfer task, supersede your record with a second one that changes the queue, and say what you do with the first document.
