+++
slug = "test-doubles-fixtures-and-patching"
skill = "testing"
topic = "test-doubles"
difficulty = "intermediate"
title = "Test doubles: fixtures, contracts and patching the right name"
summary = "Replace external boundaries deliberately, enforce useful call contracts, and keep fixture state independent without testing private implementation choreography."
estimated_minutes = 32
objectives = ["Choose a stub, fake or interaction mock from the behavior being tested.", "Patch the name the consumer actually looks up.", "Use function-scoped fixtures and autospec while recognizing what neither can prove."]
prerequisites = ["unit-tests-that-matter", "python-functions-scope-and-closures"]
misconceptions = ["Patching the original module always changes every imported reference.", "An unrestricted mock proves that a real API accepts the same calls.", "A session-scoped mutable fake is safe because each test has its own function."]
checks = ["test-pytest-fixture-scope", "test-mock-where-to-patch", "test-overspecified-mock", "test-mock-without-autospec"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; multi-file examples executed with pytest; advisory second-model review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Python unittest.mock: Where to patch"
url = "https://docs.python.org/3.12/library/unittest.mock.html#where-to-patch"
[[resources]]
title = "Python unittest.mock: Autospeccing"
url = "https://docs.python.org/3.12/library/unittest.mock.html#autospeccing"
[[resources]]
title = "pytest: Fixtures and scope"
url = "https://docs.pytest.org/en/stable/how-to/fixtures.html"
[[resources]]
title = "pytest: Monkeypatching attributes and environments"
url = "https://docs.pytest.org/en/stable/how-to/monkeypatch.html"
+++
## Why it matters

A billing test patches a gateway function, yet still reaches the real gateway. Another test stays green after the production code starts passing an invalid keyword argument. Both suites contain mocks; neither has isolated the right boundary with a useful contract.

Read the unit-test design and Python functions lessons first. You should understand imports, function calls, fixtures and assertions. The example uses the API environment's pytest and the standard library. It deliberately contains no real network client or credentials, so even the demonstration of a wrong patch cannot contact a provider.

## Mental model

A test double stands in for a collaborator. A **stub** supplies chosen responses, a **fake** implements a simpler working version, and an **interaction mock** checks selected calls. These describe roles, not rigid Python classes: one Mock object can supply values and record interactions.

Choose the boundary from the test's question. A pricing rule should usually be asserted through the resulting amount. A payment retry rule may need an interaction assertion because making two charges instead of one is itself the bug. Do not assert every internal helper call just because the mocking library can observe it.

A fixture controls setup, ownership and cleanup. Its scope determines which tests share an instance. A function-scoped fixture starts each test with independent state; a broader scope intentionally creates a shared resource whose mutation and reset policy must be understood.

## How it works

Python names are bindings to objects. With `from price_gateway import lookup_price`, billing receives its own binding to the function object. Replacing price_gateway.lookup_price afterward does not rewrite billing.lookup_price. Patch the consumer's looked-up name. With a different import style, such as importing the module itself, the lookup path changes; read the consuming code before choosing a patch target. If billing instead used `import price_gateway`, the lookup would be `billing.price_gateway.lookup_price`, an attribute on the shared module object.

`create_autospec` checks calls against a callable's signature. `spec_set` can also prevent invented attributes on the double. These controls catch useful mismatches but do not verify response semantics, remote schema compatibility, authentication or network failures. A correctly shaped call can still have the wrong business meaning.

For reusable external boundaries, a small adapter can make the application-facing contract explicit. Unit tests can replace that adapter; integration or contract tests then check the actual adapter against the provider or a controlled representative service. Avoid mocking an entire ORM chain simply to reproduce its private method sequence.

## Worked example

Create these three files together in a disposable directory. The first is `price_gateway.py`; its real path is intentionally disabled in this lab.

```python
from decimal import Decimal

def lookup_price(sku: str) -> Decimal:
    raise RuntimeError("Real gateway disabled in this lesson")
```

Save the second as `billing.py`:

```python
from price_gateway import lookup_price

def quote(sku: str, quantity: int):
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return lookup_price(sku) * quantity
```

Save the third as `test_billing.py`, then run pytest in that directory:

```python
from decimal import Decimal
from unittest.mock import create_autospec

import pytest
import billing
import price_gateway

@pytest.fixture
def catalog(monkeypatch):
    double = create_autospec(price_gateway.lookup_price,
                             return_value=Decimal("12.50"))
    monkeypatch.setattr(billing, "lookup_price", double)
    return double

def test_quote(catalog):
    assert billing.quote("sku-1", 2) == Decimal("25.00")
    catalog.assert_called_once_with("sku-1")

def test_new_fixture_has_no_prior_calls(catalog):
    catalog.assert_not_called()
    assert billing.quote("sku-2", 1) == Decimal("12.50")

def test_patching_original_module_misses_consumer(monkeypatch):
    double = create_autospec(price_gateway.lookup_price, return_value=Decimal("1.00"))
    monkeypatch.setattr(price_gateway, "lookup_price", double)
    with pytest.raises(RuntimeError, match="Real gateway disabled"):
        billing.quote("sku-1", 1)
    double.assert_not_called()

def test_autospec_rejects_invented_argument(catalog):
    with pytest.raises(TypeError):
        catalog("sku-1", currency="imaginary")
```

Expected result: **four tests pass**. The wrong-target test passes because it deliberately asserts that the original disabled path is still reached. It demonstrates the faulty isolation technique safely, rather than allowing a test to make a real call. The two catalog tests receive separate doubles and call histories because fixture scope defaults to function. Monkeypatch restores each replaced binding after its test.

## Common mistakes

- Asserting a private sequence of helper calls when only the final quote matters. Harmless refactoring then breaks tests without changing behavior.
- Treating autospec as a data validator. It checks the Python call contract, not whether a vendor returns an amount in the correct currency.
- Sharing a mutable fake across the entire suite without resetting its data and call history between tests.
- Replacing too much at once. If every function is mocked, the test may only prove that the mocks agree with one another.

## In production

Define which tests may use real external services, and keep ordinary unit tests isolated from them. A stubbed success must not accidentally require a developer's credentials. For failure cases, simulate explicit timeout, rejection and malformed-response outcomes at the adapter boundary.

Keep fakes honest with shared contract cases when practical. A fake repository that silently accepts duplicate keys can make tests pass while the production database rejects the same operation. Integration tests should exercise important constraints and transaction behavior against the real database engine. Resource fixtures should use try/finally or context managers so failed assertions still release connections and restore process state.

## Trade-offs and limits

A narrow mock is quick to create but can hide integration assumptions. A fake can make multi-step scenarios clearer but is additional code that can drift. Real integration tests offer stronger evidence at a higher setup and runtime cost. Match the evidence to the boundary rather than choosing one style for everything.

Interaction checks are appropriate when the interaction itself is contractual: one charge, a required audit event, or a bounded number of expensive lookups. They become brittle when they merely mirror incidental implementation choices. Be able to explain what user-visible failure each assertion prevents.

## Check your understanding

1. Why does replacing price_gateway.lookup_price not affect this billing module?
   - Feedback: billing already holds a separate imported binding. The production call looks up billing.lookup_price.
2. Would autospec detect a validly shaped call that uses the wrong customer's SKU?
   - Feedback: no. The signature accepts it. Assert the relevant business input or output when that distinction matters.
3. When can a session-scoped fixture be reasonable?
   - Feedback: for a deliberately shared expensive resource with controlled isolation, such as a service process while each test owns its data. Sharing mutable per-test results is a different contract.

The linked FORGE checks cover scope, patch targets, over-specified interactions and unrestricted mocks. Start with intermediate testing assessments; beginner and advanced checks are reached at their corresponding skill levels.

## Practice

Use an adapter contract `get_rate(base: str, target: str) -> Decimal` and test a quote calculation with a stubbed rate, a timeout and an invalid response. Choose one externally meaningful interaction to assert and explain why the rest of the implementation is free to change.

Acceptance criteria: no unit test reaches a real service; every test starts with independent fake state; invalid call shapes fail; and changing an internal helper's organization does not break behavior-focused assertions. Add a small adapter contract test that would catch a fake/real disagreement about missing currency pairs.
