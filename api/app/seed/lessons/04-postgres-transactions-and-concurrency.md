+++
slug = "postgres-transactions-and-concurrency"
skill = "sql"
topic = "transactions"
difficulty = "intermediate"
title = "PostgreSQL transactions and concurrency"
summary = "What a transaction guarantees, what each isolation level allows, and how to prevent lost updates and write skew in real code."
estimated_minutes = 25
objectives = [
  "Explain atomicity and isolation, and what READ COMMITTED does and does not prevent.",
  "Prevent lost updates with atomic statements, row locks or optimistic concurrency.",
  "Recognise write skew and handle serialization failures with retries.",
]
prerequisites = ["tracing-program-state"]
misconceptions = [
  "Wrapping code in a transaction makes it safe from all concurrency problems.",
  "REPEATABLE READ prevents every anomaly.",
  "Transactions that update different rows can never interfere.",
]
checks = ["sql-lost-update", "sql-write-skew-repeatable-read"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; isolation behaviour executed on PostgreSQL 16; pending independent human review"

[[resources]]
title = "PostgreSQL docs: Transaction isolation"
url = "https://www.postgresql.org/docs/current/transaction-iso.html"

[[resources]]
title = "PostgreSQL docs: Explicit locking"
url = "https://www.postgresql.org/docs/current/explicit-locking.html"

[[resources]]
title = "PostgreSQL tutorial: Transactions"
url = "https://www.postgresql.org/docs/current/tutorial-transactions.html"
+++
## Why it matters

Concurrency bugs do not show up when you test alone. They appear in production when two requests touch the same data at the same moment: a balance loses a withdrawal, two people book the last seat, a rule such as "someone must stay on call" is silently broken. These bugs cost money and are hard to reproduce, so you need to recognise the patterns before they ship.

## Mental model

A transaction is a group of statements that the database treats as one unit:

- **Atomicity**: either all of it commits or none of it does.
- **Isolation**: while it runs, how much of *other* transactions' work can it see? This is a dial, not a switch.

Picture each transaction reading from a **snapshot** of the database. The isolation level decides how often that snapshot is refreshed and what happens when two transactions' writes collide.

## How it works

PostgreSQL offers three effective levels:

| Level | Snapshot taken | What can still go wrong |
| --- | --- | --- |
| READ COMMITTED (default) | at the start of **each statement** | lost updates through read-then-write in the application, non-repeatable reads, write skew |
| REPEATABLE READ | once, at the **first statement** | write skew; concurrent updates to the *same* row fail with a serialization error |
| SERIALIZABLE | once, plus dependency tracking | nothing beyond retries: the database aborts transactions whose combined effect would not match some serial order |

Two writes to the **same row** always serialise: the second waits for the first to commit or roll back. The trouble is application logic that reads, decides in Python, then writes.

**Lost update.** Two requests both read `balance = 100`, each computes `100 - 30`, each writes `70`. One withdrawal disappeared. Fixes:

1. Let the database do the arithmetic: `UPDATE accounts SET balance = balance - 30 WHERE id = 1 AND balance >= 30`.
2. Lock the row while deciding: `SELECT balance FROM accounts WHERE id = 1 FOR UPDATE`.
3. Optimistic concurrency: keep a `version` column and update `WHERE id = 1 AND version = $read_version`; if zero rows changed, someone else won, so reload and retry.

**Write skew.** Each transaction reads a set of rows, checks a rule, then updates a *different* row. Their writes never collide, so REPEATABLE READ lets both commit, and the rule breaks. SERIALIZABLE detects the dangerous pattern and aborts one transaction.

## Worked example

Two doctors are on call, and at least one must stay. Both try to go off call at the same time:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM doctors WHERE on_call;     -- both see 2
UPDATE doctors SET on_call = false WHERE id = $me;
COMMIT;
```

Run concurrently on PostgreSQL 16, both transactions commit and nobody is on call. Change the level to `SERIALIZABLE` and one of the commits fails with `could not serialize access due to read/write dependencies among transactions`. The application must catch that error (SQLSTATE `40001`) and retry the whole transaction, which will then see only one doctor on call and refuse.

A retry loop in Python:

```python
for attempt in range(3):
    try:
        async with conn.transaction(isolation="serializable"):
            await go_off_call(conn, doctor_id)
        break
    except asyncpg.SerializationError:
        if attempt == 2:
            raise
```

## Common mistakes

- Reading a value, computing in the application, and writing it back without a lock or a version check.
- Assuming a transaction alone prevents interference. At READ COMMITTED it guarantees atomicity, not that your earlier read is still true.
- Using SERIALIZABLE without retry logic: serialization failures are normal, expected events.
- Holding transactions open across slow work such as HTTP calls, which keeps locks longer and increases conflicts.

## In production

Payment ledgers usually use single-statement updates with constraints (`CHECK (balance >= 0)`) or append-only entries. Booking systems use `SELECT ... FOR UPDATE` on the resource row, or a unique constraint on `(seat_id, show_id)` so the database rejects double booking outright. Teams that adopt SERIALIZABLE wrap every transaction in a shared retry helper and watch the rate of `40001` errors.

## Trade-offs and limits

Row locks are simple but make concurrent requests wait, and inconsistent lock ordering can deadlock (PostgreSQL detects deadlocks and aborts one transaction). Optimistic concurrency avoids waiting but needs retry logic and a version column. SERIALIZABLE is the most general protection, at the cost of some overhead and more aborted transactions under contention. Constraints are the strongest guarantee of all, but only for rules that can be expressed as constraints.

## Check your understanding

1. Why does `UPDATE accounts SET balance = balance - 30` avoid the lost update?
   - Answer: the read and the write happen in one statement on a locked row, so concurrent updates apply one after another.
2. Two transactions update different rows. Can they still produce a wrong result together?
   - Answer: yes, through write skew, when each one's decision depended on rows the other changed.
3. What must application code do when using SERIALIZABLE?
   - Answer: retry transactions that fail with a serialization error.

## Practice

In a local PostgreSQL, create `accounts(id int primary key, balance int)`. Open two `psql` sessions and reproduce a lost update by hand with `BEGIN`, `SELECT`, then `UPDATE ... SET balance = <value you computed>`. Then fix it three ways (atomic update, `FOR UPDATE`, version column) and confirm each fix in the same two-session experiment.
