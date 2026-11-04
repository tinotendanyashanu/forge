# Invoices

A small billing service: a FastAPI backend with SQLite storage, and the
TypeScript data layer of the React web app that displays invoices.

```
invoices/            FastAPI backend
  main.py            create_app(db_path): connects, migrates, mounts routes
  db.py              connect() and the migration runner
  models.py          Pydantic request/response models
  repository.py      SQL for invoices and lines
  routes.py          POST /invoices, GET /invoices/{id}
  discounts.py       marketing-owned discount codes
migrations/          SQL migrations, applied in name order, once each
web/src/lib/         TypeScript used by the React app
  money.ts           formatCents
  invoice.ts         summarizeInvoice: rows for the totals panel
  api.ts             buildCreateInvoicePayload: form -> API request body
web/src/components/  React components (rendering is not executed in FORGE)
```

## Running tests

**Run tests** in FORGE runs two suites in the sandbox: the backend (Python,
FastAPI `TestClient`, a fresh SQLite file per test) and the web data layer
(Node 24, which runs TypeScript by stripping types; it does not type-check).

Node runs `.ts` files directly, so imports between them use the `.ts`
extension (`import { formatCents } from "./money.ts"`). Use only erasable
TypeScript syntax: no `enum`, no `namespace`, no parameter properties.
