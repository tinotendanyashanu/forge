+++
slug = "browser-origins-cors-and-csrf"
skill = "http"
topic = "browser-security"
difficulty = "intermediate"
title = "Browser security: origins, CORS, cookies and CSRF"
summary = "Distinguish sending a request from reading its response, configure explicit credentialed CORS, and protect cookie-authenticated actions against cross-site requests."
estimated_minutes = 35
objectives = ["Distinguish origin from site and explain why CORS is not authorization.", "Trace simple and preflighted cross-origin requests, including credentials.", "Choose layered CSRF defenses without relying on CORS or SameSite alone."]
prerequisites = ["http-requests-and-semantics", "http-caching-and-validation"]
misconceptions = ["A CORS error proves that the server did not receive the request.", "Access-Control-Allow-Origin: * can expose a credentialed response.", "Same-site and same-origin mean the same thing.", "CORS authenticates callers and prevents every CSRF attack."]
checks = ["http-cors-preflight", "http-samesite-lax-post", "http-cors-credentials-wildcard"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; middleware examples executed; browser verification recorded in P5_REPORT.md; independent AI review; no human subject-matter verification"
[[resources]]
title = "WHATWG Fetch Standard: CORS protocol"
url = "https://fetch.spec.whatwg.org/"
[[resources]]
title = "WHATWG HTML Standard: Origins and sites"
url = "https://html.spec.whatwg.org/multipage/browsers.html#origin"
[[resources]]
title = "MDN: Set-Cookie and SameSite"
url = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie"
[[resources]]
title = "OWASP: Cross-Site Request Forgery Prevention Cheat Sheet"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html"
[[resources]]
title = "Starlette: CORSMiddleware"
url = "https://starlette.dev/middleware/#corsmiddleware"
+++
## Why it matters

A frontend reports “blocked by CORS” after submitting a form. The backend still changed the record. Another team fixes a credentialed API by reflecting every incoming Origin header, accidentally granting arbitrary websites access to responses. Both mistakes treat browser response access as though it were server authorization.

Read HTTP semantics and caching first. You should know methods, headers and shared-cache variation. The executable example uses FORGE's FastAPI and Starlette stack. It checks middleware behavior; browser enforcement requires a real browser, which the practice task addresses separately.

## Mental model

For ordinary HTTP URLs, an **origin** consists of scheme, host and effective port. Changing any of these changes the origin. A **site** uses a different boundary based on scheme and registrable domain; sibling subdomains can be same-site while remaining cross-origin. SameSite cookie rules and same-origin response protections therefore answer different questions.

Separate three decisions: can the browser send the request, will it attach credentials, and may the calling script read the response? The server must separately authenticate the caller and authorize the action. CORS is a browser protocol for selectively allowing cross-origin response access. It does not stop a command-line client from calling the endpoint.

CSRF exploits credentials, usually cookies, that the browser attaches automatically to a request initiated by another site. The attacker may need only the action to occur, without reading the response. That is why response-access restrictions alone are insufficient.

## How it works

Some cross-origin requests use only CORS-safelisted methods and headers and can be sent without a preflight. A plain form submission is a familiar example. For a non-safelisted method, content type or header, the browser normally sends an OPTIONS preflight specifying the proposed method and header names. If permission is denied, it does not send the proposed request. Preflight permission can be cached, so not every later request needs a new OPTIONS exchange.

A fetch defaults to the `same-origin` credentials mode: credentials are included for same-origin requests and omitted cross-origin. To include credentials cross-origin, the script can request `credentials: "include"`, but cookie Domain, Path, Secure, SameSite and browser privacy policy still constrain which cookies are sent. That option does not override those policies.

To expose a response to a credentialed cross-origin fetch, the server must return an explicitly allowed origin and `Access-Control-Allow-Credentials: true`. Wildcard allow-origin is incompatible with this credential mode, even if a particular request happens to have no cookies. Use a fixed allowlist, and vary by Origin when responses dynamically select an allowed origin. Do not blindly reflect arbitrary origins.

An explicitly set `SameSite=Lax` cookie is generally withheld on a cross-site POST but can be sent during a top-level safe-method navigation. A GET endpoint that changes state therefore remains a bad design. Some browsers apply a temporary POST exception to recently set cookies when Lax is merely the default, so distinguish an explicit attribute from default behavior. `SameSite=None` requires Secure and permits cross-site use subject to other browser policy.

## Worked example

Run this complete script. These are mock origins using reserved example domains; TestClient does not resolve them or act as a browser. The POST route changes only in-memory demonstration state and deliberately omits authentication and CSRF checks so the final observation is visible.

Use the API virtual environment and dependencies described in the caching lesson. FastAPI defines the route, CORSMiddleware handles the protocol headers, and TestClient sends each request without enforcing browser policy. Follow the request, response and change counter first; learning the framework's full API is not required here.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.test"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
changes = []

@app.post("/change")
def change():
    changes.append("changed")
    return {"ok": True}

with TestClient(app) as client:
    allowed = client.options("/change", headers={
        "Origin": "https://app.example.test",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-token",
    })
    print(allowed.status_code, allowed.headers["access-control-allow-origin"])
    print(allowed.headers["access-control-allow-credentials"])
    print("Origin" in allowed.headers["vary"])
    denied = client.options("/change", headers={
        "Origin": "https://other.example.test",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-token",
    })
    print(denied.status_code, "access-control-allow-origin" in denied.headers)
    simple = client.post("/change", headers={"Origin": "https://other.example.test"})
    print(simple.status_code, len(changes), "access-control-allow-origin" in simple.headers)
```

Output:

```text
200 https://app.example.test
true
True
400 False
200 1 False
```

The allowed preflight returns explicit origin and credentials permission. The denied preflight would stop a browser from sending that proposed non-safelisted request. The final direct request reaches the route despite its disallowed origin, because this middleware does not reject every ordinary request. A browser can likewise send a safelisted cross-origin request while withholding the response from script. TestClient sees the response because it does not enforce CORS.

## Common mistakes

- Changing the client to `mode: "no-cors"` to obtain readable API data. An opaque response does not expose the desired response data to script.
- Requiring an authenticated cookie on the preflight itself. Cross-origin preflights do not carry the actual request's credentials; handle the protocol exchange before authorizing the actual operation.
- Checking a token's presence without validating its value and binding. An arbitrary string is not a CSRF defense.
- Treating sibling subdomains as equally trusted because they are same-site. A compromised sibling may still initiate requests with same-site cookies.

## In production

For cookie-authenticated state changes, use the framework's established CSRF protection: validate a secret token bound to the session or an appropriate signed double-submit design, and validate Origin or Referer according to a strict deployment policy. Fetch Metadata checks can provide another layer. Handle missing or special-origin cases deliberately instead of falling back to arbitrary acceptance.

Use Secure and HttpOnly where appropriate for session cookies; HttpOnly limits script access to the cookie, not authenticated actions from an XSS payload. Set a suitable SameSite policy, avoid state changes on GET, and keep ordinary authorization checks on every request. XSS can undermine CSRF defenses, so these controls complement rather than replace each other.

## Trade-offs and limits

Strict cookie policies can affect cross-site sign-in and embedded integrations. Explicitly inventory those flows instead of weakening every endpoint. A custom CSRF header helps because it requires preflight cross-origin, but permissive CORS or a same-origin script compromise can defeat that assumption.

Different browsers and privacy settings can block third-party cookies even when CORS is configured correctly. Debug credentials, cookie policy and response access separately. Command-line HTTP tests verify headers and server behavior; only browser tests demonstrate browser enforcement for a particular configuration.

## Check your understanding

1. A rejected preflight and an unreadable simple POST both show CORS errors. Which may have changed server state?
   - Feedback: the simple POST may have reached the route. The failed preflight normally prevents its proposed actual request from being sent.
2. Why can `app.example.test` and `api.example.test` need CORS while their cookies remain same-site?
   - Feedback: hosts differ, so origins differ, while the scheme and registrable domain can define the same site.
3. Would adding a valid session cookie to the sample route repair its CSRF vulnerability?
   - Feedback: no. Automatically attached credentials are what make CSRF possible. Protect the state-changing request as well as authenticating it.

The linked FORGE checks cover preflight, explicit Lax cookies and wildcard credential rules. The intermediate HTTP assessment introduces these concepts; the advanced assessment tests the credentialed wildcard case.

## Practice

Use two local origins on different ports and a browser. Record OPTIONS requests, actual POST requests, response-access errors and the server's change counter. Compare a safelisted POST with a JSON POST carrying a custom header, first allowing and then denying the calling origin.

Acceptance criteria: distinguish a blocked actual request from a sent request with an unreadable response. Add a session-bound CSRF token check and verify that an omitted or incorrect token cannot change state. Ports alone create different origins but generally not different sites; use distinct sites with controlled local HTTPS setup to test SameSite behavior. Explain what this local experiment does and does not prove about production cookie policies.
