"""Hidden backend checks."""

from checks_public import client, fresh_db, http, observe  # noqa: F401

# The migration exactly as it shipped in the previous release. Production
# databases were created by this file, not by whatever 001 says today.
SHIPPED_001 = """
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);
CREATE TABLE schema_migrations (name TEXT PRIMARY KEY);
INSERT INTO schema_migrations (name) VALUES ('001_create_invoices.sql');
"""


def legacy_upgrade(customer, lines, keys):
    """A production database from the last release, with an existing invoice,
    upgraded by starting the new app (which runs pending migrations) twice."""
    import sqlite3

    path = fresh_db()
    conn = sqlite3.connect(path)
    conn.executescript(SHIPPED_001)
    cur = conn.execute("INSERT INTO invoices (customer) VALUES (?)", (customer,))
    invoice_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
        [(invoice_id, d, q, p) for d, q, p in lines],
    )
    conn.commit()
    conn.close()
    with client(path):
        pass  # first start applies the new migrations
    with client(path) as c:  # a restart must not re-apply them
        return observe(c.get(f"/invoices/{invoice_id}"), keys)
