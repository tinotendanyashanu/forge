+++
slug = "security-auth-and-injection"
skill = "security"
topic = "auth"
difficulty = "beginner"
title = "Authentication, authorisation and injection"
summary = "The two questions every request must answer, why object-level checks matter, and how to keep untrusted input from becoming code."
estimated_minutes = 22
objectives = [
  "Distinguish authentication from authorisation and enforce object-level authorisation.",
  "Prevent SQL injection with parameterised queries.",
  "Explain how stored XSS works and how output encoding or sanitisation prevents it.",
]
prerequisites = ["http-requests-and-semantics", "fastapi-validation-and-dependencies"]
misconceptions = [
  "A valid login token means the request is allowed.",
  "Escaping quotes by hand is enough to prevent SQL injection.",
  "Removing <script> tags prevents XSS.",
]
checks = ["sec-idor-invoice", "sec-parameterised-query", "sec-react-xss-bio"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pending independent human review"

[[resources]]
title = "OWASP Top 10"
url = "https://owasp.org/Top10/"

[[resources]]
title = "OWASP API Security: Broken Object Level Authorization"
url = "https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/"

[[resources]]
title = "OWASP Cheat Sheet: SQL injection prevention"
url = "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"

[[resources]]
title = "OWASP Cheat Sheet: Cross-site scripting prevention"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html"
+++
## Why it matters

The most common serious web vulnerabilities are not exotic. An API returns someone else's invoice because nobody checked ownership. A search box lets an attacker read the whole users table. A profile bio runs JavaScript in every visitor's browser. Each comes from forgetting one of two rules: check *who may do what to which object*, and never let input change the structure of code.

## Mental model

Every request must answer two separate questions:

1. **Authentication**: *who is making this request?* (a session cookie, a token, a client certificate).
2. **Authorisation**: *is this caller allowed to perform this action on this specific object?*

And every piece of untrusted input is **data**. Injection happens when data is pasted into something that will be interpreted as **code**: SQL text, HTML, a shell command. The defence is to keep data and code in separate channels.

## How it works

**Object-level authorisation.** Checking that a user is signed in is not enough; most APIs operate on objects identified in the URL (`/invoices/1043`). For every such access, scope the lookup to the caller (`WHERE id = $1 AND account_id = $2`) or check ownership after loading. Return `404` rather than `403` when you do not want to reveal that the object exists.

**SQL injection.** Building SQL with string formatting lets input such as `' OR '1'='1` change the query. Parameterised queries send the SQL text and the values separately, so the database never parses values as SQL. ORMs parameterise for you unless you build raw SQL strings yourself. Identifiers (column names in `ORDER BY`) cannot be parameters: map them from an allow-list.

**Cross-site scripting (XSS).** If user-supplied text is inserted into a page as HTML, it can run scripts with the victim's session. Frameworks such as React escape text by default; the danger appears when you opt out (`dangerouslySetInnerHTML`, `innerHTML`, template `|safe` filters). Render untrusted content as text, or sanitise it with an allow-list sanitiser if some formatting is required. A Content-Security-Policy adds a second line of defence.

## Worked example

```python
# Vulnerable: authenticates, but anyone can read any invoice.
@app.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, user=Depends(current_user), db=Depends(get_db)):
    return await db.get(Invoice, invoice_id)


# Fixed: the query itself is scoped to the caller's account.
@app.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, user=Depends(current_user), db=Depends(get_db)):
    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.account_id == user.account_id)
    )
    if invoice is None:
        raise HTTPException(404)
    return invoice
```

```python
# Vulnerable: the email is pasted into the SQL text.
cur.execute(f"SELECT * FROM users WHERE email = '{email}'")

# Safe: the value travels separately from the query.
cur.execute("SELECT * FROM users WHERE email = %s", (email,))
```

```tsx
// Vulnerable: runs any HTML a user saved, including <img src=x onerror=...>.
<div dangerouslySetInnerHTML={{ __html: user.bio }} />

// Safe by default: React escapes text.
<p>{user.bio}</p>
```

## Common mistakes

- Relying on hard-to-guess ids instead of authorisation checks.
- Doing authorisation only in the frontend by hiding buttons.
- "Sanitising" SQL by stripping quotes, which breaks legitimate data and misses other vectors.
- Deny-listing `<script>`: event-handler attributes and `javascript:` URLs still execute.
- Logging tokens or passwords while debugging authentication.

## In production

Mature services centralise authorisation: a dependency or policy function every endpoint must call, and tests that try every endpoint with a second user's token to prove they get `404`. Static analysis and code review flag raw SQL string formatting and `dangerouslySetInnerHTML`. Security headers (CSP, `HttpOnly` and `SameSite` cookies) reduce the damage when something slips through.

## Trade-offs and limits

Scoping every query to the caller adds a condition and an index to many tables; that cost is tiny compared with a data breach. Sanitising rich text is genuinely hard: prefer a restricted format such as Markdown rendered by a safe library over arbitrary HTML. No single control is enough; layer them so one mistake is not fatal.

## Check your understanding

1. A signed-in user changes `/orders/15` to `/orders/16` and sees someone else's order. Is that an authentication or an authorisation failure?
   - Answer: authorisation; the user was correctly authenticated.
2. Why can't you parameterise a column name in `ORDER BY`?
   - Answer: parameters carry values, not identifiers; map allowed column names from a fixed list instead.
3. Does an `HttpOnly` cookie prevent XSS?
   - Answer: no. It stops scripts reading that cookie, but injected scripts can still act as the user.

## Practice

Take a small CRUD API you have written (or the FORGE practice project). For every endpoint that takes an id, write a test that creates the object as user A and requests it as user B, expecting `404`. Then search the code for string-built SQL and any place that renders HTML from user input, and fix each one.
