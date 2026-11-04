ALTER TABLE invoices ADD COLUMN discount_code TEXT;
ALTER TABLE invoices ADD COLUMN discount_cents INTEGER NOT NULL DEFAULT 0 CHECK (discount_cents >= 0);
