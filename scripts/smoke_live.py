#!/usr/bin/env python3
"""Manually-run live smoke test (T3.16) — real LiteLLM arbiter.

This is intentionally NOT part of the offline pytest suite (#31). It verifies
the production LiteLLM arbiter adapter against a live provider. Run it with
the same credentials you use for invokes, for example:

    OPENROUTER_API_KEY=sk-or-...  python scripts/smoke_live.py

Or OPENAI_API_KEY / ANTHROPIC_API_KEY with a matching ARBITER_MODEL. Optional
ARBITER_API_KEY forces the key passed to LiteLLM.

Exit code 0 = arbiter adapter round-tripped with a parseable verdict.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from admz.core.config import AdminAccount, Config  # noqa: E402
from admz.dispatch.adapters import LiteLLMArbiterClient  # noqa: E402

_NATIVE_KEYS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def main() -> int:
    override = (os.environ.get("ARBITER_API_KEY") or "").strip()
    if not override and not any(os.environ.get(k) for k in _NATIVE_KEYS):
        print(
            "Set OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "or ARBITER_API_KEY first."
        )
        return 2
    config = Config(
        database_url="sqlite:///:memory:",
        secret_key="smoke",
        app_port=8000,
        flask_debug=False,
        log_level="INFO",
        session_cookie_secure=False,
        arbiter_model=os.environ.get("ARBITER_MODEL", "openrouter/openai/gpt-4o-mini"),
        arbiter_api_key=override,
        arbiter_timeout=30,
        arbiter_max_tokens=512,
        arbiter_temperature=0.0,
        dispatch_retries=2,
        dispatch_timeout=180,
        key_payload_chars=14,
        admins=(AdminAccount(username="admin", password="pw", token=None),),
    )
    client = LiteLLMArbiterClient(config)
    verdict = client.check(
        side="request",
        action_id="smoke",
        payload={"name": "Ada Lovelace"},
    )
    print(f"verdict: approved={verdict.approved} reason={verdict.reason!r}")
    print("arbiter adapter OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
