from payments import ledger
from payments.errors import AccountNotFound, IdempotencyConflict


def process_payment(conn, *, account_id: int, amount_cents: int, idempotency_key: str) -> dict:
    """Charges an account at most once per idempotency key.

    Returns {"payment_id": int, "status": "succeeded" | "declined", "replayed": bool}.
    A request with a key that was already processed returns the original result
    with replayed=True.

    Safe under concurrency at READ COMMITTED:
    * the payment row claims the key first (INSERT ... ON CONFLICT DO NOTHING on a
      unique key): a concurrent retry blocks until the first transaction commits,
      then reads its final result;
    * the debit is one conditional UPDATE, so the check and the write are atomic.
    """
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    with conn.transaction():
        if conn.execute("SELECT 1 FROM accounts WHERE id = %s", (account_id,)).fetchone() is None:
            raise AccountNotFound(account_id)
        claimed = conn.execute(
            "INSERT INTO payments (idempotency_key, account_id, amount_cents, status) "
            "VALUES (%s, %s, %s, 'pending') ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
            (idempotency_key, account_id, amount_cents),
        ).fetchone()
        if claimed is None:
            payment_id, owner, amount, status = conn.execute(
                "SELECT id, account_id, amount_cents, status FROM payments WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
            if (owner, amount) != (account_id, amount_cents):
                raise IdempotencyConflict(idempotency_key)
            return {"payment_id": payment_id, "status": status, "replayed": True}

        payment_id = claimed[0]
        debited = conn.execute(
            "UPDATE accounts SET balance_cents = balance_cents - %s WHERE id = %s AND balance_cents >= %s",
            (amount_cents, account_id, amount_cents),
        ).rowcount == 1
        status = "succeeded" if debited else "declined"
        conn.execute("UPDATE payments SET status = %s WHERE id = %s", (status, payment_id))
        if debited:
            ledger.record_debit(conn, payment_id, account_id, amount_cents)
    return {"payment_id": payment_id, "status": status, "replayed": False}
