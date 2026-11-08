+++
slug = "reliable-tests-time-state-and-order"
skill = "testing"
topic = "reliability"
difficulty = "beginner"
title = "Reliable tests: time, shared state and execution order"
summary = "Turn flaky conditions into controlled inputs, test exact boundaries without sleeping, and investigate order-dependent failures without hiding them behind retries."
estimated_minutes = 30
objectives = ["Inject a controllable clock and test expiry boundaries exactly.", "Identify hidden dependencies on shared state, order, environment and scheduling.", "Use reproducible failure evidence to repair a flaky test rather than merely rerunning it."]
prerequisites = ["unit-tests-that-matter"]
misconceptions = ["Sleeping longer makes a timing test deterministic.", "A test passing alone proves the implementation is correct.", "Automatically retrying a failing test fixes its reliability problem."]
checks = ["test-now-in-assertion", "test-flaky-investigation", "test-shared-state-order"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; pytest examples executed in varied orders and environments; advisory review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "pytest: Flaky tests"
url = "https://docs.pytest.org/en/stable/explanation/flaky.html"
[[resources]]
title = "pytest: Fixtures and teardown"
url = "https://docs.pytest.org/en/stable/how-to/fixtures.html"
[[resources]]
title = "Python 3.12: Time and monotonic clocks"
url = "https://docs.python.org/3.12/library/time.html"
[[resources]]
title = "Python 3.12: datetime and timezone-aware values"
url = "https://docs.python.org/3.12/library/datetime.html"
+++
## Why it matters

A cache test sleeps for exactly its time-to-live, then checks expiry. It passes locally and fails under load. Another test passes alone but sees an old record when run after a different test. Repeated green reruns do not remove these defects; they make the evidence harder to trust.

Read the test-design lesson first. You should know fixtures, boundary cases and ownership of mutable state. This lesson starts with a small controllable cache, then extends the method to concurrent and integration tests. The executable example requires only pytest and Python's standard library.

## Mental model

A reliable test is a controlled experiment. List every input that can influence the result, including inputs not shown in the function signature: the clock, environment, random generator, filesystem, database contents and other tasks. Make the important ones explicit or isolate them.

Test order is not a valid data dependency unless the test framework explicitly models a larger ordered scenario. One test should not prepare the database for another independent test. Likewise, a fixed random seed is useful evidence about one sequence, not proof that all orderings or schedules are safe.

Separate product time from test runtime. A business expiry boundary can be advanced through an injected clock instantly. A timeout in the test harness can prevent a hang; that is different from asserting that production must finish within an exact number of milliseconds on a busy CI runner.

## How it works

Inject the clock operation, not just one timestamp, when behavior reads time at several moments. A manual clock lets the test advance from just before expiry to exactly expiry without waiting. State the equality rule: this cache expires when current time is greater than or equal to its deadline.

Use timezone-aware values for shared wall-clock timestamps. For elapsed intervals within a running process, a monotonic clock avoids wall-clock jumps; it is not a portable timestamp to persist across process restarts. The cache below uses aware datetimes to make boundary behavior readable. A production in-process TTL cache can instead inject a monotonic seconds source with the same boundary contract.

Function-scoped fixtures give each case independent objects. Wider scopes can still be useful for expensive infrastructure, but test data should be separated or reset deliberately. Teardown must execute after failures. In database integration tests, understand whether transactions, background workers and multiple connections actually share the isolation boundary you assume.

## Worked example

Save as `test_cache_lifetime.py` and run pytest. No sleeps, network calls or live clock reads occur:

```python
from datetime import datetime, timedelta, timezone

import pytest

class ManualClock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

class Cache:
    def __init__(self, ttl_seconds, clock):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.clock = clock
        self.entries = {}

    def put(self, key, value):
        self.entries[key] = (value, self.clock() + self.ttl)

    def get(self, key):
        entry = self.entries.get(key)
        if entry is None:
            return None
        value, deadline = entry
        if self.clock() >= deadline:
            del self.entries[key]
            return None
        return value

@pytest.fixture
def resources():
    clock = ManualClock()
    return clock, Cache(10, clock)

@pytest.mark.parametrize("elapsed, expected", [
    (0, "ready"), (9, "ready"), (10, None), (11, None),
])
def test_expiry_boundary(resources, elapsed, expected):
    clock, cache = resources
    cache.put("job", "ready")
    clock.advance(elapsed)
    assert cache.get("job") == expected

def test_missing_key_has_no_previous_test_state(resources):
    _, cache = resources
    assert cache.get("job") is None
```

Expected result: **five tests pass**. Every parameterized case receives a new fixture. Exactly ten seconds is expired by contract; the test does not depend on how long Python or CI took to execute. Missing and expired values both return None in this small API, so storing None as a meaningful distinguishable value would require a different return contract.

## Common mistakes

- Reading the real clock again in the expected value. The two observations need not be identical and can cross a boundary.
- Increasing a sleep until the test usually passes. Scheduling delays remain variable, and the suite becomes slower.
- Seeding one global random generator while unrelated tests consume it. Inject a test-owned generator when the sequence matters.
- Comparing unordered results as ordered sequences when ordering is not part of the product contract. Conversely, sorting in a test can hide a missing required product order: sorting returned events before comparing them would conceal an API that incorrectly returns them out of chronological order.

## In production

When a test flakes, record its exact failing assertion, seed, environment, test order and relevant task/resource events. Reproduce it alone and with likely predecessors. A test passing alone but failing after another often points to leaked globals, environment variables, files, mock state or database data; it can also expose a real product isolation bug.

For concurrency, coordinate the intended interleaving with events, barriers or controlled promises rather than hoping sleeps create it. Still retain broader stress tests when useful, because one deterministic schedule is not exhaustive. A temporary quarantine should have an owner, explanation and expiry; blanket retries can conceal a broken release signal.

## Trade-offs and limits

Controllable clocks and fakes improve precision but can diverge from real systems. Keep some integration checks for actual driver, clock-conversion and persistence behavior. Do not make the whole suite depend on a single live external service just to avoid maintaining a small adapter contract.

Rerunning a failure is diagnostic evidence, not a repair. Some products intentionally retry transient failures; tests should then verify that retry contract with controlled failures and limits. That is different from the test harness silently accepting a later pass after an unexplained failure.

## Check your understanding

1. Why is exactly-expired behavior easier to test with a manual clock than with sleep?
   - Feedback: the test chooses the precise logical time, independent of scheduling and elapsed runner time.
2. Why can changing test order reveal a defect even if every test passes independently?
   - Feedback: an earlier test may leave shared state behind, or the product may incorrectly reuse state between supposedly independent operations.
3. Does a fixed random seed prove that a concurrent implementation is race-free?
   - Feedback: no. It reproduces some generated inputs, not every task interleaving. Control important schedules and use other evidence as needed.

The linked FORGE checks cover clock comparisons, flaky-failure investigation and shared-state ordering. Start with beginner testing assessments and use intermediate assessments for suite-level diagnosis.

## Practice

Add cache replacement and deletion behavior. Test a replacement immediately before the old value would expire, zero TTL and an explicit policy for negative TTL. Run the tests in reverse order and under different hash seeds and timezones. These cache cases should remain identical: hash seeds do not change dictionary insertion-order guarantees. Seed variation is especially useful when a larger fixture or algorithm depends on unordered set traversal.

Acceptance criteria: no real sleeps or live-clock expected values, exact expiry equality is documented, tests own their mutable state, and every failure identifies a behavior. As a transfer exercise, design an event-controlled test for two concurrent writers and explain why reproducing one lost-update schedule is stronger than merely running the race twenty times and getting lucky.
