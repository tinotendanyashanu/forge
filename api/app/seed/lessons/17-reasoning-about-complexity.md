+++
slug = "reasoning-about-complexity"
skill = "programming-fundamentals"
topic = "complexity"
difficulty = "intermediate"
title = "Reasoning about time and space complexity"
summary = "Count growing work, include preprocessing and memory, and distinguish average, worst-case and amortized costs before optimizing."
estimated_minutes = 30
objectives = ["Derive time and auxiliary-space bounds for lookup inside a loop.", "Distinguish worst-case, average-case and amortized claims.", "Choose a queue or membership representation without hiding setup costs."]
prerequisites = ["choosing-data-structures"]
misconceptions = ["Every nested loop is quadratic.", "A hash lookup is guaranteed constant time.", "Amortized constant time means every operation takes the same time."]
checks = ["pf-membership-in-loop", "pf-bfs-pop-front", "pf-amortised-append"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; executable examples; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "CPython 3.12 list implementation (growth and shifting)"
url = "https://github.com/python/cpython/blob/3.12/Objects/listobject.c"
[[resources]]
title = "CPython 3.12 set implementation (hash probing)"
url = "https://github.com/python/cpython/blob/3.12/Objects/setobject.c"
[[resources]]
title = "Python 3.12 collections: deque performance"
url = "https://docs.python.org/3.12/library/collections.html#collections.deque"
+++
## Why it matters

A nightly import checks every incoming account against an allowlist. It finishes quickly with a hundred rows and misses its deadline with a million. The important question is how work grows with input size, not how fast a single laptop runs today's sample. Complexity analysis helps predict which change will still help next year.

Read the data structures lesson first. You should know list membership, set membership and queues. The examples are scoped to CPython 3.12 or later and fixed-size integer keys; hashing a very long string or comparing large user-defined objects adds costs that the simple model does not count.

## Mental model

Name each independent input size. Let **n** be incoming records and **m** the allowlist length. Count a useful unit of work, such as key comparisons. An expression like O(nm) describes an upper bound on growth once constant factors and small terms are ignored. It does not predict milliseconds.

If m is fixed at 20 by a product rule, an O(nm) algorithm is linear in n under that rule. If both sizes can grow together, treating m as a constant hides a scaling problem. State your assumptions next to the bound.

Space complexity needs the same care. Count **auxiliary space**, the extra storage needed beyond inputs, and say whether you include the returned output. An algorithm returning n records needs O(n) space for that output even if its temporary working memory is constant.

## How it works

A list membership search compares entries until it finds a match or reaches the end. For n missing records against an m-item list, that is nm comparisons. Constructing a set from m distinct fixed-size keys takes O(m) expected time and O(m) space. Then n expected constant-time lookups give O(n + m) expected time overall. Include the construction cost even if it is on a different line.

Hash-table claims are typically **expected** or average-case claims under ordinary hash distribution assumptions. With pathological collisions, building an m-item set can take O(m²) time and one lookup can take O(m). Repeated resizing alone does not establish that worst case; growth costs are amortized. A list's O(m) worst-case scan is more predictable, though usually slower for repeated large membership checks.

**Worst-case** describes a bound for the most expensive permitted input. **Average-case** needs a distribution of inputs or an explicit hashing assumption. **Amortized** analysis spreads occasional expensive operations across a sequence without assuming a random input. A dynamic array append can copy many references during a resize, but the growth strategy makes a long sequence of appends O(n) overall, or O(1) amortized per append. It does not make the slowest append constant time.

Nested syntax is insufficient to infer a bound. If an outer loop visits groups and an inner loop visits each group's records exactly once, total work is proportional to the total number of records. Conversely, one visible loop can be quadratic when each iteration copies a growing list or removes its first element.

## Worked example

This script counts equality comparisons instead of using noisy wall-clock timing:

```python
def filter_slow(records, allowed):
    comparisons = 0
    accepted = []
    for record in records:
        for candidate in allowed:
            comparisons += 1
            if record == candidate:
                accepted.append(record)
                break
    return accepted, comparisons

def filter_fast(records, allowed):
    allowed_ids = set(allowed)
    return [record for record in records if record in allowed_ids]

print(filter_slow([9, 10], [1, 2, 3]))
print(filter_slow([9, 10, 11, 12], [1, 2, 3, 4, 5, 6]))
print(filter_fast([3, 9, 1, 3], [1, 2, 3]))

def model_shifted_references(n):
    return sum(range(n))

print(model_shifted_references(4), model_shifted_references(8))
```

Output:

```text
([], 6)
([], 24)
[3, 1, 3]
6 28
```

Doubling both list sizes multiplies comparisons by four in this all-misses case. The fast version preserves order and duplicate records because it changes only the membership representation, not the output policy. Returning the same values is a correctness condition; improving the bound does not excuse a semantic change.

The final numbers count references shifted by repeatedly removing the first item of a list: n−1, then n−2, down to zero. Their sum is n(n−1)/2. In a breadth-first graph traversal, replace that list queue with a deque. With adjacency lists, expected constant-time visited-set operations and one queue insertion per vertex, traversal takes O(V + E) time and O(V) auxiliary space. Scanning an adjacency matrix has different costs.

## Common mistakes

- Rebuilding a set inside the records loop. That repeats setup n times and can restore O(nm) work.
- Calling a sort O(n) because it is one function call. Library calls still perform work; a general comparison sort commonly has O(n log n) time.
- Using a short timing run to prove a complexity bound. Measurements reveal behavior at tested sizes, while analysis explains growth under assumptions.
- Ignoring output size. Producing every pair from two lists requires nm output pairs; no data structure removes that requirement.

## In production

Use analysis to choose experiments, then measure representative data and tail latency. A larger set can reduce CPU while exhausting a worker's memory. A streaming import may need bounded batches, a database join or a disk-backed index instead of loading all allowed IDs into every worker.

Amortized performance can hide latency spikes. If a latency-sensitive handler occasionally resizes a large list, the total throughput may look healthy while a few requests breach their deadline. Preallocation in a suitable language, batching or moving work off the request path may help. Measure the actual allocation and copying costs before adding complexity.

## Trade-offs and limits

Big-O ignores cache locality, network calls and constants. For a ten-element allowlist, a list may be entirely adequate. For a remote database, reducing query count can matter far more than shaving comparisons in local code. Also distinguish batch cost from repeated-query cost: preprocessing pays off only when enough future queries reuse it, and that reused index must stay current.

Complexity analysis is an explanation of resource growth. It is not a universal ranking of implementations or permission to optimize a component that does not dominate the workload.

## Check your understanding

1. An allowlist has m entries and is queried once. Does constructing a set guarantee less total work?
   - Feedback: no. Both construction and a worst-case list scan are linear in m; allocation and hashing can make the set more expensive for one query.
2. An outer loop visits ten groups whose lengths sum to n. Is the inner record-processing loop O(n²)?
   - Feedback: not if each record is visited once and the per-record work is bounded. Count total visits rather than indentation.
3. Why does amortized O(1) append not promise a constant worst-case response time?
   - Feedback: a resize can copy existing references during one append; the bound averages that cost across the sequence.

The linked FORGE checks cover lookup inside a loop, queue costs in BFS and amortized append. Start with the intermediate assessment; advanced checks appear in advanced assessments for this skill.

## Practice

Implement allowlist filtering with a list and a prebuilt set. Verify identical results for empty inputs, duplicates, all matches and all misses. Measure sizes 100, 1,000 and 10,000, including set construction. Record input sizes, result count and elapsed time; keep timing assertions out of correctness tests.

Acceptance criteria: derive bounds in both n and m, explain the memory difference, and identify a workload where the simpler list is reasonable. Extend the exercise to breadth-first traversal and compare front removal from a list with deque removal. Explain why a chain-shaped graph can conceal the list queue problem while a wide frontier exposes it.
