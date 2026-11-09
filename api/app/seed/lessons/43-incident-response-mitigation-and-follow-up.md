+++
slug = "incident-response-mitigation-and-follow-up"
skill = "senior-practices"
topic = "incidents"
difficulty = "intermediate"
title = "Incidents: mitigation, roles and follow-up"
summary = "When a fresh deploy makes errors jump, take the reversible path first, separate coordination from debugging, and write follow-up actions that change the system."
estimated_minutes = 32
objectives = ["Choose rollback as the first mitigation when a recent deploy lines up with a sharp error increase and the previous version was healthy.", "Assign distinct roles so the incident lead is not also the only person debugging.", "Reject a follow-up that only tells an individual to be more careful."]
prerequisites = ["safe-delivery-and-observability", "code-review-that-finds-risk"]
misconceptions = ["The first job is to find the faulty line before changing anything, even when the previous version is healthy and one click away.", "The incident lead should debug, because they understand the system best.", "A postmortem action item is a reminder to the person who merged the change."]
checks = ["sp-incident-first-action", "sp-lead-incident", "sp-postmortem-action-item"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the mitigation and action examples were executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Google SRE book: managing incidents"
url = "https://sre.google/sre-book/managing-incidents/"
[[resources]]
title = "Google SRE book: postmortem culture"
url = "https://sre.google/sre-book/postmortem-culture/"
[[resources]]
title = "Google SRE workbook: incident response"
url = "https://sre.google/workbook/incident-response/"
+++
## Why it matters

Ten minutes after a deploy, checkout errors move from a tenth of a percent to eight percent. The previous version was healthy. People open traces, the channel fills with theories, and nobody has said who is allowed to roll back. Forty minutes later a dropped column is the cause, and the follow-up ticket says the engineer should be more careful. The next migration repeats it. Incident response is a sequence: make the user impact smaller with the least irreversible step, keep one timeline, and change the system so the same trigger does not need heroics.

Prerequisites: the safe-delivery lesson's rollback criteria, and the review habit of looking at risk. The script is a teaching rule with the numbers from a single scenario. It is not an incident commander and it must not be wired to a production deploy button.

## Mental model

Mitigation comes before a complete explanation when you have a reversible step that matches the evidence. A deploy that just went out, a healthy previous version, and a sharp jump in errors are that pattern. Rollback returns to the version you already ran. It is not a confession that you understand the bug. It is a way to stop the harm while you learn. If the previous version is not healthy, or the bad change was a data migration that rollback will not undo, the first step is different. Say which case you are in.

Roles exist so one person is not the only communicator, the only debugger, and the only decision maker. The incident lead coordinates. An operations role debugs and proposes mitigations. A communications role updates the people who are waiting, including customers when the impact is external. On a small team one person may wear two hats, and the lead should still not be the only person reading logs. The Google SRE chapter on managing incidents describes this separation. Titles in your company can differ. The failure mode to avoid is a silent hero.

A follow-up action changes a tool, a default, or a process that does not depend on someone remembering. "Be more careful" is not an action. "Drop the column in a later migration, after the running version no longer reads it" is an action. So is a check that refuses the drop while a known reader exists. Blameless does not mean vague. It means the story is about the system that allowed the change to ship, and the fix is aimed there.

## How it works

Declare the incident when the impact is real and more than one person needs to coordinate. Open one channel. Start a timeline with times, not a second chat. Assign the roles out loud. Collect what changed: deploys, flags, migrations, traffic, dependencies. If a deploy in the last half hour is the only large change and errors jumped, roll back unless you already know the rollback is unsafe. The example's rule is specific: error rate at least 5 percent, previous rate under 1 percent, deploy within 30 minutes, recommendation "roll back the deployment." Change the thresholds only by rewriting the rule, not by remembering a vibe. If the evidence does not match, the rule says to keep investigating before changing more. Do not expand the rule into a general AI incident bot.

Define resolved before you need the word. For this shape, resolved means the error rate is back under the threshold you had before, the rollback or other mitigation is stable, and the user-facing message says so. A fix that is merged but not deployed is not resolved. A deploy that lowered errors for five minutes is not resolved until you have watched the window you agreed.

Afterwards, write the timeline from the channel while it is fresh. Ask what made the mistake easy, not who made it. Pick actions a stranger can implement: a migration linter, a progressive rollout that stops on the error budget, an alarm that pages on that dashboard. Give each action an owner and a date. Review whether they were finished. A postmortem with no finished action is a diary.

The dropped-column case is a schema-compat problem. The running code still selected the column. The safe sequence is expand, migrate readers, then contract. The follow-up is to make the contract step wait until the readers are gone, and to test that with the old binary. A reminder to the author does not add that test.

## Worked example

The function encodes the one scenario above. The action labels are a string check for a teaching pair of sentences, not a classifier you should deploy.

```python
def first_mitigation(error_rate, previous_error_rate, deployed_minutes_ago):
    if error_rate >= 0.05 and previous_error_rate < 0.01 and deployed_minutes_ago <= 30:
        return "roll back the deployment"
    return "keep investigating before changing more"

print("mitigation", first_mitigation(0.08, 0.001, 10))

def system_action(text):
    blame = text.lower().startswith("remind the engineer")
    return "not-a-system-fix" if blame else "system-fix"

print("blame_action", system_action("Remind the engineer who merged the migration not to do that again."))
print("migration_action", system_action("Make column removal a later migration that ships only after readers are gone."))
```

```text
mitigation roll back the deployment
blame_action not-a-system-fix
migration_action system-fix
```

Eight percent errors, a previous rate of 0.1 percent, and a deploy ten minutes ago fall inside the rule, so the printed mitigation is rollback. The reminder is labeled as not a system fix. The delayed column drop is labeled as a system fix. Executed with CPython 3.14. A different sentence that still blames someone would fool `startswith`. Read the action. Do not trust the helper outside this example.

## Common mistakes

- Hunting for the root cause while the bad deploy keeps serving all users and the previous artifact is ready.
- Rolling forward with an untested patch because rollback feels like failure. Rollback is a mitigation. The patch can come next.
- Letting the most senior person debug alone in a terminal while the channel has no updates.
- Declaring resolution when the graph has dipped once.
- Closing the review with a training action and no change to the migration path that dropped the column.

## In production

Decide the rollback command before the incident. The person on call should be able to run it without finding the right CI job from scratch. Record who ran it and the result on the timeline. If rollback is unsafe because of a migration, say that in the first minutes and pick the next reversible step: a flag, a traffic shift, or a restore plan you have actually rehearsed.

Keep customer updates on a cadence even when the update is "we are still mitigating." Silence is interpreted as not knowing, or as not caring. Internal theories stay in the working channel. The external sentence is impact, current mitigation, and the next update time.

Page from the symptom, the error rate or the failed checkouts, not only from the cause. The safe-delivery lesson's canary checks are the same signals. An incident that starts from a canary is smaller. Use that path when you have it. This lesson assumes the bad deploy already reached users.

## Trade-offs and limits

Rollback is wrong when the previous version is the outage, when the new version fixed a worse hole, or when data written by the new version cannot be read by the old one. The rule in the script does not know those cases. A human has to refuse the recommendation. That is why the script is not a controller.

Role separation is harder on a team of two. Write down the minimum: one person speaks on the cadence, one person changes production, and they do not both improvise in the same minute. A large incident adds a planning role and a scribe. The SRE workbook shows a fuller set. You do not need every role to avoid the failure mode in this lesson.

Blameless reviews can still become a pile of action items nobody finishes. Three finished system changes beat twelve reminders. This lesson does not describe legal, communications, or security-incident processes beyond the engineering response. Those have their own owners when user data or the law is involved.

## Check your understanding

1. Errors jumped from 0.1 percent to 8 percent ten minutes after a deploy, and the previous version was healthy. What is the first mitigation to reach for, and what is it for?
   - Feedback: roll back. It restores a known-good version while you find the cause. It is not a substitute for the later fix.
2. Why should the incident lead not be the only person in the logs?
   - Feedback: the lead has to keep roles, the timeline, and the mitigation decision moving. Debugging can absorb that person until nobody is coordinating.
3. Why is "remind the engineer" a weak postmortem action after a dropped column?
   - Feedback: the next person can make the same migration. A system change keeps the drop from shipping while old code still reads the column.

## Practice

Write a one-page timeline for the checkout scenario: detection, roles, the rollback decision, what would make you refuse rollback, the resolution line, and two follow-up actions. Run the teaching function on a second set of numbers where the deploy was yesterday and confirm it does not recommend rollback.

Acceptance criteria: roles are named and the lead is not the only debugger; the rollback decision cites the fresh deploy and the healthy previous version, and the refusal case is explicit; both follow-ups change a system or a check, and neither is a personal reminder. Do not run a rollback in production as the exercise. As a transfer task, take a migration that deletes a column and sequence it so the running version is safe at every step.
