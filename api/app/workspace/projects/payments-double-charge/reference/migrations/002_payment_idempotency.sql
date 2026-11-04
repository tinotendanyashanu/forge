-- One payment per idempotency key, enforced by the database.
ALTER TABLE payments ADD CONSTRAINT payments_idempotency_key_key UNIQUE (idempotency_key);
DROP INDEX payments_idempotency_key_idx;
-- A payment row claims its key before the debit decision is made.
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check CHECK (status IN ('pending', 'succeeded', 'declined'));
-- Defence in depth: a balance can never go negative.
ALTER TABLE accounts ADD CONSTRAINT accounts_balance_non_negative CHECK (balance_cents >= 0);
