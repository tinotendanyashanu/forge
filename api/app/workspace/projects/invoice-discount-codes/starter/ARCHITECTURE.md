# Architecture

```
React app ── web/src/lib/api.ts ──► POST /invoices ──► routes.py ──► repository.py ──► SQLite
    ▲                                                                    │
    └──── web/src/lib/invoice.ts ◄── GET /invoices/{id} ◄────────────────┘
```

## Money

All amounts are **integer cents**, end to end. Never use floats for money:
`0.1 + 0.2 != 0.3`, and Python's `round()` rounds half to even
(`round(0.5) == 0`), which is not what finance expects. Finance's rule is
**round half up to the nearest cent**.

## Migrations

`db.migrate()` applies `migrations/*.sql` in name order and records each file
in `schema_migrations`. Production databases have already applied
`001_create_invoices.sql`; **never edit a migration that has shipped**. Schema
changes go in a new numbered file.

SQLite's `ALTER TABLE ... ADD COLUMN` supports `NOT NULL` only with a
`DEFAULT`.

## Totals

`repository.get_invoice` computes `subtotal_cents` from the lines on read.
