"""T1.5: migration upgrade/downgrade round-trip on SQLite + schema spot-check."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DMZ_DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_downgrade_roundtrip(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'mig.db'}"
    up = _alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, up.stdout + up.stderr
    down = _alembic("downgrade", "base", db_url=db_url)
    assert down.returncode == 0, down.stdout + down.stderr
    up2 = _alembic("upgrade", "head", db_url=db_url)
    assert up2.returncode == 0, up2.stdout + up2.stderr

    # Spot-check the schema against #13.
    import sqlite3

    con = sqlite3.connect(tmp_path / "mig.db")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {
        "agents", "actions", "action_versions", "enrollments",
        "requests", "dispatch_attempts", "audit_events",
    }
    assert expected <= tables, f"missing tables: {expected - tables}"
    cols = {r[1] for r in con.execute("PRAGMA table_info(audit_events)")}
    assert {"id", "occurred_at", "actor_type", "actor_id", "event",
            "target_type", "target_id", "detail"} <= cols
    rcols = {r[1] for r in con.execute("PRAGMA table_info(requests)")}
    assert {"outcome", "request_verdict", "active_version_id", "finished_at"} <= rcols
    con.close()
