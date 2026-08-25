"""Bearer auth middleware (#17): resolve any Bearer token to agent-or-admin.

- Agent keys (``dmz_...``) resolve against ``agents.api_key_hash``.
- Admin tokens (``dmzadm_...``) resolve against config-defined admin tokens.
- Auth always goes through the hash; prefixes are cosmetic metadata (#15).
- Unknown/garbage token → 401 everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import request

from admz.core.keys import ADMIN_PREFIX, AGENT_PREFIX, hash_key
from admz.core.storage import find_agent_by_key

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from admz.core.config import AdminAccount, Config
    from admz.core.models import Agent


@dataclass
class Identity:
    kind: str  # "agent" | "admin"
    agent: Agent | None = None
    admin: AdminAccount | None = None

    @property
    def actor_id(self) -> str:
        if self.kind == "admin" and self.admin is not None:
            return f"admin:{self.admin.username}"
        assert self.agent is not None
        return self.agent.id


def resolve_bearer(session: Session, config: Config, token: str) -> Identity | None:
    """Resolve a bearer token to an Identity, or None if unknown."""
    if token.startswith(ADMIN_PREFIX):
        hashed = hash_key(token)
        for admin in config.admins:
            if admin.token and hash_key(admin.token) == hashed:
                return Identity(kind="admin", admin=admin)
        return None
    if token.startswith(AGENT_PREFIX):
        agent = find_agent_by_key(session, token)
        if agent is None or agent.disabled:
            return None
        return Identity(kind="agent", agent=agent)
    return None


def bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer ") :].strip()
    return None
