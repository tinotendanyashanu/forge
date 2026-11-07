+++
slug = "code-review-that-finds-risk"
skill = "senior-practices"
topic = "code-review"
difficulty = "beginner"
title = "Code review that finds risk"
summary = "How to review changes for what can hurt users and the team (correctness, security, data and operability) instead of style, and how to give feedback that gets acted on."
estimated_minutes = 20
objectives = [
  "Prioritise review attention on correctness, security, data safety and operability.",
  "Ask for changes that are small and single-purpose enough to review well.",
  "Write review comments that are specific, explained and appropriately weighted.",
]
prerequisites = ["unit-tests-that-matter", "security-auth-and-injection"]
misconceptions = [
  "A good review comments on as many lines as possible.",
  "Style and formatting issues are the most valuable things to catch.",
  "Approving means the reviewer has guaranteed the change is bug-free.",
]
checks = ["sp-review-missing-tenant-check", "sp-risky-migration-change", "sp-large-pr"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pending independent human review"

[[resources]]
title = "Google engineering practices: The standard of code review"
url = "https://google.github.io/eng-practices/review/reviewer/standard.html"

[[resources]]
title = "Google engineering practices: What to look for in a code review"
url = "https://google.github.io/eng-practices/review/reviewer/looking-for.html"

[[resources]]
title = "Google engineering practices: Small CLs"
url = "https://google.github.io/eng-practices/review/developer/small-cls.html"
+++
## Why it matters

Code review is one of the last cheap places to catch a problem before it reaches users. It is also where teams share knowledge and set standards. Reviews that focus on naming and formatting while missing a missing authorisation check or a table-locking migration give a false sense of safety; reviews that are slow or harsh make people avoid them. A senior engineer's reviews are valuable because they find the risky line and explain it clearly.

## Mental model

Review in order of **cost if wrong**:

1. **Correctness and security**: does it do what it claims for all inputs, including other tenants' data, empty values, concurrency and failure paths? Is every input validated and every access authorised?
2. **Data safety**: can it lose or corrupt data? Are migrations reversible and safe to run on a large, live table?
3. **Operability**: will we know when it breaks (logs, metrics, alerts) and can we roll it back?
4. **Design and maintainability**: is it in the right place, readable, tested at the right level?
5. **Style**: leave as much as possible to formatters and linters.

Spend most of your attention at the top of the list.

## How it works

**Start with intent.** Read the description and linked issue first. If you cannot tell what the change should do, ask before reading the diff.

**Find the risky lines.** Look for queries and endpoints that take an id from the request (is ownership checked?), new external calls (timeouts, retries, error handling), money or permissions logic, migrations, concurrency, and anything deleted. Check that tests cover the behaviour that matters, including a failure case.

**Ask for reviewable changes.** A change that mixes a feature, mass reformatting and dependency upgrades hides risk. Ask for it to be split by purpose. Small, single-purpose changes get better reviews and are easier to revert.

**Write useful comments.** Be specific (which line, what input breaks it), explain why it matters, and suggest a direction. Label weight explicitly: a blocking issue versus a "nit" or an optional suggestion. Ask questions when you are unsure rather than asserting. Praise good decisions; it reinforces them.

**Approve deliberately.** Approval means "I have reviewed this and believe it is safe to ship", not "I skimmed it". If you only reviewed part, say which part.

## Worked example

A change adds an endpoint to download an invoice:

```python
@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice(invoice_id: int, user: User = Depends(current_user), db: Db = Depends(get_db)):
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404)
    return Response(render_pdf(invoice), media_type="application/pdf")
```

The diff also renames twenty variables and reformats a file. A risk-focused review comment:

> **Blocking:** `download_invoice` loads any invoice by id but never checks that it belongs to `user`'s organisation, so any logged-in user can download every customer's invoices by changing the number (broken object-level authorisation). Please filter by `organisation_id == user.organisation_id` in the query and return 404 for other tenants' invoices, and add a test where a user from another organisation gets 404.
>
> **Non-blocking:** could the renames and formatting go in a separate PR? They make the security-relevant part harder to spot.

The comment names the line, the exploit, the fix and the test, and separates it clearly from the optional request.

## Common mistakes

- Dozens of style comments and no mention of the missing authorisation check.
- Approving a huge pull request after reading only the parts you understand.
- Vague comments ("this looks wrong") with no reason or suggestion.
- Personal tone ("why would you do this?") instead of discussing the code.
- Blocking on personal preference that is not a team standard.
- Letting reviews sit for days, which pushes authors towards bigger, riskier batches.

## In production

Teams agree on what reviewers must check (security, migrations, observability) and automate everything else: formatting, linting, type checking, dependency and secret scanning. Risky areas (authentication, payments, migrations) may require a specific reviewer. Track review turnaround time; fast reviews encourage small changes. When an incident traces back to a reviewed change, improve the checklist or the automation rather than blaming the reviewer.

## Trade-offs and limits

Review catches many problems but is not a substitute for tests, type systems, monitoring or staged rollouts; reviewers miss things, especially in large diffs. Deep reviews take time, so match depth to risk: a copy change needs a glance, a migration on a 500-million-row table needs careful thought. Mandatory multiple approvals add safety but slow delivery; use them where the risk justifies it.

## Check your understanding

1. A diff contains a missing tenant check, inconsistent variable names and a long function. Which comment matters most?
   - Answer: The missing tenant check, because it lets users access other customers' data; the others are maintainability concerns.
2. What should you do with a 3,000-line pull request that mixes a feature, formatting and upgrades?
   - Answer: Ask for it to be split into single-purpose changes so each can be reviewed properly and reverted independently.
3. What makes a review comment actionable?
   - Answer: It is specific about the line and the problem, explains why it matters, suggests a direction, and says whether it is blocking.

## Practice

Pick a recent merged pull request in a project you know (or an open-source one). Review it using the priority list above and write your three most important comments, each labelled blocking or non-blocking, with the reason and a suggested fix. Then compare them with the comments the change actually received.
