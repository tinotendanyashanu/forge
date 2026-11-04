CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    amount_cents BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'declined')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX payments_idempotency_key_idx ON payments (idempotency_key);

CREATE TABLE ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES payments(id),
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    amount_cents BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
