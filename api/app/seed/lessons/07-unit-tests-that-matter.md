+++
slug = "unit-tests-that-matter"
skill = "testing"
topic = "test-design"
difficulty = "beginner"
title = "Unit tests that matter"
summary = "Choose test cases that catch real regressions, keep tests deterministic, and use fixtures without hiding what a test does."
estimated_minutes = 20
objectives = [
  "Select typical, boundary and invalid cases for a function and say what each protects.",
  "Remove non-determinism such as clock reads from tests.",
  "Use pytest fixtures with appropriate scope.",
]
prerequisites = ["tracing-program-state"]
misconceptions = [
  "High line coverage means the tests are good.",
  "A test that fails occasionally is a CI problem, not a test problem.",
  "Broader fixture scopes are always better because they are faster.",
]
checks = ["test-choosing-cases", "test-pytest-fixture-scope", "test-now-in-assertion"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; examples executed with pytest; pending independent human review"

[[resources]]
title = "pytest docs: How to use fixtures"
url = "https://docs.pytest.org/en/stable/how-to/fixtures.html"

[[resources]]
title = "Martin Fowler: Eradicating non-determinism in tests"
url = "https://martinfowler.com/articles/nonDeterminism.html"
+++
## Why it matters

Tests are how you change code without fear. A good test fails when behaviour breaks and passes otherwise; a bad test either misses real bugs or fails for reasons unrelated to the code, until people stop trusting the suite and ignore red builds. The difference lies mostly in which cases you choose and whether the test is deterministic.

## Mental model

A unit test is a small, repeatable experiment with three parts:

1. **Arrange** the inputs and environment.
2. **Act** by calling the code once.
3. **Assert** one behaviour about the result.

Each test should answer: *if this fails, what broke?* If you cannot say, the test is doing too much or too little.

## How it works

**Choosing cases.** For any function, think in categories rather than random examples:

- A **typical** case that represents normal use.
- **Boundaries**: the smallest and largest valid inputs, and the values just outside them.
- **Invalid** inputs and the exact error you expect.
- **Special values**: empty collections, zero, `None`, very long strings, Unicode.

**Determinism.** A test must give the same result every run. Common sources of flakiness are the clock, randomness, ordering of sets or dicts across processes, network calls, and shared state between tests. Make them inputs: pass a clock or a fixed timestamp, seed or inject the random generator, and use fakes for the network.

**Fixtures.** A pytest fixture provides a resource to tests that request it by name. Its default scope is `function`, so every test gets a fresh instance; `module` and `session` scopes share one instance across many tests, which is faster but couples tests through shared state.

## Worked example

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest


def apply_discount(price: Decimal, percent: int) -> Decimal:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return (price * (100 - percent) / 100).quantize(Decimal("0.01"))


@pytest.mark.parametrize(
    ("price", "percent", "expected"),
    [
        (Decimal("80.00"), 25, Decimal("60.00")),   # typical
        (Decimal("80.00"), 0, Decimal("80.00")),    # lower boundary
        (Decimal("80.00"), 100, Decimal("0.00")),   # upper boundary
        (Decimal("0.05"), 50, Decimal("0.02")),     # rounding: 0.025 -> 0.02 (banker's rounding)
    ],
)
def test_apply_discount(price, percent, expected):
    assert apply_discount(price, percent) == expected


@pytest.mark.parametrize("percent", [-1, 101])
def test_rejects_percent_outside_range(percent):
    with pytest.raises(ValueError):
        apply_discount(Decimal("10.00"), percent)


def create_order(user_id: int, now: datetime) -> dict:
    return {"user_id": user_id, "created_at": now}


def test_order_uses_the_given_time():
    fixed = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert create_order(1, now=fixed)["created_at"] == fixed
```

The rounding case documents a real decision: `Decimal.quantize` uses round-half-even by default, so 0.025 becomes 0.02. If the business wants half-up rounding, this test is where that requirement gets pinned down.

## Common mistakes

- Asserting on `datetime.now()` inside the test, which reads the clock a second time.
- Testing only the happy path.
- Several unrelated behaviours in one test, so a failure does not say what broke.
- Session-scoped fixtures holding mutable data that one test changes and another depends on.
- Deleting or silently retrying flaky tests instead of fixing their cause.

## In production

Teams run the fast unit suite on every commit and treat a flaky test as a bug with an owner. Parametrised tests document business rules (rounding, limits, error messages) in one readable table. CI runs tests in random order to surface hidden dependencies between them.

## Trade-offs and limits

Unit tests are fast and precise but cannot prove that components work together; you still need some integration tests against a real database and a few end-to-end checks. Injecting clocks and randomness adds parameters to your functions; that small cost is usually worth the determinism. Coverage tells you what ran, not what was checked.

## Check your understanding

1. Which cases would you add for a function that accepts ages 0 to 130?
   - Answer: a typical age, 0 and 130, -1 and 131 with the expected error, and a non-integer if the type allows it.
2. A test passes locally and fails once in twenty CI runs. What do you do first?
   - Answer: reproduce it by running it repeatedly and in random order, then look for time, ordering, shared state or network causes.
3. What is the default pytest fixture scope?
   - Answer: `function`.

## Practice

Write `slugify(title: str) -> str` that lowercases, trims, replaces runs of non-alphanumeric characters with a single hyphen, and strips leading and trailing hyphens. Before implementing it, write a parametrised test table with at least eight cases (including empty strings, only punctuation, Unicode letters and repeated separators). Then implement it and see which cases changed your design.
