"""Public checks: a private PostgreSQL in the sandbox (Unix socket in /tmp, no TCP).

Payment ids are reported as labels ("p1", "p2", ...) in first-seen order, so
implementations that consume sequence values differently compare equally.
"""

import os
import shutil
import subprocess
import threading

import psycopg

_DSN = None


def dsn() -> str:
    global _DSN
    if _DSN is None:
        data = "/tmp/pgdata"
        shutil.copytree("/opt/pgtemplate", data)
        os.chmod(data, 0o700)
        subprocess.run(["/opt/pgbin/pg_ctl", "-D", data, "-l", "/tmp/pg.log", "-w", "-t", "20", "start"],
                       check=True, capture_output=True)
        _DSN = "host=/tmp dbname=postgres user=forge"
    return _DSN


def reset(balances) -> None:
    """Fresh schema from the learner's migrations, then the given accounts."""
    from payments.db import apply_migrations

    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
    with psycopg.connect(dsn()) as conn:
        apply_migrations(conn)
        conn.commit()
    with psycopg.connect(dsn(), autocommit=True) as c:
        for account, balance in balances:
            c.execute("INSERT INTO accounts (id, balance_cents) VALUES (%s, %s)", (account, balance))


def state() -> dict:
    with psycopg.connect(dsn(), autocommit=True) as c:
        return {
            "balances": [list(r) for r in c.execute("SELECT id, balance_cents FROM accounts ORDER BY id")],
            "payments": [list(r) for r in c.execute(
                "SELECT idempotency_key, account_id, amount_cents, status FROM payments ORDER BY idempotency_key, id")],
            "ledger_entries": c.execute("SELECT count(*) FROM ledger_entries").fetchone()[0],
            "ledger_total": int(c.execute("SELECT coalesce(sum(amount_cents), 0) FROM ledger_entries").fetchone()[0]),
        }


class Labels:
    def __init__(self) -> None:
        self.seen: dict = {}

    def __call__(self, payment_id) -> str:
        return self.seen.setdefault(payment_id, f"p{len(self.seen) + 1}")


def call(conn, labels, account, amount, key):
    from payments.service import process_payment

    try:
        r = process_payment(conn, account_id=account, amount_cents=amount, idempotency_key=key)
        return [labels(r["payment_id"]), r["status"], r["replayed"]]
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return ["error", type(exc).__name__]


def sequential(balances, calls):
    """Runs calls ([account, amount, key]) one after another on one connection."""
    reset(balances)
    labels, results = Labels(), []
    with psycopg.connect(dsn()) as conn:
        for account, amount, key in calls:
            results.append(call(conn, labels, account, amount, key))
            # The connection must be left with no open transaction.
            results[-1].append(conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE)
    return {"results": results, **state()}


def concurrent_retries(balance, threads, amount, rounds):
    """`threads` connections send the same key at the same moment, `rounds` times."""
    from payments.service import process_payment

    reset([[1, balance]])
    good_rounds, errors = 0, set()
    for r in range(rounds):
        key = f"retry-{r}"
        barrier, out, lock = threading.Barrier(threads), [], threading.Lock()

        def work():
            with psycopg.connect(dsn()) as conn:
                barrier.wait()
                try:
                    res = process_payment(conn, account_id=1, amount_cents=amount, idempotency_key=key)
                    with lock:
                        out.append(res)
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.add(type(exc).__name__)

        ts = [threading.Thread(target=work) for _ in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        with psycopg.connect(dsn(), autocommit=True) as c:
            rows = c.execute("SELECT count(*) FROM payments WHERE idempotency_key = %s", (key,)).fetchone()[0]
            entries = c.execute(
                "SELECT count(*) FROM ledger_entries l JOIN payments p ON p.id = l.payment_id "
                "WHERE p.idempotency_key = %s", (key,)).fetchone()[0]
        same = len({o["payment_id"] for o in out}) == 1 and len({o["status"] for o in out}) == 1
        fresh = sum(1 for o in out if not o["replayed"])
        if rows == 1 and entries <= 1 and len(out) == threads and same and fresh == 1:
            good_rounds += 1
    s = state()
    return {"good_rounds": good_rounds, "final_balance": s["balances"][0][1], "ledger_total": s["ledger_total"],
            "errors": sorted(errors)}
