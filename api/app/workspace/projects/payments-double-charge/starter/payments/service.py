from payments import ledger


def process_payment(conn, *, account_id: int, amount_cents: int, idempotency_key: str) -> dict:
    """Charges an account at most once per idempotency key.

    Returns {"payment_id": int, "status": "succeeded" | "declined", "replayed": bool}.
    A request with a key that was already processed returns the original result
    with replayed=True.
    """
    existing = conn.execute(
        "SELECT id, status FROM payments WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    if existing is not None:
        conn.commit()
        return {"payment_id": existing[0], "status": existing[1], "replayed": True}

    balance = conn.execute("SELECT balance_cents FROM accounts WHERE id = %s", (account_id,)).fetchone()[0]
    if balance < amount_cents:
        payment_id = conn.execute(
            "INSERT INTO payments (idempotency_key, account_id, amount_cents, status) "
            "VALUES (%s, %s, %s, 'declined') RETURNING id",
            (idempotency_key, account_id, amount_cents),
        ).fetchone()[0]
        conn.commit()
        return {"payment_id": payment_id, "status": "declined", "replayed": False}

    conn.execute("UPDATE accounts SET balance_cents = %s WHERE id = %s", (balance - amount_cents, account_id))
    payment_id = conn.execute(
        "INSERT INTO payments (idempotency_key, account_id, amount_cents, status) "
        "VALUES (%s, %s, %s, 'succeeded') RETURNING id",
        (idempotency_key, account_id, amount_cents),
    ).fetchone()[0]
    ledger.record_debit(conn, payment_id, account_id, amount_cents)
    conn.commit()
    return {"payment_id": payment_id, "status": "succeeded", "replayed": False}
