"""T3.2: Arbiter verdict parsing (schemas-v2.md \"Verdict format\").

JSON parse with a fallback that extracts the first ``{...}`` block from the
reply; ``approved`` is coerced to bool; a missing reason defaults to
\"No reason provided\"; an unparseable verdict is a failed check.
"""

from __future__ import annotations

import json
import re
from typing import Any

from admz.dispatch.interfaces import Verdict

_FALLBACK_RE = re.compile(r"\{.*?\}", re.DOTALL)
_FAILED = Verdict(approved=False, reason="Arbiter reply was not parseable as a verdict.")


def parse_verdict(reply: str) -> Verdict:
    """Parse an arbiter model reply into a Verdict; unparseable = failed check."""
    if not isinstance(reply, str):
        return _FAILED
    parsed = _try_json(reply.strip())
    if parsed is None:
        for match in _FALLBACK_RE.finditer(reply):
            candidate = _try_json(match.group(0))
            if isinstance(candidate, dict) and "approved" in candidate:
                parsed = candidate
                break
        if parsed is None:
            return _FAILED
    if not isinstance(parsed, dict) or "approved" not in parsed:
        return _FAILED
    return Verdict(
        approved=_coerce_bool(parsed["approved"]),
        reason=str(parsed.get("reason") or "No reason provided"),
    )


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)
