# Payments

The service that charges customer wallets. API handlers (not included here)
call `payments.service.process_payment` with a psycopg 3 connection from a pool;
many API workers run it concurrently against the same PostgreSQL database.

```
payments/
  service.py     process_payment(): the entry point
  ledger.py      ledger entries (one per balance movement)
  errors.py      domain exceptions
  db.py          apply_migrations()
migrations/      SQL migrations, applied in name order, once each
docs/            incident notes
```

Connections are **not** in autocommit mode, and PostgreSQL runs at its default
isolation level, **READ COMMITTED**. Do not change the isolation level.

**Run tests** starts a private PostgreSQL 15+ inside the sandbox (Unix socket
only, no network), applies `migrations/`, and calls `process_payment` from
several threads, each with its own connection.
