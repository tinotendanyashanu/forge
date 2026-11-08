+++
slug = "fastapi-dependency-lifetimes-and-overrides"
skill = "fastapi"
topic = "dependencies"
difficulty = "intermediate"
title = "FastAPI dependencies: composition, lifetime and test overrides"
summary = "Build a request-scoped dependency graph, release resources reliably, and replace the correct callable in isolated tests."
estimated_minutes = 32
objectives = ["Trace shared sub-dependencies and request-local caching.", "Define resource acquisition and cleanup with yield without hiding transaction failures.", "Override the registered dependency callable in tests and restore the override afterward."]
prerequisites = ["fastapi-validation-and-dependencies", "python-functions-scope-and-closures"]
misconceptions = ["A cached dependency is a singleton shared by all requests.", "Patching a module name necessarily replaces a callable already registered with Depends.", "Cleanup after yield is always a safe place to commit work that determines request success."]
checks = ["fa-dependency-caching", "fa-db-session-dependency", "fa-dependency-override"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; examples executed and advisory second-model review recorded in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "FastAPI: Dependencies and sub-dependencies"
url = "https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/"
[[resources]]
title = "FastAPI: Dependencies with yield"
url = "https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/"
[[resources]]
title = "FastAPI: Testing dependencies with overrides"
url = "https://fastapi.tiangolo.com/advanced/testing-dependencies/"
+++
## Why it matters

An endpoint and its authorization helper both request a database session. If each creates an independent session accidentally, the request can observe different transactions or waste scarce connections. A test may also appear isolated while the original dependency still opens a real connection. The useful abstraction is a graph of required capabilities with an explicit resource lifetime.

Read the request-validation lesson and Python functions lesson first. You should understand functions as objects, exception handling and request/response flow. Run the complete example with the API virtual environment and installed requirements. Its store is a dictionary so lifecycle behavior can be observed without any database or external account. The example is validated with FastAPI 0.162 and Starlette 1.10.

## Mental model

A dependency describes what a callable needs before it can do its job. FastAPI resolves those requirements recursively. An endpoint can require a repository, the repository can require a session, and authorization can require the current principal. This graph makes shared requirements visible instead of repeating setup in every route.

The dependency cache normally belongs to one request. Multiple consumers of the same dependency can receive the same resolved value. This is not application-wide caching, and it does not turn a request-specific identity or session into a safe global singleton.

Separate acquisition, useful work and cleanup. Opening a resource and returning it does not define whether the business operation should commit or roll back. Those are transaction semantics that the service must decide deliberately.

## How it works

`Depends` receives a callable, not its result. For a shared sub-dependency with default caching, the framework can reuse its resolved value during that request. `use_cache=False` requests fresh resolution at that dependency use. Sub-dependencies keep their own caching settings; it is not a general instruction to disable every application cache.

A dependency with yield acquires a resource, yields it to consumers, then performs cleanup in a finally block. Exceptions can pass back through the yield boundary. Do not swallow them accidentally and claim success. Prefer a context manager supplied by the resource library rather than inventing partial cleanup rules for connections or files.

Cleanup timing depends on dependency scope, framework version and response lifetime. Modern FastAPI distinguishes function/request scopes, and streaming responses can outlive the endpoint function. Do not assume a commit failure after the response has already been sent can change its status. Complete transaction work that determines success before committing the success response; cleanup can then release the session reliably. Use the framework documentation for the exact version and scope you deploy.

For tests, `app.dependency_overrides` maps the original registered callable to a replacement callable. Reassigning a module variable after a route has captured the original callable is not equivalent. Always restore overrides after the test, including when an assertion fails, so later tests do not inherit a fake identity or repository.

## Worked example

Run this entire script. Both direct and nested consumers ask for the same store dependency:

```python
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

app = FastAPI()
events = []

def get_store():
    events.append("open")
    try:
        yield {"source": "real"}
    finally:
        events.append("close")

def nested_store(store=Depends(get_store)):
    return store

@app.get("/report")
def report(left=Depends(get_store), right=Depends(nested_store)):
    return {"shared": left is right, "source": left["source"]}

@app.get("/fail")
def fail(store=Depends(get_store)):
    raise HTTPException(409, "Example conflict")

def fake_store():
    events.append("fake-open")
    try:
        yield {"source": "fake"}
    finally:
        events.append("fake-close")

with TestClient(app) as client:
    data = client.get("/report").json()
    print(data["shared"], data["source"])
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_store] = fake_store
    try:
        data = client.get("/report").json()
        print(data["shared"], data["source"])
    finally:
        app.dependency_overrides = previous_overrides
    print(client.get("/fail").status_code)
print(events)
```

Output:

```text
True real
True fake
409
['open', 'close', 'fake-open', 'fake-close', 'open', 'close']
```

The two graph paths share one store per request, and the fake replaces both paths because they reference the registered callable. The failing route still releases its resource. TestClient waits for the in-process request lifecycle here; this observation is not a universal claim about when every streaming response performs cleanup.

## Common mistakes

- Creating a session in module scope and returning it to every request. A shared mutable session is not a connection pool and generally cannot safely host unrelated concurrent transactions.
- Passing a request-owned session to a background task that outlives the request. Give longer-lived work its own resource scope and pass stable identifiers instead.
- Overriding the wrong wrapper or a newly constructed callable that is not the dependency's registered identity.
- Leaving overrides installed on a reused app after a failed test. Treat override state as a resource that needs cleanup too.

## In production

Use dependencies to compose authentication, authorization and resource access, while keeping their purposes distinct. A repository dependency does not authorize every lookup it performs. Scope queries or policy checks to the authenticated principal at the appropriate trusted boundary.

Session factories and pools may be long-lived; individual sessions and transactions usually are not. Match synchronous or asynchronous database clients to the execution model and the library's threading rules. A request-local cache does not itself guarantee thread affinity for a synchronous session. Keep transactions short and avoid holding a database connection while waiting for an unrelated remote API.

## Trade-offs and limits

A dependency graph centralizes repeated setup but can become difficult to inspect if it hides too much business behavior. Keep dependencies focused on capabilities and policy, and leave domain operations visible in the service layer. Overriding a repository makes unit tests fast but cannot prove the real SQL or connection lifecycle works; retain integration coverage.

Streaming, cancellation and background execution create different ownership boundaries. Choose scopes deliberately and test both successful and exceptional paths. Do not solve a cleanup timing problem by making every resource global.

## Check your understanding

1. Why does the fake replace both consumers even though only one override entry is added?
   - Feedback: both paths resolve the same original callable through the dependency graph, with request-local reuse.
2. Why can a session factory be application-scoped while a session should not be shared between all requests?
   - Feedback: the factory allocates independently owned sessions; one session carries transaction and mutable state that unrelated requests must not accidentally share.
3. Why is a commit after yield risky if its failure determines whether a request succeeded?
   - Feedback: depending on scope/version, the response may already be sent. Resolve critical transaction success before sending a success response.

The linked FORGE checks cover shared sub-dependencies, database-session ownership and test overrides. Use intermediate FastAPI assessments first and advanced assessments for session design.

## Practice

Add a repository dependency and a principal dependency to a scratch endpoint. Override each independently and test success, denial and an exception during the domain operation. Record acquisition and release events without logging credentials.

Acceptance criteria: shared consumers use one request-local resource, separate requests acquire separate resources, cleanup runs on errors, and overrides never leak to later tests. As a transfer task, design a streaming endpoint and a durable background job that each need data access; explain which resources they own and when those resources may be released.
