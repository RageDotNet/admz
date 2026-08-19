"""Quality gate wired into the pytest run (T0.3): ruff + mypy must pass."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"quality gate failed: {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}"
        )


def test_ruff_clean() -> None:
    _run([sys.executable, "-m", "ruff", "check", "src", "tests", "fabfile.py"])


def test_mypy_clean() -> None:
    _run([sys.executable, "-m", "mypy", "--pretty"])
