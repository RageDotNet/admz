"""Fabric workflow helpers (infra-v2.md): thin wrappers, single entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fabric import task

REPO = Path(__file__).resolve().parent
PY = sys.executable


def _sh(c, cmd: list[str] | str, msg_on_fail: str | None = None) -> None:
    print(f">>> {cmd}")
    proc = subprocess.run(cmd if isinstance(cmd, list) else cmd.split(), cwd=REPO, shell=False)
    if proc.returncode != 0:
        raise SystemExit(msg_on_fail or f"command failed: {cmd}")


class dev:
    @task
    def up(c):  # noqa: N805
        """Bring the compose stack up for local development."""
        _sh(c, ["docker", "compose", "-f", "deploy/docker-compose.yml", "up", "-d"])

    @task
    def down(c):  # noqa: N805
        """Bring the compose stack down."""
        _sh(c, ["docker", "compose", "-f", "deploy/docker-compose.yml", "down"])


@task
def test(c):
    """Run the offline test suite (includes ruff + mypy quality gates)."""
    _sh(c, [PY, "-m", "pytest", "-q"])


@task
def lint(c):
    """Run linter + formatter checks."""
    _sh(c, [PY, "-m", "ruff", "check", "src", "tests", "fabfile.py"])


@task
def fmt(c):
    """Apply formatting fixes."""
    _sh(c, [PY, "-m", "ruff", "format", "src", "tests", "fabfile.py"])
    _sh(c, [PY, "-m", "ruff", "check", "--fix", "src", "tests", "fabfile.py"])


class db:
    @task
    def migrate(c, message="auto"):  # noqa: N805
        """Generate an Alembic migration."""
        _sh(c, [PY, "-m", "alembic", "revision", "--autogenerate", "-m", message])

    @task
    def upgrade(c):  # noqa: N805
        """Apply Alembic migrations."""
        _sh(c, [PY, "-m", "alembic", "upgrade", "head"])


@task
def build(c):
    """Build the Docker image."""
    _sh(c, ["docker", "build", "-t", "llmdmz:v2", "-f", "deploy/Dockerfile", "."])


@task
def deploy(c):
    """Deploy the compose stack (build + up)."""
    build(c)
    _sh(c, ["docker", "compose", "-f", "deploy/docker-compose.yml", "up", "-d"])
