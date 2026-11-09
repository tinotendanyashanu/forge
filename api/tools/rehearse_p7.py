"""P6 -> P7 and two complete seeds on a NEW local scratch database.

Set FORGE_P7_DATABASE_URL to a fresh local forge_p7_* database.
Never drops an existing database or tables. Synthetic learner data only.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg
from app.seed.__main__ import main as seed_main
from app.seed.lessons import load_lessons
import rehearse_p5 as shared

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "25c4b6ff80b418b298d11f530f582072a240b617"


def main():
    url = os.environ["FORGE_P7_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    target = urlsplit(url)
    assert target.hostname in {"localhost", "127.0.0.1"} and target.path.startswith("/forge_p7_")

    async def empty():
        conn = await asyncpg.connect(url)
        try:
            assert await conn.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='public'") == 0, "Use a NEW scratch database"
        finally:
            await conn.close()

    asyncio.run(empty())
    subprocess.run([sys.executable, "-m", "alembic", "-x", f"database_url={url.replace('postgresql://', 'postgresql+asyncpg://')}",
                    "upgrade", "head"], cwd=ROOT / "api", check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix="forge-p7-baseline-") as directory:
        files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASELINE, "api/app/seed/lessons"], cwd=ROOT, text=True).splitlines()
        assert len(files) == 35, len(files)
        for name in files:
            Path(directory, Path(name).name).write_bytes(subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT))
        with patch("app.seed.__main__.load_lessons", lambda c, qs: load_lessons(c, qs, Path(directory))):
            asyncio.run(seed_main(url.replace("postgresql://", "postgresql+asyncpg://")))
    shared.synthetic_history(url)

    async def history_tables():
        conn = await asyncpg.connect(url)
        try:
            return [r[0] for r in await conn.fetch("""WITH RECURSIVE scoped(oid) AS (
              SELECT 'learners'::regclass::oid
              UNION SELECT con.conrelid FROM pg_constraint con JOIN scoped s ON con.confrelid=s.oid WHERE con.contype='f'
            ) SELECT c.relname FROM scoped s JOIN pg_class c ON c.oid=s.oid ORDER BY c.relname""")]
        finally:
            await conn.close()

    shared.HISTORY = asyncio.run(history_tables())
    before = asyncio.run(shared.snapshot(url))
    assert before["counts"]["active_lessons"] == 35 and before["answers"]["count"] == 3
    snapshots = []
    for _ in range(2):
        asyncio.run(seed_main(url.replace("postgresql://", "postgresql+asyncpg://")))
        after = asyncio.run(shared.snapshot(url))
        for table in shared.HISTORY + shared.CONTENT:
            assert after[table] == before[table], f"Protected fingerprint mismatch: {table}"
        assert all(after["lesson_ids"][slug] == lesson_id for slug, lesson_id in before["lesson_ids"].items())
        assert after["counts"] == {"active_questions": 158, "inactive_questions": 0, "active_lessons": 45, "covered_subskills": 45}
        assert after["lesson_questions"]["count"] == 147 and after["lesson_resources"]["count"] == 157
        snapshots.append(after)
    assert snapshots[0] == snapshots[1], "Second seed changed logical content or history"
    print("P7_REHEARSAL=" + json.dumps({
        "baseline_commit": BASELINE, "history_tables": shared.HISTORY,
        "baseline": before, "first_seed": snapshots[0], "second_seed": snapshots[1],
        "history_unchanged": True, "logical_idempotency": True,
    }))


if __name__ == "__main__":
    main()
