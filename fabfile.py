"""Fabric workflow helpers (infra-v2.md): thin wrappers, single entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fabric import task
from invoke import Collection

REPO = Path(__file__).resolve().parent
PY = sys.executable


def _sh(c, cmd: list[str] | str, msg_on_fail: str | None = None) -> None:
    print(f">>> {cmd}")
    proc = subprocess.run(cmd if isinstance(cmd, list) else cmd.split(), cwd=REPO, shell=False)
    if proc.returncode != 0:
        raise SystemExit(msg_on_fail or f"command failed: {cmd}")


@task
def dev_up(c):
    """Bring the compose stack up for local development."""
    _sh(c, ["docker", "compose", "-f", "deploy/docker-compose.yml", "up", "-d"])


@task
def dev_down(c):
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


@task
def db_migrate(c, message="auto"):
    """Generate an Alembic migration."""
    _sh(c, [PY, "-m", "alembic", "revision", "--autogenerate", "-m", message])


@task
def db_upgrade(c):
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


# Fabric 2.x namespacing: group tasks into `dev.*` and `db.*` sub-collections.
dev = Collection("dev")
dev.add_task(dev_up, "up")
dev.add_task(dev_down, "down")
db = Collection("db")
db.add_task(db_migrate, "migrate")
db.add_task(db_upgrade, "upgrade")

ns = Collection(test, lint, fmt, build, deploy)
ns.add_collection(dev)
ns.add_collection(db)
