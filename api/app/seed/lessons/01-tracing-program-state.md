+++
slug = "tracing-program-state"
skill = "programming-fundamentals"
topic = "control-flow"
difficulty = "beginner"
title = "Tracing program state"
summary = "Learn to predict exactly what a short program does by tracking names, values and the call stack step by step."
estimated_minutes = 18
objectives = [
  "Trace the value of every variable through loops, branches and function calls.",
  "Explain the difference between rebinding a name and mutating an object.",
  "Predict the effect of break and continue inside loops.",
]
prerequisites = []
misconceptions = [
  "Assigning to a function parameter changes the caller's variable.",
  "`b = a` makes a copy of a list.",
  "`break` skips only the current iteration.",
]
checks = ["pf-loop-continue-break", "pf-function-local-scope", "pf-alias-vs-copy"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; code examples executed; pending independent human review"

[[resources]]
title = "Python tutorial: More control flow tools"
url = "https://docs.python.org/3/tutorial/controlflow.html"

[[resources]]
title = "Python FAQ: rules for local and global variables"
url = "https://docs.python.org/3/faq/programming.html#what-are-the-rules-for-local-and-global-variables-in-python"

[[resources]]
title = "Python tutorial: Data structures"
url = "https://docs.python.org/3/tutorial/datastructures.html"
+++
## Why it matters

Most bugs are a mismatch between what you think the program does and what it actually does. Tracing is the skill of running the program in your head, one step at a time, and writing down the state as you go. It is how you read unfamiliar code, review a pull request, and find the line where reality diverges from your expectation. Debuggers help, but they only show you state; you still need a model of how state changes.

## Mental model

Think of a running program as three things:

1. **Names** that point at **objects**. In Python, `x = 5` does not put 5 "into" x. It makes the name `x` refer to an integer object whose value is 5.
2. **Frames**: each function call gets its own set of local names. When the call returns, its frame disappears.
3. **A current line**: the program executes one statement at a time, and control flow (`if`, `for`, `while`, `break`, `continue`, `return`) decides which line runs next.

A trace is simply a table: one row per step, one column per name.

## How it works

**Assignment rebinds a name.** `x = x * 2` computes a new object from the old value, then points `x` at it. Any other name that referred to the old object is unaffected.

**Mutation changes an object.** `items.append(4)` does not rebind `items`; it changes the list object itself. Every name that refers to that list sees the change. This is called aliasing.

**Function calls create new local names.** When you call `f(x)`, the parameter inside `f` is a new local name bound to the same object the caller passed. Rebinding the parameter inside the function never rebinds the caller's name. Mutating the object, however, is visible to the caller because both names point to the same object.

**Loops repeat a block.** `continue` jumps to the next iteration, skipping the rest of the current one. `break` leaves the loop immediately; no later elements are examined.

## Worked example

```python
def double_and_add(nums, extra):
    extra = extra * 2        # rebinds the local name only
    nums.append(extra)       # mutates the shared list
    return len(nums)

values = [1, 2]
bonus = 3
n = double_and_add(values, bonus)
print(values, bonus, n)
```

Trace it:

| Step | `values` (caller) | `bonus` | `nums` (local) | `extra` (local) |
| --- | --- | --- | --- | --- |
| before call | `[1, 2]` | `3` | – | – |
| call starts | `[1, 2]` | `3` | same list as `values` | `3` |
| `extra = extra * 2` | `[1, 2]` | `3` | same list | `6` |
| `nums.append(extra)` | `[1, 2, 6]` | `3` | same list | `6` |
| return | `[1, 2, 6]` | `3` | – | – |

The program prints `[1, 2, 6] 3 3`. The list changed because it was mutated through an alias; `bonus` did not change because only the local `extra` was rebound.

Now a loop:

```python
total = 0
for n in [4, 7, 10, 1]:
    if n > 8:
        break
    if n % 2 == 0:
        continue
    total += n
print(total)
```

4 is even, so `continue` skips it. 7 is added (`total` is 7). 10 is above 8, so `break` ends the loop and 1 is never examined. The output is `7`.

## Common mistakes

- **Treating assignment as copying.** `b = a` creates a second name for the same list. Use `a[:]` or `list(a)` for a shallow copy, and `copy.deepcopy` when nested objects must not be shared.
- **Expecting a function to rebind the caller's variable.** Return the new value instead and assign it in the caller.
- **Skipping steps while tracing.** Trace every iteration, even the "obvious" ones; bugs live in the iteration you skipped.
- **Confusing `break` and `continue`.** Say out loud which one leaves the loop.

## In production

Aliasing bugs are common in real systems: a function that "cleans" a request payload by mutating it changes the caller's data too; a default argument list (`def f(items=[])`) is shared across calls; a cached object is mutated by one request and seen by the next. Code reviewers catch these by tracing who else holds a reference to an object before approving a mutation.

## Trade-offs and limits

Mutation is not wrong: appending to a list in place is faster and uses less memory than building a new list each time. The trade-off is that shared mutable state makes code harder to reason about. Many teams prefer functions that return new values for data passed across module boundaries, and mutate freely only inside a function they fully control. Tracing by hand also has limits: for large programs, combine it with logging, debuggers and small experiments.

## Check your understanding

1. After `a = [1]; b = a; b = b + [2]`, what is `a`?
   - Answer: `[1]`. `b + [2]` builds a new list and rebinds `b`; `a` still refers to the original list.
2. After `a = [1]; b = a; b += [2]`, what is `a`?
   - Answer: `[1, 2]`. For lists, `+=` extends the existing object in place, so both names see the change.
3. In a `for` loop, which statement stops the loop entirely?
   - Answer: `break`.

The linked assessment questions check these objectives with scored answers.

## Practice

Write a function `remove_negatives(nums)` two ways: one that mutates the list it receives and returns nothing, and one that returns a new list and leaves the input unchanged. For each version, trace a call with `values = [3, -1, 2]` and write down `values` before and after the call. Then explain to yourself which version you would rather receive from a teammate, and why.
