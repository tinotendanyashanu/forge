import sqlite3

from invoices.models import InvoiceIn


def create_invoice(conn: sqlite3.Connection, data: InvoiceIn) -> int:
    with conn:  # one transaction: the invoice and its lines, or nothing
        cur = conn.execute("INSERT INTO invoices (customer) VALUES (?)", (data.customer,))
        invoice_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
            [(invoice_id, l.description, l.quantity, l.unit_price_cents) for l in data.lines],
        )
    return invoice_id


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        return None
    lines = [dict(r) for r in conn.execute(
        "SELECT id, description, quantity, unit_price_cents FROM invoice_lines WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    )]
    subtotal = sum(l["quantity"] * l["unit_price_cents"] for l in lines)
    return {"id": row["id"], "customer": row["customer"], "lines": lines,
            "subtotal_cents": subtotal, "total_cents": subtotal}
