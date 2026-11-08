+++
slug = "python-functions-scope-and-closures"
skill = "python"
topic = "functions"
difficulty = "beginner"
title = "Python functions: contracts, scope and closures"
summary = "Design predictable function boundaries, understand definition-time defaults and call-time name lookup, and avoid hidden shared state."
estimated_minutes = 28
objectives = ["Separate a function's return contract from its mutations.", "Explain when default arguments are evaluated and allocate per-call state deliberately.", "Predict closure name lookup and construct callbacks with independent captured values."]
prerequisites = ["tracing-program-state", "python-objects-equality-and-copying"]
misconceptions = ["A mutable default argument is created fresh for every call.", "A closure freezes every referenced value when the function is created.", "Every method that changes an object returns the changed object."]
checks = ["py-mutable-default-argument", "py-sort-returns-none", "py-late-binding-closures"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; executable examples; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Python 3.12 tutorial: Defining functions and default arguments"
url = "https://docs.python.org/3.12/tutorial/controlflow.html#defining-functions"
[[resources]]
title = "Python 3.12 FAQ: Lambdas defined in a loop"
url = "https://docs.python.org/3.12/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result"
[[resources]]
title = "Python 3.12 language reference: Naming and binding"
url = "https://docs.python.org/3.12/reference/executionmodel.html#naming-and-binding"
+++
## Why it matters

A helper builds a response for each customer. Its default list accidentally retains messages from the previous call. Another helper registers three callbacks, but all three use the last customer's ID. These are failures to distinguish when an object is created from when a name is looked up.

Read the tracing and object-model lessons first. You should understand local names and shared mutable objects. Examples use Python 3.12 or later. The aim is to design functions that another engineer can call correctly without inspecting every implementation line.

## Mental model

A function has a **contract**: inputs, return value, mutations and failure conditions. A useful contract says whether the function owns its arguments or merely reads them. Returning a new sorted list and sorting a caller-owned list in place are different contracts even when the final ordering looks identical.

Keep three moments separate. At **definition time**, Python creates the function object and evaluates default argument expressions. At **call time**, it binds arguments to local parameter names. When the function executes, it looks up names according to the enclosing scopes. A callback may execute long after it was created, so call-time lookup matters.

A function with no explicit return value returns `None`. Some mutating methods deliberately return `None` to discourage confusing a mutation with a new-value computation. This convention is useful but not universal: `list.pop`, for example, mutates and returns the removed item. Read the contract rather than guessing from the method name.

## How it works

In `def collect(item, bucket=[]): ...`, the list is created once when that definition executes. Calls that omit `bucket` reuse the same list. Use a `None` default and allocate inside the body for independent per-call state. If `None` is itself a meaningful supplied value, use a separate sentinel object and test identity against it.

Python resolves names through local, enclosing function, module-global and built-in scopes. Assignment inside a function normally makes that name local throughout its body. Reading such a name before it is bound raises `UnboundLocalError`; Python does not silently fall back to a same-named global. `global` and `nonlocal` declare which existing scope an assignment targets, but neither is a substitute for a clear state-ownership design.

A closure retains access to bindings in an enclosing function. It does not automatically take a value snapshot. Functions created in one loop can all refer to the same loop variable binding. A factory call creates a new local binding for each callback; binding a loop value as a default argument is another deliberate technique. Both capture references to objects, so a captured mutable dictionary can still change later.

## Worked example

Run the complete script:

```python
def collect_bad(item, bucket=[]):
    bucket.append(item)
    return bucket

print(collect_bad("first"))
print(collect_bad("second"))

def collect(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket

print(collect("first"), collect("second"))

def callbacks_bad():
    return [lambda: customer_id for customer_id in [10, 20, 30]]

def callback_for(customer_id):
    def run():
        return customer_id
    return run

print([callback() for callback in callbacks_bad()])
print([callback_for(i)() for i in [10, 20, 30]])
callbacks = [callback_for(i) for i in [10, 20, 30]]
print([callback() for callback in callbacks])

amounts = [30, 10, 20]
result = amounts.sort()
print(amounts, result)
print(sorted([30, 10, 20]))
```

Output:

```text
['first']
['first', 'second']
['first'] ['second']
[30, 30, 30]
[10, 20, 30]
[10, 20, 30]
[10, 20, 30] None
[10, 20, 30]
```

The bad default is shared across omitted-argument calls. The corrected function allocates independently, but still intentionally mutates a list supplied by its caller. If that mutation is unwanted, make a copy or return a new list and say so in the contract.

The immediate factory calls and the delayed callbacks both return independent IDs. Each invocation of the factory owns a separate local `customer_id` binding. The broken callbacks all consult the binding from their shared comprehension scope after its last iteration. Finally, `sort()` changes `amounts` and returns `None`; `sorted()` constructs a new list.

## Common mistakes

- Replacing a missing collection with `bucket or []`. This also replaces a deliberately supplied empty list, changing the mutation contract. Check `is None` when only omission should allocate.
- Thinking the callback bug is specific to lambdas. A nested `def` can close over the same shared binding.
- Adding `global` to silence a scope error without deciding who owns state. Return the new value or encapsulate the state where possible.
- Testing a helper once. Shared defaults often appear correct on the first call and fail on subsequent calls.

## In production

Callbacks appear in UI handlers, job scheduling and asynchronous task setup. Test them after registration has finished, not only while constructing them. A task can retain a large object graph through its closure, extending the lifetime of request data or credentials. Pass the smallest stable inputs needed for the work.

Keep business calculations separate from external effects. A price calculation that returns a result is easy to test; writing invoices or sending emails requires explicit retries and failure handling. Repeated calls are safe only if the contract says how effects behave. A function being small does not make its effects idempotent.

## Trade-offs and limits

A closure is a compact way to package behavior with state. A class can make longer-lived state and reset operations clearer. Explicit parameters make dependencies visible, while injecting every minor value can make simple code cumbersome. Choose a boundary another caller can understand.

Copying inputs can protect the caller but adds allocation and only protects nested values if the chosen copy strategy does. A pure function contract is valuable where independence matters; internal mutation of an owned local accumulator is often both clear and efficient.

## Check your understanding

1. Why is a tuple default usually safer than a list default, and what if that tuple contains a list?
   - Feedback: a tuple cannot replace its element references, but nested mutable objects can still be shared and changed. Inspect the whole graph.
2. A caller passes an empty list to the corrected `collect`. Which list receives the item?
   - Feedback: the caller's list. The `None` guard allocates only for an omitted or explicitly `None` argument.
3. A factory captures a dictionary. Does creating a separate binding freeze the dictionary contents?
   - Feedback: no. The closure retains a reference. Copy the required value or use an immutable snapshot if later changes must be invisible.

The linked FORGE checks cover shared defaults, mutating return contracts and late-bound closures. Begin with the beginner assessment and use intermediate Python assessments for closure reasoning.

## Practice

Write a factory that creates one callback per order. Each callback returns that order's ID and the discount rate that applied when the callback was registered. Change the source order dictionary and global discount afterward, then execute all callbacks. Their results must retain the registration-time ID and rate despite those later changes.

Acceptance criteria: callbacks retain the intended ID and rate, two registrations do not share mutable accumulators, and an explicit caller-provided result list follows your documented mutation contract. Add repeated-call tests, not just a first-call test. Explain which values you copied, which objects you still share, and when a whole-object snapshot would be necessary.
