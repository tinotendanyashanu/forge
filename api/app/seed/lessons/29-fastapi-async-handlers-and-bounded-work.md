+++
slug = "fastapi-async-handlers-and-bounded-work"
skill = "fastapi"
topic = "async-handlers"
difficulty = "intermediate"
title = "FastAPI async handlers: event-loop safety and bounded work"
summary = "Choose async or sync handlers from the libraries they call, measure concurrency without timing guesses, and distinguish offloaded work from durable jobs."
estimated_minutes = 32
objectives = ["Identify work that blocks an event loop and choose an appropriate execution path.", "Explain the shared thread-pool capacity limit and why offloading still needs bounds.", "Distinguish a successful HTTP response from durable completion of background work."]
prerequisites = ["python-concurrency-models", "fastapi-dependency-lifetimes-and-overrides"]
misconceptions = ["Writing async def makes blocking SDK calls nonblocking.", "A plain helper function called by an async route is automatically moved to a worker thread.", "BackgroundTasks guarantees completion after a deploy or process crash."]
checks = ["fa-blocking-call-in-async-handler", "fa-background-task-durability", "fa-sync-threadpool-limit"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; concurrency examples executed; advisory second-model review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "FastAPI: Concurrency and async / await"
url = "https://fastapi.tiangolo.com/async/"
[[resources]]
title = "Starlette: Thread pool and capacity limiter"
url = "https://starlette.dev/threadpool/"
[[resources]]
title = "FastAPI: Background tasks and caveats"
url = "https://fastapi.tiangolo.com/tutorial/background-tasks/"
[[resources]]
title = "Python: asyncio timeouts and running code in threads"
url = "https://docs.python.org/3.12/library/asyncio-task.html"
+++
## Why it matters

A service handles many requests until one endpoint calls a blocking vendor SDK inside an async route. Other requests on that worker pause too. Moving the call to a thread can restore responsiveness, but an unbounded queue of waiting work can still exhaust connections, memory or the vendor's quota.

Prerequisites: Python concurrency models, await, resource ownership and basic FastAPI routes. The example uses the installed API requirements: FastAPI 0.162, Starlette 1.10, httpx 0.28 and the measured AnyIO limiter configuration. It uses in-process HTTP and synchronization events rather than external services or wall-clock speed assertions.

## Mental model

An event loop coordinates many waiting coroutines on a thread. A coroutine must yield control for other tasks to progress. Declaring a function async changes how it is called; it does not transform every operation inside it into a yielding operation.

FastAPI handles ordinary def endpoints through a thread-pool path. An async endpoint runs on the event loop and should await asynchronous I/O. A helper called directly from that endpoint executes where it is called. There is no automatic thread migration simply because the helper was defined with def.

Distinguish **request work**, **offloaded work** and **durable jobs**. Offloading changes where execution happens. Durability changes whether accepted work survives process failure. One does not imply the other.

## How it works

Use an async client for I/O that offers a well-supported async API. For a blocking SDK, use a def endpoint when the whole endpoint is naturally synchronous, or explicitly offload the blocking operation from an async endpoint. Do not call time.sleep, a synchronous HTTP client or a long CPU loop directly on the event-loop thread.

Starlette's AnyIO thread path uses a capacity limiter; its documented default is 40 tokens, shared with other thread-backed framework work. This is a configurable implementation default, not forty independent threads reserved for every endpoint. Python's asyncio.to_thread uses a different executor path, so its capacity is not automatically governed by that same limiter.

Thread offloading does not make CPU-heavy pure Python scale across cores on standard GIL-enabled CPython. Long computations often belong in a process pool or a separate worker service. Offloaded calls also need connection limits and deadlines. Cancelling the awaiting coroutine cannot generally kill an arbitrary blocking function already running in a thread.

## Worked example

Run this complete script from the API virtual environment. A gate deliberately keeps two async requests in progress until both have entered. The timeout only prevents a hung demonstration; it is not an assertion about request speed.

```python
import asyncio
import threading

import anyio
import httpx
from fastapi import FastAPI

app = FastAPI()
entered = asyncio.Event()
release = asyncio.Event()
in_flight = 0
peak = 0
loop_thread = None

@app.get("/work/{name}")
async def work(name: str):
    global in_flight, peak
    in_flight += 1
    peak = max(peak, in_flight)
    if in_flight == 2:
        entered.set()
    try:
        await release.wait()
        return {"name": name}
    finally:
        in_flight -= 1

@app.get("/sync")
def sync_probe():
    return {"offloaded": threading.get_ident() != loop_thread}

async def main():
    global loop_thread
    loop_thread = threading.get_ident()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://lesson") as client:
        tasks = [asyncio.create_task(client.get(f"/work/{name}")) for name in ["one", "two"]]
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
        finally:
            release.set()
        responses = await asyncio.gather(*tasks)
        print(peak, sorted(response.json()["name"] for response in responses))
        print((await client.get("/sync")).json()["offloaded"])
        print(anyio.to_thread.current_default_thread_limiter().total_tokens)

asyncio.run(main())
```

Output with the installed framework defaults:

```text
2 ['one', 'two']
True
40
```

Both handlers reached the gate while the other was waiting, demonstrating concurrency without assuming how many milliseconds the machine needs. The sync route ran on a different thread. The final value measures the limiter in this environment; if an application deliberately configures it, inspect that setting instead of treating the number as a language guarantee.

## Common mistakes

- Wrapping a blocking call in an async function without changing how the call executes. The event loop still blocks.
- Increasing thread capacity to hide a slow dependency while ignoring database connections or downstream rate limits.
- Starting thousands of independent tasks without a bound. A semaphore limits concurrency, but waiting tasks and their queued inputs still consume resources.
- Treating HTTP 202 as evidence that a background job finished. It usually means work was accepted, and the acceptance itself needs a durability contract.

## In production

Measure event-loop lag, request queue time, downstream latency and pool saturation separately. Low CPU utilization does not prove a service has spare capacity: it may be waiting for a bounded pool or a slow dependency. Set outbound timeouts and cap work before scarce resources are exhausted.

FastAPI BackgroundTasks runs in the application process after response handling. It is useful for suitable best-effort work, but a crash or deploy can lose unfinished work. A durable email, payment reconciliation or export workflow usually needs persisted job state and a worker. When a database change and job publication must agree, consider an outbox pattern rather than an uncoordinated dual write.

## Trade-offs and limits

Async I/O can handle many waits efficiently but requires compatible libraries and disciplined cancellation. Threads support blocking libraries but consume memory and must obey each library's thread-safety rules. Processes isolate CPU work but add serialization and memory overhead. Choose from workload and failure requirements, not the presence of async in a framework's name.

The in-process example does not measure socket behavior, worker-process balancing or real dependency latency. Load testing is a separate experiment with a defined workload and limits; do not infer production throughput from this two-request probe.

## Check your understanding

1. Why can a plain def endpoint be safe for a blocking SDK while calling the same def helper directly inside an async endpoint is unsafe?
   - Feedback: FastAPI offloads the endpoint invocation. A direct helper call does not pass through that framework boundary.
2. Why might increasing the AnyIO limiter from 40 to 200 make a database-backed service worse?
   - Feedback: more work may contend for fewer database connections, increase memory and queues, and overload the dependency without improving useful throughput.
3. What additional guarantee does a durable queue provide beyond moving a function to a thread?
   - Feedback: accepted work can be persisted and retried across process failure, subject to the queue's delivery and acknowledgment rules. Threads alone provide no such persistence.

The linked FORGE checks cover blocking calls, background-task durability and thread-pool limits. Use intermediate FastAPI assessments first, then advanced assessments for the capacity and failure cases.

## Practice

Create a scratch endpoint around a simulated blocking client. Implement a safe sync-endpoint version and an explicit-offload async version. Add a bounded number of outstanding operations and a controlled failure mode. Use events to show that unrelated async work can progress.

Acceptance criteria: no blocking client call runs on the event-loop thread, the concurrency bound is observable, failures release capacity, and the test does not assert exact elapsed milliseconds. Explain how the design changes when work must survive a deploy and how cancellation affects an already-running thread.
