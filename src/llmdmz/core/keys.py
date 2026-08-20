"""Bearer key generation and hashing (#15).

New keys: ``dmz_`` / ``dmzadm_`` plus a body of ``payload_chars`` random
base64url characters and a 2-character checksum appended (checksum is part of
the body, not stored separately). Default body is 16 chars (14 + 2 check).
``key_payload_chars`` in config.yaml controls generation length.

The full string is hashed with SHA-256 for lookup. Plaintext is reveal-once.

Older bodies are still accepted:
- 43 chars, no checksum (original ``token_urlsafe(32)`` keys)
- 49 chars = 43 payload + 6-char checksum (brief intermediate format)
- any length >= default + checksum where the trailing 2 chars validate
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

AGENT_PREFIX = "dmz_"
ADMIN_PREFIX = "dmzadm_"

DEFAULT_PAYLOAD_CHARS = 14
PAYLOAD_CHARS = DEFAULT_PAYLOAD_CHARS  # backward-compatible alias
CHECKSUM_CHARS = 2
CHECKSUMMED_BODY_CHARS = DEFAULT_PAYLOAD_CHARS + CHECKSUM_CHARS  # 16
MIN_PAYLOAD_CHARS = DEFAULT_PAYLOAD_CHARS

# Historical bodies that must keep working.
LEGACY_UNCHECKED_BODY_CHARS = 43
LEGACY_CHECKSUMMED = ((43, 6),)  # payload_chars, checksum_chars

CHECKSUM_MESSAGE = (
    "Bearer key failed checksum; it may be mistyped. "
    "Re-read the key from disk or your keystore."
)


class KeyChecksumError(ValueError):
    """The token looks like a DMZ key but its checksum or length is wrong."""


def _checksum(payload: str, nchars: int = CHECKSUM_CHARS) -> str:
    digest = hashlib.sha256(payload.encode("ascii")).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return encoded[:nchars]


def _random_payload(payload_chars: int) -> str:
    nbytes = max(1, (payload_chars * 3 + 3) // 4)
    raw = secrets.token_urlsafe(nbytes)
    while len(raw) < payload_chars:
        raw += secrets.token_urlsafe(nbytes)
    return raw[:payload_chars]


def _prefixed_key(prefix: str, payload_chars: int) -> str:
    payload = _random_payload(payload_chars)
    return prefix + payload + _checksum(payload)


def generate_agent_key(payload_chars: int = DEFAULT_PAYLOAD_CHARS) -> str:
    return _prefixed_key(AGENT_PREFIX, payload_chars)


def generate_admin_token(payload_chars: int = DEFAULT_PAYLOAD_CHARS) -> str:
    return _prefixed_key(ADMIN_PREFIX, payload_chars)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_namespace(key: str) -> str | None:
    """Cosmetic prefix metadata (#17); auth always goes through the hash."""
    if key.startswith(ADMIN_PREFIX):
        return "admin"
    if key.startswith(AGENT_PREFIX):
        return "agent"
    return None


def _body_and_prefix(token: str) -> tuple[str, str] | None:
    if token.startswith(ADMIN_PREFIX):
        return ADMIN_PREFIX, token[len(ADMIN_PREFIX) :]
    if token.startswith(AGENT_PREFIX):
        return AGENT_PREFIX, token[len(AGENT_PREFIX) :]
    return None


def _checksummed_ok(body: str, payload_chars: int, checksum_chars: int) -> bool:
    if len(body) != payload_chars + checksum_chars:
        return False
    payload, check = body[:payload_chars], body[payload_chars:]
    expected = _checksum(payload, checksum_chars)
    return hmac.compare_digest(check, expected)


def _agent_checksum_status(body: str) -> str:
    n = len(body)
    if n == LEGACY_UNCHECKED_BODY_CHARS:
        return "legacy"
    for payload_chars, checksum_chars in LEGACY_CHECKSUMMED:
        if n == payload_chars + checksum_chars:
            return "ok" if _checksummed_ok(body, payload_chars, checksum_chars) else "invalid"
    if n >= MIN_PAYLOAD_CHARS + CHECKSUM_CHARS:
        payload_chars = n - CHECKSUM_CHARS
        if _checksummed_ok(body, payload_chars, CHECKSUM_CHARS):
            return "ok"
        return "invalid"
    return "invalid"


def key_checksum_status(token: str) -> str:
    """Classify a bearer token's checksum.

    ``ok`` — checksummed format, checksum matches.
    ``legacy`` — known unchecked length, or a config-defined admin token.
    ``invalid`` — DMZ prefix but wrong length or checksum (likely a typo).
    ``other`` — not a DMZ-prefixed key (unknown/garbage).
    """
    parsed = _body_and_prefix(token)
    if parsed is None:
        return "other"
    prefix, body = parsed
    if prefix == AGENT_PREFIX:
        return _agent_checksum_status(body)
    for payload_chars, checksum_chars in LEGACY_CHECKSUMMED:
        if len(body) == payload_chars + checksum_chars:
            if _checksummed_ok(body, payload_chars, checksum_chars):
                return "ok"
            return "invalid"
    if len(body) >= MIN_PAYLOAD_CHARS + CHECKSUM_CHARS:
        payload_chars = len(body) - CHECKSUM_CHARS
        if _checksummed_ok(body, payload_chars, CHECKSUM_CHARS):
            return "ok"
    # Operator-defined admin tokens in config.yaml are not required to use
    # generate_admin_token(); treat non-matching bodies as legacy.
    return "legacy"


def assert_key_checksum(token: str) -> None:
    """Raise :class:`KeyChecksumError` when a DMZ key looks mistyped."""
    if key_checksum_status(token) == "invalid":
        raise KeyChecksumError(CHECKSUM_MESSAGE)
