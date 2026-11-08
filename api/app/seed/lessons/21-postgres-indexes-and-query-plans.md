+++
slug = "postgres-indexes-and-query-plans"
skill = "sql"
topic = "indexing"
difficulty = "intermediate"
title = "PostgreSQL indexes: from predicates to execution plans"
summary = "Design an index for a concrete access pattern, inspect estimates and actual work, and account for write cost and pagination behavior."
estimated_minutes = 35
objectives = ["Choose B-tree column order from equality, range and ordering requirements.", "Read EXPLAIN ANALYZE without treating estimates as milliseconds.", "Explain when a sequential scan, expression index or keyset cursor is appropriate."]
prerequisites = ["sql-querying-joins-and-nulls", "reasoning-about-complexity"]
misconceptions = ["Creating an index guarantees that PostgreSQL will use it.", "Planner cost numbers are measured milliseconds.", "Any index containing a column is equally useful for filtering on it."]
checks = ["sql-composite-index-order", "sql-expression-index", "sql-seq-scan-low-selectivity", "sql-offset-vs-keyset", "sql-unused-index"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; PostgreSQL examples executed; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "PostgreSQL 16: Multicolumn indexes"
url = "https://www.postgresql.org/docs/16/indexes-multicolumn.html"
[[resources]]
title = "PostgreSQL 16: Using EXPLAIN"
url = "https://www.postgresql.org/docs/16/using-explain.html"
[[resources]]
title = "PostgreSQL 16: Indexes on expressions"
url = "https://www.postgresql.org/docs/16/indexes-expressional.html"
[[resources]]
title = "PostgreSQL 16: LIMIT and OFFSET"
url = "https://www.postgresql.org/docs/16/queries-limit.html"
+++
## Why it matters

A tenant's recent events page returns twenty rows, yet gets slower as the events table grows. A limit bounds the output; it does not necessarily bound the work needed to find and order those rows. An index helps when its ordering fits the query's actual access pattern.

Read the SQL querying and complexity lessons first. You should understand filtering, ordering, output grain and the difference between result size and work performed. This lesson uses PostgreSQL 16 behavior. Newer versions may add access strategies, so evaluate the actual plan on the version you deploy.

## Mental model

A B-tree index maintains searchable ordered keys pointing toward table rows. It is like a separate access path, not a faster replacement for the table. PostgreSQL chooses a plan by estimating the work of candidate paths from statistics, table sizes and configured costs.

Think of a composite index as lexicographic ordering. An index on `(tenant_id, created_at, id)` groups keys by tenant, then time, then ID. Constraining tenant equality lets the engine navigate a contiguous tenant range and continue through time order. Filtering only by time may require much more scanning in PostgreSQL 16 because the leading tenant key is unconstrained.

Indexes also have a maintenance cost. Inserts and relevant updates must maintain them, and indexes consume storage and cache space. “Index every column” is neither a capacity plan nor a workload analysis.

## How it works

Start with the full query: equality predicates, range predicates, requested ordering, output columns and limit. For a B-tree, equality restrictions on leading keys and a range on the next key often tightly bound the scan. Later indexed keys can filter entries without necessarily narrowing the scanned interval as much. Index ordering can satisfy `ORDER BY` when the ordering and constraints align; reverse scans can supply the reverse direction for this example's uniformly reversed sort.

`EXPLAIN` shows estimates without executing the query. `EXPLAIN (ANALYZE, BUFFERS)` executes it and adds actual timing, rows, loops and buffer activity. Cost units are planner units based on settings such as sequential-page and random-page costs, not milliseconds. A node's reported actual row count is per loop; inspect loops before comparing the total work of a repeated inner scan. Parent timings include child work, so summing every timing double-counts.

A sequential scan can be cheaper when a predicate selects much of the table, especially if scattered index lookups would fetch many heap pages anyway. Tiny tables may also be scanned sequentially. A mismatch between estimated and actual rows suggests investigating statistics and data distribution before forcing a plan.

An expression predicate needs an applicable access path. An ordinary index on `email` does not generally provide indexed lookup for `lower(email) = ...`; an index on that expression can. Its usefulness still depends on selectivity and costs. An index-only scan additionally depends on index coverage and heap visibility; covering columns alone do not guarantee zero heap access.

## Worked example

Run all statements together in a scratch database. Temporary tables are discarded by rollback:

```sql
BEGIN;
CREATE TEMP TABLE lesson_events (
    id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    created_at timestamptz NOT NULL,
    email text NOT NULL
);
INSERT INTO lesson_events
SELECT n, n % 100,
       TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * INTERVAL '1 second',
       'User' || n || '@example.test'
FROM generate_series(1, 20000) AS n;
ANALYZE lesson_events;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM lesson_events
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 3;

CREATE INDEX lesson_events_recent ON lesson_events (tenant_id, created_at, id);
ANALYZE lesson_events;
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM lesson_events
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 3;

SELECT id FROM lesson_events
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 3;

SELECT id FROM lesson_events
WHERE tenant_id = 7
  AND (created_at, id) < (TIMESTAMPTZ '2026-01-01 05:28:27+00', 19707)
ORDER BY created_at DESC, id DESC LIMIT 3;

CREATE INDEX lesson_events_email_lower ON lesson_events (lower(email));
ANALYZE lesson_events;
SELECT id FROM lesson_events WHERE lower(email) = 'user123@example.test';
ROLLBACK;
```

The first result query returns IDs `19907, 19807, 19707`. The cursor query returns `19607, 19507, 19407`; its timestamp is the last row's sort value from the previous page. The email query returns `123`.

Compare the two plans rather than expecting identical plan text or timings across machines. In the supplied dataset, the composite index offers an ordered route to the tenant's first few rows and avoids a separate sort when that route is selected. Confirm the selected path and work with your own output; a planner choice is an observation, not part of SQL's result guarantee.

## Common mistakes

- Dropping the unique tie-breaker from a pagination cursor. Equal timestamps can cause skipped or repeated rows.
- Expecting `OFFSET 100000` to skip work for free. The engine generally still computes or walks past the preceding rows.
- Forcing index scans to make a demonstration look successful. Investigate estimates and selectivity first.
- Running `EXPLAIN ANALYZE` on a production write without realizing that it executes the write. A rollback does not undo every possible external effect.

## In production

Observe slow queries with realistic tenant sizes and parameter distributions. A plan suitable for a small tenant may be poor for a very large one. Keep statistics current and examine buffer work alongside latency; cache warmth can make two equivalent runs look very different.

Adding an index to a live large table needs an operational plan. PostgreSQL's concurrent index build reduces blocking of ordinary writes but has extra work and caveats, and cannot run inside a transaction block. Test disk capacity, failure cleanup and the migration procedure. The temporary-table example uses an ordinary build because it has no concurrent production traffic.

## Trade-offs and limits

Keyset pagination efficiently continues from an ordered key but does not naturally jump to arbitrary page numbers. Concurrent insertions, deletions or updates can change later pages unless a stable snapshot or application contract addresses them. An index makes lookup faster; it does not supply a consistency guarantee.

Expression indexes add write work and bind a query to an expression and its semantics, including collation behavior. Remove unused indexes only after considering rare operational queries and constraints. A unique index may enforce correctness even if it is rarely chosen as a read path.

## Check your understanding

1. Why can an index on `(tenant_id, created_at)` help a tenant-specific recent-events query more than one on `(created_at, tenant_id)`?
   - Feedback: the leading equality key isolates the tenant before navigating its ordered times. The alternative may inspect entries belonging to many tenants.
2. A query selects 80% of a table. Is a sequential scan evidence of failure?
   - Feedback: no. Reading most heap pages in order may be cheaper than many index-directed visits.
3. Why does a cursor need both time and ID even if the index already contains both?
   - Feedback: the query's continuation condition must describe the full unique ordering; index contents cannot repair an incomplete cursor predicate.

The linked FORGE assessments cover composite and expression indexes, selectivity, unused indexes and pagination. Start at intermediate SQL; the advanced assessment checks the operational trade-offs.

## Practice

Extend the dataset with a tenant holding half the rows. Compare a selective tenant query with the large tenant's unbounded export. Record plan type, estimated and actual rows, buffers and whether a sort occurs. Do not assert exact timings or force a particular scan.

Acceptance criteria: every index proposal names the query it serves and its write/storage cost. Implement two pages with tied timestamps and verify no duplicates or omissions on the unchanged dataset. Explain what guarantee remains possible if events can change their timestamps between page requests.
