+++
slug = "injection-safe-data-boundaries"
skill = "security"
topic = "injection"
difficulty = "beginner"
title = "Injection defenses: keeping data out of interpreter control"
summary = "Use parameter channels and context-appropriate output handling, then extend the same boundary reasoning to rich text, command execution and server-side URL fetching."
estimated_minutes = 32
objectives = ["Separate SQL values from identifiers and keep authorization scope in the query.", "Choose safe text rendering or a maintained sanitizer for the actual output context.", "Explain why URL validation alone is insufficient for a server-side fetch boundary."]
prerequisites = ["security-auth-and-injection", "sql-querying-joins-and-nulls", "python-functions-scope-and-closures"]
misconceptions = ["Removing quote characters is equivalent to SQL parameterization.", "Escaping HTML text makes a value safe in every JavaScript or URL context.", "Checking that a URL starts with https prevents SSRF."]
checks = ["sec-parameterised-query", "sec-react-xss-bio", "sec-ssrf-avatar-url"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; dummy local fixtures only; advisory second-model review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "OWASP: SQL injection prevention"
url = "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"
[[resources]]
title = "OWASP: Cross-site scripting prevention"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html"
[[resources]]
title = "OWASP: Server-side request forgery prevention"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html"
[[resources]]
title = "Python sqlite3: SQL placeholders"
url = "https://docs.python.org/3.12/library/sqlite3.html#sqlite3-placeholders"
+++
## Why it matters

A search field should choose which records to return, not change the database query's structure. A profile biography should supply visible text, not instructions for another person's browser. An avatar importer should retrieve an approved image, not become a proxy into the server's internal network. Each failure crosses a boundary where a lower-trust value gains authority it was never meant to have.

Read the authentication lesson, SQL querying and Python functions lesson first. You should distinguish authorization from input shape checks. This lesson deepens the earlier security overview with a complete safe query, explicit identifier handling and separate output/network boundaries. The executable lab uses dummy in-memory SQLite data and no network or credentials.

## Mental model

An interpreter receives both instructions and values. Injection occurs when an untrusted value can alter the instruction structure or reach an unsafe capability. The defense depends on the receiving context: a SQL value channel, an HTML text node and a server's network destination are different boundaries.

Validation asks whether a value meets an application's rules. Parameterization or safe rendering controls how an interpreter treats that value. Authorization determines whether the principal may use the resulting capability. None of these substitutes for the other two.

Name the principal, input, intended capability and resource for each design. For a tenant invoice search, the principal may choose an email filter within their tenant. They may not remove the tenant restriction or select an arbitrary SQL expression. This description makes the invariant testable.

## How it works

For SQL values, send query text and bound values through the database driver's parameter API. SQLite uses question-mark placeholders here; other drivers use different syntax, such as asyncpg's `$1`, `$2` placeholders or psycopg's `%s` and `%(name)s` value placeholders. Follow the specific driver rather than interpolating strings or surrounding placeholders with hand-written quotes.

Parameters represent values, not arbitrary SQL identifiers or syntax. To offer user-selected sorting, map a small public option to a fixed trusted column or use the driver's identifier-composition API where appropriate. Do not call an unchecked user string an identifier merely because the query also uses parameters elsewhere.

For HTML, prefer a text-rendering API. React interpolation escapes strings as text; assigning a string to innerHTML or dangerouslySetInnerHTML chooses a different, interpreting boundary. A maintained allowlist sanitizer is needed when the product intentionally accepts restricted rich HTML. Output handling must match the context: escaping a text node does not automatically make a string safe in script source, a CSS expression or a navigable URL.

SSRF concerns the server's network authority. Prefer a narrow trusted destination policy or a dedicated fetch service instead of accepting arbitrary URLs. Parse URLs structurally, constrain schemes/hosts/ports, control redirects, and enforce allowed destinations at connection/egress boundaries. DNS changes, alternate address forms and redirects can defeat simplistic string checks. A public hostname string is not proof that the eventual connection reaches only an allowed public address.

The SQL value boundary is the entry topic. Treat rich-text and SSRF controls as extensions after you can explain the complete query below.

## Worked example

Run this script in a disposable environment. The tenant argument models an identity already established by server-side authentication; it must not be trusted merely because a client supplied it.

```python
import sqlite3
from html import escape

db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE invoices(id INTEGER PRIMARY KEY, tenant_id INTEGER, email TEXT, total_cents INTEGER);
INSERT INTO invoices VALUES
  (11, 1, 'a@example.test', 100),
  (12, 1, 'a@example.test', 200),
  (21, 2, 'a@example.test', 900);
""")

def invoice_ids(tenant_id, email, order_by):
    columns = {"amount": "total_cents", "id": "id"}
    if order_by not in columns:
        raise ValueError("Unsupported sort")
    column = columns[order_by]  # only a fixed trusted SQL fragment reaches this slot
    rows = db.execute(
        f"SELECT id FROM invoices WHERE tenant_id = ? AND email = ? ORDER BY {column}, id",
        (tenant_id, email),
    ).fetchall()
    return [row[0] for row in rows]

try:
    print(invoice_ids(1, "a@example.test", "amount"))
    print(invoice_ids(1, "' OR 1=1 --", "amount"))
    try:
        invoice_ids(1, "a@example.test", "total_cents DESC")
    except ValueError as error:
        print(str(error))
    print(escape("<b>untrusted</b>"))
finally:
    db.close()
```

Output:

```text
[11, 12]
[]
Unsupported sort
&lt;b&gt;untrusted&lt;/b&gt;
```

The first query cannot return tenant 2's invoice. The quote-containing string in the second call is treated as one email value and matches no fixture row. The sort option is rejected before any SQL fragment is selected. The final line is suitable for an HTML text context; it is not a universal sanitizer. In React, ordinarily pass the original string as text and let React perform its normal escaping rather than double-encoding it first.

## Common mistakes

- Parameterizing the search value but accepting the tenant ID from an untrusted request without authorization.
- Joining an allowlisted column with unchecked user-supplied direction or suffix text. Every syntax fragment needs a trusted construction path.
- Removing only script tags while leaving interpreting attributes, unsafe URLs or other active markup.
- Validating one URL, then following redirects or performing a later DNS lookup without enforcing the same destination policy on the actual connection.

## In production

Keep database privileges limited to what the service needs. Query timeouts, row limits and resource bounds reduce damage but do not repair interpreter-boundary errors. Audit raw SQL composition at its final execution point and test both correct business scoping and literal handling of unusual input.

For rich text, update the sanitizer as part of dependency maintenance and test the exact rendering context. CSP is a useful additional control, not permission to render untrusted markup unsafely. For server-side fetching, constrain response size, time, redirects and content processing as well as destinations. Never probe internal or production networks to practice this lesson; use isolated fixtures.

## Trade-offs and limits

An allowlist is easiest when the product needs a small known set of destinations or query options. A generic public-URL fetcher is a more complex service with a larger attack surface and must be designed accordingly. A regular expression over the entire URL is not an adequate replacement for a connection policy.

Passing an argument array with shell interpretation disabled can avoid shell metacharacter parsing, but an invoked program can still interpret its own flags. Keep capabilities narrow and use explicit APIs. The general lesson is to choose a boundary whose guarantees match the interpreter you actually invoke.

## Check your understanding

1. Why is the f-string in this example different from interpolating the supplied email?
   - Feedback: its only variable fragment comes from a fixed internal mapping. The untrusted email remains in a bound-value channel.
2. Why does safe SQL parameterization not prove that a user may read the selected invoices?
   - Feedback: interpreter safety does not establish authority. The tenant/principal scope must come from trusted authentication and authorization.
3. Why can a URL pass an initial hostname check and still require redirect and egress controls?
   - Feedback: the connection destination can differ after redirection or resolution changes. Enforce the destination policy where connections are actually made.

The linked FORGE checks cover parameterized queries, React text versus rich HTML and SSRF destination reasoning. Begin with beginner security assessments, then use intermediate and advanced checks for rendering and network boundaries.

## Practice

Use the existing second tenant to verify isolation, then extend the fixture with a third tenant and a sortable created-time field. Test ordinary input, apostrophes, a SQL-shaped email value, unknown sort options and attempts to select another tenant's records. Keep all values synthetic.

Acceptance criteria: query structure changes only through approved fixed options; tenant isolation holds; unusual strings remain data. Then design a local-only avatar-import test plan covering redirect to a forbidden fixture address, excessive response size and a slow response. State which control rejects each case without making any request to a real internal service.
