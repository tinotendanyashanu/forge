+++
slug = "choosing-data-structures"
skill = "programming-fundamentals"
topic = "data-structures"
difficulty = "beginner"
title = "Choosing data structures from the operations you need"
summary = "Model sequences, membership, lookup and priority before choosing a list, set, dictionary, deque or heap."
estimated_minutes = 30
objectives = ["Choose a structure from ordering, duplicate and lookup requirements.", "Build an ordered deduplicating work queue and explain its invariants.", "Explain when a heap helps and why its backing list is not sorted."]
prerequisites = ["tracing-program-state"]
misconceptions = ["A set preserves the arrival order of its elements.", "A heap is a completely sorted list.", "A container makes compound operations safe across workers."]
checks = ["pf-set-membership", "pf-alias-vs-copy", "pf-priority-structure", "pf-leaderboard-design"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; executable examples; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Python 3.12 tutorial: Data structures"
url = "https://docs.python.org/3.12/tutorial/datastructures.html"
[[resources]]
title = "Python 3.12 collections: deque"
url = "https://docs.python.org/3.12/library/collections.html#collections.deque"
[[resources]]
title = "Python 3.12 heapq: priority queues"
url = "https://docs.python.org/3.12/library/heapq.html"
+++
## Why it matters

A support service receives ticket IDs in arrival order. Retries can submit the same ID twice. The service must process each ID once during this batch, preserving the first arrival order. Choosing a set alone loses the ordering requirement; choosing a list alone makes repeated membership searches expensive as the batch grows. Start by describing the required behavior, then choose structures to support it.

Prerequisite: you can trace a loop and distinguish mutation from rebinding. The examples use Python 3.12 or later and only the standard library. This lesson builds beyond the tracing lesson by choosing a representation for a problem rather than following a representation already chosen by someone else.

## Mental model

A data structure is a set of promises about storage and operations. Ask four questions before writing code: must order be retained, may values repeat, how will items be located, and how will items be removed? Your answers often rule out more choices than performance measurements do.

A **list** represents a sequence: position matters and duplicates are allowed. A **set** answers membership questions while retaining each equal value once; it offers no insertion-order guarantee. A **dictionary** associates a unique key with a value and preserves insertion order in modern Python. Overwriting an existing dictionary key updates its value without moving its position. A **deque** supports a queue with efficient operations at both ends. A **heap** repeatedly exposes the smallest priority without sorting every item.

The container and its elements are separate objects. Putting a mutable ticket dictionary into two lists does not create two independent tickets. Representation decisions include ownership as well as ordering and lookup.

Start with sequences and membership. The heap and multi-worker discussion are extensions: return to them after you can explain the ordered deduplication example without running it.

## How it works

For the ticket service, use a set to remember IDs already accepted and a deque for pending work. Keep the invariant: every ID added to the queue is already in the set, and no ID is added twice. Process an arrival by checking membership first, then adding to both structures. This order makes the invariant easy to inspect in a single-threaded loop.

Sets and dictionaries require **hashable** keys. A hash helps locate candidates, and equality distinguishes the matching key. A tuple of immutable IDs is a useful composite key; a list is not hashable. Hashability requires a stable hash during the key's lifetime and equal keys must have equal hashes. Do not use a mutable business attribute as an object's hash.

If all you need is a one-time ordered deduplicated list, a dictionary can remove the need for a separate queue and set. If IDs may be retried after completion, however, a set that remembers every accepted ID forever implements the wrong policy. Define whether deduplication lasts for a batch, a time window or the lifetime of a job.

For priority scheduling, a min-heap returns the item with the smallest priority first. Store a sequence number after the priority to make equal-priority jobs deterministic. The sequence number also prevents Python from trying to compare arbitrary payload objects when priorities tie. Heap insertion and removal take logarithmic time; inspecting the minimum is constant time. Read the next complexity lesson for the assumptions behind those descriptions.

## Worked example

Run this complete script:

```python
from collections import deque
from heapq import heappop, heappush

arrivals = ["T3", "T1", "T3", "T2", "T1"]
seen = set()
pending = deque()
for ticket_id in arrivals:
    if ticket_id not in seen:
        seen.add(ticket_id)
        pending.append(ticket_id)

processed = []
while pending:
    processed.append(pending.popleft())
print(processed)
print(sorted(seen))  # sort only to make this display deterministic

jobs = []
for sequence, (priority, ticket_id) in enumerate([(2, "T3"), (1, "T1"), (1, "T2")]):
    heappush(jobs, (priority, sequence, ticket_id))
print([heappop(jobs)[2] for _ in range(len(jobs))])
```

Output:

```text
['T3', 'T1', 'T2']
['T1', 'T2', 'T3']
['T1', 'T2', 'T3']
```

The first output proves that duplicates were removed without sorting away arrival order. The second is a presentation choice, not the iteration order of a set. The third shows two scheduling decisions: priority 1 precedes priority 2, and sequence breaks the tie between T1 and T2. The heap's internal array need not be globally sorted; only removal promises the next minimum.

## Common mistakes

- Converting a sequence to a set and then assuming its original order can be recovered. Retain order separately or use an ordered dictionary strategy.
- Calling the first item in a heap the oldest job. It is the smallest by the chosen comparison, which might represent urgency rather than time.
- Using a heap for arbitrary rank queries. Finding the item at rank 5,000 or updating a user's score needs more design than repeatedly looking at the minimum.
- Removing from the front of a large list for every queued item. The remaining entries must shift. A deque expresses this queue operation directly.

## In production

An in-memory set disappears on restart and is private to one process. Two workers can both observe that an ID is absent and accept it. Durable deduplication usually needs a database uniqueness constraint or an atomic operation in a shared store, plus a defined retry policy. A container's individual method guarantees do not make a multi-step business operation atomic.

Bound the pending queue and the deduplication window. Otherwise a popular service can exhaust memory while correctly deduplicating every arrival. Measure queue age as well as queue length: a small queue can still contain a stuck, very old job. For a priority queue, decide whether low-priority work can starve and whether priorities should age upward over time.

## Trade-offs and limits

A set adds memory overhead to avoid repeated scans. For a handful of IDs, a list can be simpler and fast enough. A heap is useful when new items arrive between removals; sorting once can be simpler for a fixed batch processed in full. A database index is often more appropriate than holding a whole production leaderboard in process memory.

Choose the simplest representation that preserves the required invariants, then profile the expensive operation. A familiar container with the wrong behavior is not a useful optimization.

## Check your understanding

1. A customer asks for unique product IDs sorted by price. Is a set enough? Explain what additional information is required.
   - Feedback: a set handles uniqueness but not the price lookup or ordering. Retain a mapping to prices and sort by them, or use a query that provides the required order.
2. A retry should run again after a successful earlier attempt. What is wrong with the example's lifetime-long `seen` set?
   - Feedback: it records all accepted jobs, including completed ones. Change the deduplication policy, not just the container.
3. Would a heap alone efficiently support a leaderboard with arbitrary score updates and rank lookups?
   - Feedback: no. It supports minimum access well; arbitrary updates and ranking require additional indexing or another structure.

Use the lesson's linked FORGE checks for membership, aliasing and priority design. The assessment button draws from this skill at the displayed difficulty; use later skill assessments for the intermediate and advanced checks. Reading and practice are not mastery evidence.

## Practice

Build a local job dispatcher from arrivals containing an ID and a priority. The policy is first arrival wins: ignore every later duplicate, even if it carries a higher priority. Process accepted jobs by priority, with arrival order as the tie-breaker. Test empty input, repeated IDs with different priorities and two distinct IDs with equal priority. State the deduplication policy before coding.

Acceptance criteria: each accepted ID appears once; equal-priority jobs retain first-arrival order; changing a duplicate's priority does not replace the first arrival. As a transfer exercise, explain how your design changes if users may reprioritize an existing job. A useful answer names both the lookup operation and how obsolete heap entries will be handled.
