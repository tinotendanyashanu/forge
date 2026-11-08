+++
slug = "sql-querying-joins-and-nulls"
skill = "sql"
topic = "querying"
difficulty = "beginner"
title = "SQL queries: joins, NULL and the grain of a result"
summary = "Build reports that preserve the right rows, count the right entities and handle missing values deliberately."
estimated_minutes = 32
objectives = ["State the grain of a query result before combining tables.", "Explain how ON and WHERE affect unmatched rows in a LEFT JOIN.", "Use NULL predicates and aggregate counts without inventing or losing entities."]
prerequisites = ["choosing-data-structures"]
misconceptions = ["NULL equals NULL in an ordinary equality predicate.", "COUNT(*) counts matched children in a LEFT JOIN.", "Moving a predicate from ON to WHERE always preserves a join's meaning."]
checks = ["sql-null-comparison", "sql-left-join-where", "sql-group-by-ungrouped-column", "sql-left-join-count-star"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; PostgreSQL examples executed; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "PostgreSQL 16 tutorial: Joins between tables"
url = "https://www.postgresql.org/docs/16/tutorial-join.html"
[[resources]]
title = "PostgreSQL 16: Table expressions and grouping"
url = "https://www.postgresql.org/docs/16/queries-table-expressions.html"
[[resources]]
title = "PostgreSQL 16: Comparison predicates and NULL"
url = "https://www.postgresql.org/docs/16/functions-comparison.html"
[[resources]]
title = "PostgreSQL 16: Aggregate functions"
url = "https://www.postgresql.org/docs/16/functions-aggregate.html"
+++
## Why it matters

An account dashboard must show every customer, including customers with no paid orders. A plausible query silently drops those customers. Another query gives them one order each. Both errors come from reasoning about the tables separately instead of reasoning about the rows produced by the join.

Prerequisites: understand records, keys, equality and basic Boolean conditions. No prior SQL lesson is required. The example introduces the SQL statements it uses and runs on PostgreSQL 16 or later. Use a scratch database: the script creates temporary tables and rolls its transaction back.

## Mental model

A table represents rows with named columns. A primary key identifies a row. A foreign key relates a child row to its parent. Before querying, state the **grain**: what does one output row represent? For a customer summary, the target grain is one row per customer, even though one customer may have many orders.

A query transforms a set of candidate rows. Its logical stages include forming joined rows, filtering them with `WHERE`, grouping, calculating aggregates and ordering the result. The optimizer may execute a different physical plan while preserving these semantics. Do not confuse this reasoning order with an engine execution trace.

SQL's `NULL` represents missing or unknown information. Most comparisons involving NULL produce **unknown**, rather than true or false. `WHERE` retains only true predicates. Use `IS NULL` to test missingness, or `IS NOT DISTINCT FROM` when you explicitly want a comparison that treats two NULLs as equal.

## How it works

An inner join emits matching pairs. A left join also emits one null-extended row for a left-side row with no match. Conditions in `ON` determine which pairs match before that fallback row is created; false or unknown conditions do not establish a match. Conditions in `WHERE` then filter the joined result, including any fallback rows.

Putting a paid-status predicate in the `ON` clause means “match only paid orders, but retain every customer.” Putting it in `WHERE` means “retain joined rows whose order is paid.” The second form rejects the null-extended row and also rejects a customer who has only unpaid orders. Adding `OR order.id IS NULL` to that WHERE clause does not restore the customer who had a real unpaid match.

`COUNT(*)` counts rows, including the fallback row. `COUNT(expression)` counts rows where that expression is non-NULL. Counting a matched child's non-null primary key therefore gives zero for an unmatched parent. `SUM` over no non-null inputs returns NULL; `COALESCE` can supply zero when zero is the intended business meaning. Missing measurement data and a true total of zero are not always interchangeable.

Grouping collapses rows to the stated grain. Select grouped columns and aggregates; arbitrary ungrouped values have no well-defined representative. PostgreSQL can recognize some functional dependencies, such as a table's other columns depending on its grouped primary key, but grouping explicitly is often clearest when learning and when porting queries.

## Worked example

Run the entire block in one PostgreSQL session. The queries return rows in the shown order:

```sql
BEGIN;
CREATE TEMP TABLE lesson_customers (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TEMP TABLE lesson_orders (
    id integer PRIMARY KEY,
    customer_id integer REFERENCES lesson_customers(id),
    status text NOT NULL,
    total integer
);
INSERT INTO lesson_customers VALUES (1, 'Asha'), (2, 'Bo'), (3, 'Cy');
INSERT INTO lesson_orders VALUES
    (11, 1, 'paid', 40), (12, 1, 'pending', 25), (13, 3, 'pending', NULL);

SELECT c.id, c.name, COUNT(o.id) AS paid_orders,
       COALESCE(SUM(o.total), 0) AS paid_total
FROM lesson_customers AS c
LEFT JOIN lesson_orders AS o
    ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.id, c.name
ORDER BY c.id;

SELECT c.id, COUNT(*) AS joined_rows, COUNT(o.id) AS matching_orders
FROM lesson_customers AS c
LEFT JOIN lesson_orders AS o ON o.customer_id = c.id
GROUP BY c.id
ORDER BY c.id;

SELECT id FROM lesson_orders WHERE total IS NULL ORDER BY id;
SELECT id FROM lesson_orders WHERE total = NULL ORDER BY id;
ROLLBACK;
```

The first query returns `(1, Asha, 1, 40)`, `(2, Bo, 0, 0)` and `(3, Cy, 0, 0)`. Bo has no orders and Cy has no paid orders; both remain visible. The second returns `(1, 2, 2)`, `(2, 1, 0)` and `(3, 1, 1)`. Bo's one joined row is a fallback, not an order. The third query returns only ID 13. The fourth returns no rows because equality with NULL is unknown even for the NULL total.

## Common mistakes

- Counting order rows after also joining order lines and payments. A one-to-many join can multiply rows. Preaggregate each child table to one row per parent before combining summaries.
- Adding `DISTINCT` until a total looks plausible. Deduplication can hide a faulty join and collapse legitimate equal-valued rows.
- Assuming rows arrive in insertion order. Specify `ORDER BY`, including a unique tie-breaker where stable paging matters.
- Replacing NULL with zero everywhere. Unknown revenue and zero revenue express different facts; decide the business meaning first.

## In production

Reports often cross tenant boundaries. Apply the correct tenant predicate and join on the complete key when IDs are only unique within a tenant. Parameterize user-supplied values; string interpolation is not query parameterization. Grant reporting processes only the access they need.

Test queries with an empty database, an unmatched parent, multiple children, a parent with only nonmatching children and nullable values. These cases catch semantic errors that a large happy-path fixture misses. For financial data, choose appropriate exact numeric types and currency handling; integer totals here deliberately avoid teaching floating-point money arithmetic. Integer minor units can be appropriate when currency scale and range are explicit; an exact numeric representation is another option.

## Trade-offs and limits

Preaggregation can make grain explicit and prevent fan-out, but it still needs a plan appropriate to the dataset. A correct query can be slow, and an index cannot repair an incorrect join. Learn semantics first; the next lesson examines execution plans.

`COUNT(DISTINCT child_id)` can be legitimate for unique-child counts, but it does not automatically fix sums multiplied by other joins. Likewise, a left join is useful when absence matters; use an inner join when only matching parents should appear. Choose based on the question the report must answer.

## Check your understanding

1. Why does adding `WHERE o.status = 'paid'` after the example's unrestricted left join lose Cy as well as Bo?
   - Feedback: Cy has a real pending match, which fails the filter; Bo's fallback has NULL status, which also fails. Neither produces a retained paid row.
2. A customer has two orders, each with three lines. How many rows can joining both tables produce, and what does `COUNT(order.id)` now count?
   - Feedback: six rows; it counts repeated order IDs per line, not two unique orders. Aggregate at the desired grain.
3. When would replacing a NULL total with zero mislead the dashboard user?
   - Feedback: when NULL means the amount has not been determined. Displaying zero would assert information you do not have.

The linked FORGE checks cover NULL, left-join filtering, grouping and counting. Start with beginner SQL assessments; use the intermediate assessment for joined-row counts.

## Practice

Recreate the temporary tables and write a report with one row per customer showing total orders, paid orders and the largest known paid order. Keep customers with no orders. Add a customer with two paid orders of the same amount and a customer whose only paid amount is NULL.

Acceptance criteria: counts remain correct for every case, the maximum remains NULL when no known paid amount exists, and rows have a deterministic order. Explain why equal amounts must not be deduplicated. As a transfer task, add a separate refunds table with multiple rows per order and design a query that does not multiply either revenue or refunds.
