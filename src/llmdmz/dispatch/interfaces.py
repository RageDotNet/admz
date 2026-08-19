"""T3.1: ArbiterClient + ProviderTransport interfaces — the DI seam (#31).

Production adapters (LiteLLM arbiter, HTTP/subprocess transports) implement
these protocols; tests inject fakes. No network access lives outside the
adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class Verdict:
    """Parsed arbiter verdict (schemas-v2.md \"Verdict format\")."""

    approved: bool
    reason: str


class ArbiterTransportError(Exception):
    """Transient arbiter failure (rate limit, 5xx, network, timeout) — #1/#6."""


class ArbiterConfigFault(Exception):
    """Operator configuration fault (bad key, unknown model) — 500, no retry."""


@runtime_checkable
class ArbiterClient(Protocol):
    """One check per call; the DMZ does not retry the arbiter call itself."""

    def check(
        self,
        *,
        side: str,  # "request" | "response"
        action_id: str,
        payload: Any,
        extra_instructions: str = "",
    ) -> Verdict:
        """Return a parsed verdict.

        Raises ArbiterTransportError on transient failures and
        ArbiterConfigFault on operator-configuration faults. An unparseable
        verdict is a *failed check* (approved=False), not an exception.
        """
        ...  # pragma: no cover


@dataclass
class Framing:
    """What a provider transport receives for one attempt (dispatch-v2.md)."""

    protocol: str  # post | exec | completions
    # unstructured framing (post/exec): the full plain-text payload
    text: str = ""
    # structured framing (completions): system/user split
    system_prompt: str = ""
    user_prompt: str = ""
    # delivery-config fields the adapter needs
    endpoint: str = ""
    command: str = ""
    headers: dict[str, str] | None = None
    model: str = ""
    timeout: int = 180


@dataclass
class ProviderResult:
    """Outcome of one transport attempt."""

    payload: dict[str, Any] | None = None  # parsed JSON payload on success
    error_class: str | None = None  # transport | timeout | protocol
    error_detail: str | None = None
    exit_code: int | None = None  # exec only
    stderr: str | None = None  # exec only


@runtime_checkable
class ProviderTransport(Protocol):
    def deliver(self, framing: Framing) -> ProviderResult:
        ...
