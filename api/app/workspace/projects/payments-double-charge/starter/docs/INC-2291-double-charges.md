# INC-2291: customers charged twice (summary)

**Impact.** 37 customers were charged twice for one purchase over 3 days.
Finance's nightly reconciliation also found 4 wallets whose balance did not
match the sum of their ledger entries.

**Timeline.** The mobile app retries `POST /payments` with the same
`Idempotency-Key` header when a request takes longer than 10 s. During a
database slowdown, retries arrived while the first request was still running.

**What we know.**
* Duplicate charges always share an idempotency key and were created within
  milliseconds of each other.
* The mismatched wallets had several payments from different devices at the
  same moment.

**Action items.**
1. INC-2291-1: make `process_payment` safe under concurrent retries (this ticket).
2. INC-2291-2: make balance updates safe under concurrency (this ticket).
3. INC-2291-3: refund affected customers (Finance, done).
