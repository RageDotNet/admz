"""Bearer key generation and hashing (#15).

Keys: 32 random bytes via ``secrets.token_urlsafe`` (43 chars), prefixed
``dmz_`` (agents) / ``dmzadm_`` (admins). Stored as SHA-256 hex of the full
string; auth resolves via hash lookup. Plaintext is reveal-once.
"""

from __future__ import annotations

import hashlib
import secrets

AGENT_PREFIX = "dmz_"
ADMIN_PREFIX = "dmzadm_"


def generate_agent_key() -> str:
    return AGENT_PREFIX + secrets.token_urlsafe(32)


def generate_admin_token() -> str:
    return ADMIN_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_namespace(key: str) -> str | None:
    """Cosmetic prefix metadata (#17); auth always goes through the hash."""
    if key.startswith(ADMIN_PREFIX):
        return "admin"
    if key.startswith(AGENT_PREFIX):
        return "agent"
    return None
