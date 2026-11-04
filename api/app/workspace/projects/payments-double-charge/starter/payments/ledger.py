def record_debit(conn, payment_id: int, account_id: int, amount_cents: int) -> None:
    """Records money leaving an account. Ledger amounts are negative for debits."""
    conn.execute(
        "INSERT INTO ledger_entries (payment_id, account_id, amount_cents) VALUES (%s, %s, %s)",
        (payment_id, account_id, -amount_cents),
    )
