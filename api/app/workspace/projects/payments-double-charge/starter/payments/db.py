from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def apply_migrations(conn) -> list[str]:
    """Applies migrations/*.sql in name order, each at most once, each in its own transaction."""
    with conn.transaction():
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)")
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        with conn.transaction():
            if conn.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (path.name,)).fetchone():
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied
