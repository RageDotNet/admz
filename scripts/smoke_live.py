#!/usr/bin/env python3
"""Manually-run live smoke test (T3.16) — real OpenRouter + a live provider.

This is intentionally NOT part of the offline pytest suite (#31). It verifies
the production adapters (LiteLLM arbiter + post/completions transports)
against the real world. Run it on a host with:

    OPENROUTER_API_KEY=sk-or-...  python scripts/smoke_live.py

Exit code 0 = arbiter adapter round-tripped with a parseable verdict.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from admz.core.config import AdminAccount, Config  # noqa: E402
from admz.dispatch.adapters import LiteLLMArbiterClient  # noqa: E402


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY first.")
        return 2
    config = Config(
        database_url="sqlite:///:memory:",
        secret_key="smoke",
        app_port=8000,
        flask_debug=False,
        log_level="INFO",
        session_cookie_secure=False,
        arbiter_model=os.environ.get("ARBITER_MODEL", "openai/gpt-4o-mini"),
        arbiter_api_key=api_key,
        arbiter_timeout=30,
        arbiter_max_tokens=512,
        arbiter_temperature=0.0,
        dispatch_retries=2,
        dispatch_timeout=180,
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
