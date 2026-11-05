+++
slug = "http-requests-and-semantics"
skill = "http"
topic = "semantics"
difficulty = "beginner"
title = "HTTP requests, methods and status codes"
summary = "How an HTTP exchange is structured, what each method promises, and how to choose status codes that clients can act on."
estimated_minutes = 18
objectives = [
  "Describe the parts of an HTTP request and response.",
  "Explain which methods are safe and which are idempotent, and why retries depend on it.",
  "Choose between common status codes, including 401 and 403.",
]
prerequisites = []
misconceptions = [
  "POST is fine to retry automatically because the server will notice duplicates.",
  "401 means 'not allowed'.",
  "Status codes are decoration; the body is what clients read.",
]
checks = ["http-non-idempotent-method", "http-401-vs-403"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pending independent human review"

[[resources]]
title = "MDN: An overview of HTTP"
url = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview"

[[resources]]
title = "MDN: HTTP request methods"
url = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods"

[[resources]]
title = "RFC 9110: HTTP semantics"
url = "https://www.rfc-editor.org/rfc/rfc9110"
+++
## Why it matters

Every web application, API and microservice speaks HTTP. When the semantics are right, browsers, caches, proxies, retry libraries and other developers can all make correct decisions without reading your code. When they are wrong, you get duplicated payments, cached private data, and clients that cannot tell "try again" from "give up".

## Mental model

An HTTP exchange is a letter and a reply.

- The **request** says *what* to do (the method), *to what* (the target URL), adds **headers** (metadata such as `Content-Type`, `Authorization`, `Accept`), and optionally a **body**.
- The **response** says *how it went* (the status code), adds headers (such as `Content-Type`, `Cache-Control`, `Location`) and optionally a body.

Each request stands alone: the server does not remember previous requests unless something such as a cookie or token carries that context.

## How it works

**Methods carry promises.**

| Method | Typical use | Safe | Idempotent |
| --- | --- | --- | --- |
| `GET` | read a resource | yes | yes |
| `HEAD` | read headers only | yes | yes |
| `PUT` | replace a resource at a known URL | no | yes |
| `DELETE` | remove a resource | no | yes |
| `POST` | create, or trigger an action | no | no |
| `PATCH` | partially modify | no | not by definition |

*Safe* means the client does not request a change of state. *Idempotent* means sending the same request twice has the same intended effect as sending it once. That property is what makes automatic retries safe: if a `PUT` times out, sending it again cannot create a second copy. A `POST /payments` that times out is different: the first one may have succeeded, so a blind retry can charge twice. (APIs fix that with idempotency keys, covered at the advanced level.)

**Status codes are grouped by first digit.**

- `2xx` success: `200 OK`, `201 Created` (with a `Location` header for the new resource), `204 No Content`.
- `3xx` redirection or "use your cached copy": `301`, `302`, `304 Not Modified`.
- `4xx` the client must change something: `400` malformed request, `401` missing or invalid credentials, `403` authenticated but not allowed, `404` not found, `409` conflict with current state, `422` well-formed but invalid content, `429` too many requests.
- `5xx` the server failed: `500` unexpected error, `502`/`504` a gateway could not get a good or timely answer, `503` temporarily unavailable.

## Worked example

```http
POST /api/projects HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"name": "Apollo"}
```

```http
HTTP/1.1 201 Created
Location: /api/projects/42
Content-Type: application/json

{"id": 42, "name": "Apollo"}
```

Now Ada, who is signed in, tries to delete a project that belongs to another team:

```http
DELETE /api/projects/7 HTTP/1.1
Authorization: Bearer <Ada's valid token>
```

The server knows exactly who Ada is, so `401` is wrong. She is simply not permitted: `403 Forbidden`. If revealing that project 7 exists would itself leak information, many APIs return `404` instead.

## Common mistakes

- Using `GET` for actions that change data (`GET /delete?id=7`). Crawlers, prefetching and caches will trigger it.
- Returning `200` with `{"error": ...}` in the body. Clients, monitoring and caches look at the status code first.
- Returning `500` for invalid input. That tells clients the server is broken and invites retries.
- Confusing `401` (who are you?) with `403` (I know who you are, and no).

## In production

Load balancers and API gateways retry idempotent requests on connection failures; clients' HTTP libraries often do the same. Monitoring dashboards split error rates into `4xx` (client mistakes, often harmless) and `5xx` (your incidents). A service that labels its own failures as `400` hides outages from those dashboards; one that labels validation errors as `500` pages engineers at night for nothing.

## Trade-offs and limits

Not every operation fits the method table neatly. A "search" with a large filter object is safe but may not fit in a URL, so some APIs use `POST /search` and document that it is safe. `PATCH` can be idempotent ("set the name to Ada") or not ("add 5 to the balance") depending on the operation, so document which. Status codes are coarse: put a machine-readable error code and a human message in the body for details.

## Check your understanding

1. Why can a client retry a timed-out `PUT /users/1` but not a timed-out `POST /orders`?
   - Answer: repeating the `PUT` sets the same final state; repeating the `POST` may create a second order.
2. A request has no `Authorization` header and asks for a private resource. Which status fits?
   - Answer: `401`, because the client has not authenticated.
3. A JSON body is syntactically valid but the email field is not an email. Which family of codes?
   - Answer: `4xx`, typically `422` (FastAPI's default) or `400`.

## Practice

Pick an API you use (GitHub, Stripe or your own). For five endpoints, write down the method, whether it is safe and idempotent, and two status codes it can return with the reason for each. Then use `curl -i` to make one successful request and one deliberately failing request, and compare the status lines and headers.
