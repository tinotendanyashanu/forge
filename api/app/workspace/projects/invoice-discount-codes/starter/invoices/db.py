import sqlite3
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection, stop_after: str | None = None) -> list[str]:
    """Applies migrations/*.sql in name order, each at most once. Returns the names applied.

    ``stop_after`` stops after the migration whose name starts with it (used by tests
    to build a database as it existed at an older release).
    """
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name not in done:
            conn.executescript(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (path.name,))
            conn.commit()
            applied.append(path.name)
        if stop_after and path.name.startswith(stop_after):
            break
    return applied
