+++
slug = "http-caching-and-validation"
skill = "http"
topic = "caching"
difficulty = "beginner"
title = "HTTP caching: storage, freshness and validation"
summary = "Separate permission to store from permission to reuse, validate cached representations with ETags, and keep personalized responses out of shared caches."
estimated_minutes = 30
objectives = ["Distinguish no-store, no-cache, private and freshness directives.", "Explain conditional GET and why a 304 response reuses a previously stored body.", "Choose cache keys and policies for public assets and personalized responses."]
prerequisites = ["http-requests-and-semantics"]
misconceptions = ["no-cache means a response cannot be stored.", "private means a response is encrypted or inaccessible to the user's device.", "A 304 response contains a fresh copy of the response body."]
checks = ["http-no-store-vs-no-cache", "http-cache-personalised", "http-etag-304", "http-vary-language"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; HTTP examples executed in process; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "RFC 9111: HTTP caching (storage, freshness and directives)"
url = "https://www.rfc-editor.org/rfc/rfc9111.html"
[[resources]]
title = "RFC 9110: Conditional requests and 304 semantics"
url = "https://www.rfc-editor.org/rfc/rfc9110.html"
[[resources]]
title = "MDN: HTTP caching guide"
url = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching"
[[resources]]
title = "Starlette: Static files"
url = "https://starlette.dev/staticfiles/"
+++
## Why it matters

A CDN makes a product page fast by reusing responses. The same policy on a user's account page can expose one person's data to someone else. Conversely, disabling every cache makes the origin do unnecessary work. Effective cache design starts by deciding which representation can be reused by which audience and for how long.

Read the HTTP semantics lesson first. You should recognize requests, response headers, status codes and GET. The executable example uses FORGE's installed FastAPI, Starlette and httpx test-client stack. It deliberately avoids implementing a general cache or conditional-header parser from scratch.

## Mental model

Separate three questions: **may this response be stored, may the stored representation be reused now, and how is it validated when reuse needs permission?** These are different decisions.

A private cache serves one user agent, such as a browser. A shared cache can serve many users, such as a CDN. Freshness is a protocol permission to reuse a stored response without contacting the origin. It is not proof that the underlying database has not changed. Validation asks whether the origin's current selected representation still matches the stored validator.

The cache key must describe the representation being requested. The URI and request method are a starting point; negotiated variants may also depend on request headers. Think about the audience as carefully as the URL.

## How it works

`Cache-Control: no-store` tells a compliant cache not to store the response. It does not erase every previously stored copy or make transport private. `no-cache` allows storage but requires successful validation before reuse. `private` prevents a shared cache from storing the response while allowing a private cache, subject to other directives. Encryption and access control remain separate responsibilities.

`max-age=60` gives a freshness lifetime of sixty seconds. A cache accounts for response age, including time already spent in an upstream cache; receiving a response does not always reset its age to zero. `s-maxage` can give a different shared-cache lifetime. Once stale, the response generally needs validation or replacement unless an applicable rule explicitly permits stale reuse.

`must-revalidate` forbids reuse of a stale response without successful validation, even when disconnected. It still permits reuse while fresh. This differs from `no-cache`, which requires validation before every reuse. The Age header helps downstream caches account for time already spent in caching; age calculation also accounts for transit and local residence time.

An ETag is an opaque validator supplied by the origin. A client holding a stored representation can send `If-None-Match` on GET. If the selected representation matches under the conditional-request rules, the server returns 304 without a representation body. The cache updates relevant metadata and uses its stored body. If it does not match, a normal 200 response supplies the current representation. Weak ETags can support cache validation; stronger comparison requirements apply to some other operations, including `If-Match`.

`Vary: Accept-Language` tells caches to consider that request header when selecting a stored variant. Without appropriate variation, a Spanish response might be reused for an English request. High-cardinality values can produce many separate cache variants, reducing hit rates and increasing storage. Vary is not a general privacy policy: varying on a cookie does not replace a deliberate decision about whether personalized content belongs in a shared cache at all.

## Worked example

Run this complete script from the API virtual environment. The middleware supplies a simple public-asset policy; Starlette handles file validators. TestClient does not implement a browser cache, so the second request deliberately performs validation even though the first response permits fresh reuse.

For a local FORGE checkout, save the script in a temporary file and run it with `api/venv/bin/python` after the API dependencies have been installed from `api/requirements.txt`. FastAPI creates the app, StaticFiles serves a local file, and TestClient sends in-process HTTP requests. Understanding those libraries is optional for following the status-and-body observations. A real browser may reuse a still-fresh stored response without a network request; this example deliberately exercises the conditional exchange.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

with TemporaryDirectory() as directory:
    Path(directory, "guide.txt").write_text("Cache me.\n", encoding="utf-8")
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=directory), name="assets")

    @app.middleware("http")
    async def asset_policy(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=60"
        return response

    with TestClient(app) as client:
        first = client.get("/assets/guide.txt")
        second = client.get("/assets/guide.txt", headers={"If-None-Match": first.headers["etag"]})
        third = client.get("/assets/guide.txt", headers={"If-None-Match": '"different-version"'})
        print(first.status_code, first.headers["cache-control"])
        print(first.text.strip())
        print(second.status_code, len(second.content))
        print(second.headers["etag"] == first.headers["etag"])
        print(third.status_code, third.text.strip())
```

Output:

```text
200 public, max-age=60
Cache me.
304 0
True
200 Cache me.
```

The body did not arrive again in the second response. A real cache needs the original body to satisfy the request after a 304. The mismatching validator receives a 200 with a body. The ETag is intentionally treated as opaque; application code should not infer business state from its spelling. File-validator generation here is framework behavior, not a recipe for generating validators for every dynamic API.

## Common mistakes

- Returning `public` on a personalized response merely because it uses GET. Method safety does not imply audience safety.
- Using `no-cache` when the requirement is “do not store.” Choose the directive for the required behavior.
- Omitting a representation-changing header from Vary, or varying on high-cardinality headers without considering cache fragmentation.
- Generating an ETag from unrelated metadata that can remain unchanged while the body changes. A validator must identify the selected representation according to its comparison strength.

## In production

Serve fingerprinted static assets with a policy matched to their immutability and deploy process. If an asset's bytes change, a new content-addressed URL makes old cached copies harmless. HTML and API responses often need shorter lifetimes or validation because their URLs remain stable while content changes.

For account data, choose a policy such as `private, no-cache` when browser storage plus validation is acceptable, or `no-store` when it is not. Do not rely on cookies or authentication headers alone to express the intended policy across every intermediary. Inspect actual CDN configuration, response headers and cache-hit behavior using two users with different data.

## Trade-offs and limits

Long freshness reduces latency and origin load but increases the period during which changed content may remain unseen. Validation saves transfer bytes but still adds a network round trip and may require origin computation. Stale-response extensions can improve availability but need an explicit tolerance for outdated content.

Cache invalidation is operational work. Purges can fail or take time, and invalidating an application cache does not automatically invalidate browser or CDN caches. Never make immediate authorization revocation depend solely on a long-lived cached response remaining fresh.

## Check your understanding

1. A cache holds a response with `no-cache`. Must it discard the body after every use?
   - Feedback: no. It may store the body, but must validate before reuse.
2. A browser receives a 304 but has no stored body. Why is returning an empty account page not a correct interpretation?
   - Feedback: 304 supplies no replacement representation. The cache needs a usable stored response; otherwise it must obtain the representation.
3. A localized endpoint uses the same URL for several languages. What does Vary solve, and what does it not solve?
   - Feedback: it distinguishes stored variants by specified request headers. It does not authenticate users or authorize shared storage of private data.

The linked FORGE checks cover directives, personalization, validation and language variants. Begin with the beginner HTTP assessment and progress to intermediate and advanced checks independently.

## Practice

Using a scratch app, serve a public document and a mock personalized account response with different cache policies. For the document, request once, validate with its ETag, then change the content and confirm that the old validator obtains the new representation. For this file example, append a line so the file length changes, making the change unambiguous for the server's metadata-based validator strategy.

Acceptance criteria: identify storage permission, freshness and validation behavior for each endpoint; record status and body presence for every request; keep personalized bodies out of a shared cache. As a transfer task, design English and Spanish variants and explain how the cache selects between them. Do not use a test client without a cache to claim browser freshness behavior has been tested.
