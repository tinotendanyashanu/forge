import sqlite3

from invoices.discounts import DISCOUNT_CODES
from invoices.models import InvoiceIn


class UnknownDiscountCode(ValueError):
    pass


def discount_for(subtotal_cents: int, percent: int) -> int:
    """Percent of the subtotal in whole cents, rounded half up, using integers only."""
    return (subtotal_cents * percent * 2 + 100) // 200


def create_invoice(conn: sqlite3.Connection, data: InvoiceIn) -> int:
    percent = 0
    if data.discount_code is not None:
        if data.discount_code not in DISCOUNT_CODES:
            raise UnknownDiscountCode(data.discount_code)
        percent = DISCOUNT_CODES[data.discount_code]
    subtotal = sum(l.quantity * l.unit_price_cents for l in data.lines)
    discount = discount_for(subtotal, percent)
    with conn:  # one transaction: the invoice and its lines, or nothing
        cur = conn.execute(
            "INSERT INTO invoices (customer, discount_code, discount_cents) VALUES (?, ?, ?)",
            (data.customer, data.discount_code, discount),
        )
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
    discount = row["discount_cents"]
    return {"id": row["id"], "customer": row["customer"], "lines": lines, "discount_code": row["discount_code"],
            "subtotal_cents": subtotal, "discount_cents": discount, "total_cents": subtotal - discount}
