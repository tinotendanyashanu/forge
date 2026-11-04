"""Hidden checks: heavier concurrency and the edge cases in the ticket."""

import threading

import psycopg

from checks_public import concurrent_retries, dsn, reset, sequential, state  # noqa: F401


def concurrent_spend(start, threads, per_thread, amount):
    """Different keys from many connections at once: no overdraft, no lost update."""
    from payments.service import process_payment

    reset([[1, start]])
    barrier, lock = threading.Barrier(threads), threading.Lock()
    succeeded, errors = [0], set()

    def work(t):
        ok = 0
        with psycopg.connect(dsn()) as conn:
            barrier.wait()
            for i in range(per_thread):
                try:
                    r = process_payment(conn, account_id=1, amount_cents=amount, idempotency_key=f"t{t}-{i}")
                    ok += r["status"] == "succeeded"
                except Exception as exc:  # noqa: BLE001
                    errors.add(type(exc).__name__)
                    conn.rollback()
        with lock:
            succeeded[0] += ok

    ts = [threading.Thread(target=work, args=(t,)) for t in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s = state()
    final = s["balances"][0][1]
    return {"succeeded": succeeded[0], "final_balance": final, "ledger_total": s["ledger_total"],
            "balanced": final == start + s["ledger_total"], "errors": sorted(errors)}


def declined_is_final(balance, amount, top_up):
    """A declined payment stays declined when retried, even after the balance changes."""
    from checks_public import Labels, call

    reset([[1, balance]])

    labels = Labels()
    with psycopg.connect(dsn()) as conn:
        a = call(conn, labels, 1, amount, "late")
        with psycopg.connect(dsn(), autocommit=True) as c:
            c.execute("UPDATE accounts SET balance_cents = balance_cents + %s WHERE id = 1", (top_up,))
        b = call(conn, labels, 1, amount, "late")
    return {"first": a, "retry": b, **state()}
