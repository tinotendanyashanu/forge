+++
slug = "timeouts-retries-idempotency"
skill = "distributed-systems"
topic = "partial-failure"
difficulty = "intermediate"
title = "Timeouts, retries and idempotency"
summary = "How to call other services safely when any call can fail halfway: bounded timeouts, retries with backoff and jitter, idempotency keys and circuit breakers."
estimated_minutes = 25
objectives = [
  "Explain why a timeout does not tell you whether an operation happened.",
  "Retry safely with limits, exponential backoff and jitter, at one layer only.",
  "Make operations idempotent so retries cannot apply them twice.",
]
prerequisites = ["http-requests-and-semantics"]
misconceptions = [
  "A timed-out request did not happen.",
  "More retries always make a system more reliable.",
  "Idempotency is only a property of GET requests.",
]
checks = ["ds-timeout-unknown-outcome", "ds-retry-amplification", "ds-circuit-breaker"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; example run on CPython 3.12; pending independent human review"

[[resources]]
title = "Amazon Builders' Library: Timeouts, retries and backoff with jitter"
url = "https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/"

[[resources]]
title = "Amazon Builders' Library: Making retries safe with idempotent APIs"
url = "https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/"

[[resources]]
title = "Martin Fowler: Circuit breaker"
url = "https://martinfowler.com/bliki/CircuitBreaker.html"

[[resources]]
title = "Google SRE book: Addressing cascading failures"
url = "https://sre.google/sre-book/addressing-cascading-failures/"
+++
## Why it matters

As soon as one service calls another over a network, a new kind of failure appears: the call might succeed, fail, or do something you cannot observe. Payments charged twice, orders lost, and outages that spread from one slow dependency to every service upstream all come from handling this badly. These patterns are the everyday tools for handling it well.

## Mental model

A remote call has three outcomes, not two: **success**, **failure**, and **unknown**. A timeout or dropped connection is "unknown": the request may never have arrived, may have been processed with the response lost, or may still be running. The safe design question is always: *if I send this again, what happens?*

- **Timeouts** bound how long you wait, so a slow dependency cannot hold your resources forever.
- **Retries** turn many transient failures into successes, but only if repeating the operation is safe.
- **Idempotency** makes repeating safe: doing the operation twice has the same effect as doing it once.
- **Circuit breakers** stop calling a dependency that is clearly failing, so you fail fast instead of piling up waiting requests.

## How it works

**Timeouts.** Every outbound call needs one: a connect timeout and an overall request timeout, chosen from the dependency's real latency (for example a little above its p99) and from your own deadline. If your API must answer in 2 seconds, a 5-second timeout to a dependency is meaningless. Pass the remaining deadline down the call chain where you can.

**Retries.** Retry only errors that are likely transient (timeouts, connection resets, 503, 429 with `Retry-After`), never validation errors. Cap the attempts (often 2 or 3), wait longer each time (**exponential backoff**), and randomise the wait (**jitter**) so thousands of clients do not retry in lock-step. Retry at **one layer** only: if the browser, the gateway, the API and the database client each make up to three attempts, one failing call becomes 81 attempts (3 × 3 × 3 × 3) on the struggling dependency. Retry budgets (for example "retries may add at most 10% extra load") cap amplification across a fleet.

**Idempotency.** GET, PUT and DELETE are idempotent by HTTP semantics if implemented correctly; POST is not. For operations such as "charge card" or "create order", the client generates an **idempotency key** and sends it with every attempt. The server stores the key with the result in the same transaction as the effect; a repeat with the same key returns the stored result instead of acting again. Message consumers do the same with message ids, because at-least-once delivery means duplicates will arrive.

**Circuit breakers.** Track recent failures for a dependency. Past a threshold the breaker **opens**: calls fail immediately or use a fallback. After a cool-down it goes **half-open** and lets a few trial calls through; success **closes** it again.

## Worked example

A retry helper with capped exponential backoff and full jitter, and an idempotent "charge" handler:

```python
import random, time

class Transient(Exception):
    pass

def call_with_retries(fn, attempts=3, base=0.1, cap=2.0):
    for attempt in range(attempts):
        try:
            return fn()
        except Transient:
            if attempt == attempts - 1:
                raise
            time.sleep(random.uniform(0, min(cap, base * 2 ** attempt)))  # full jitter

charges: dict[str, dict] = {}  # idempotency key -> stored result (a table in real life)

def charge(idempotency_key: str, amount: int) -> dict:
    if idempotency_key in charges:
        return charges[idempotency_key]  # repeat: return the original result
    result = {"charged": amount, "id": f"ch_{len(charges) + 1}"}
    charges[idempotency_key] = result   # store with the effect, atomically in a database
    return result

flaky = iter([Transient(), Transient(), None])
def attempt():
    outcome = next(flaky)
    if outcome:
        raise outcome
    return charge("order-123-payment", 4200)

print(call_with_retries(attempt))         # {'charged': 4200, 'id': 'ch_1'}
print(charge("order-123-payment", 4200))  # same result, no second charge
```

In a real service the key check and the insert must be one transaction with a unique constraint on the key, so two concurrent attempts cannot both pass the check.

## Common mistakes

- No timeout at all, so a hung dependency exhausts threads or connections.
- Retrying non-idempotent operations, such as POST without an idempotency key.
- Retrying at every layer, multiplying load during an outage.
- Retrying immediately with no backoff or jitter, creating synchronised waves.
- Treating a timeout as a failure and telling the user "payment failed" when it may have succeeded; instead, check the status or retry with the same key.

## In production

Instrument retries and timeouts as metrics: a rising retry rate is an early warning. Prefer failing fast with a clear error over queueing work that will time out anyway. Load-shed at the edge when overloaded. Give optional features (recommendations, avatars) fallbacks so a broken dependency degrades the page instead of breaking checkout. Test these paths: inject latency and errors in staging and confirm that breakers open and recover.

## Trade-offs and limits

Short timeouts free resources quickly but cause spurious failures for slow-but-healthy calls; long timeouts do the reverse. Retries improve success rates for transient blips but add load exactly when a dependency is struggling. Idempotency keys require storage and a retention period. Circuit breakers need tuning; too sensitive and they open on noise, too lax and they never help. None of these patterns gives exactly-once execution across systems; they give at-least-once delivery with idempotent effects, which is usually what you actually need.

## Check your understanding

1. A payment API call times out. Did the charge happen?
   - Answer: Unknown. It may or may not have been processed; retry with the same idempotency key or query the payment status.
2. Why add jitter to backoff?
   - Answer: To spread retries from many clients over time instead of having them all retry at the same instants.
3. Three layers each retry three times. How many attempts can one user request cause at the bottom layer?
   - Answer: Up to 27 if each layer makes three attempts (3 × 3 × 3), which can overload a failing dependency.

## Practice

Build a tiny HTTP service with an endpoint that randomly sleeps or returns 503. Write a client that calls it with no timeout, then add a timeout, then retries with backoff and jitter, and record the success rate and the load on the server in each case. Finally, add an idempotency key to a POST endpoint backed by a database table with a unique constraint, and prove with concurrent requests that each key creates exactly one record.
