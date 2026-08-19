"""T3.11-T3.14: the synchronous invoke pipeline (system-prd-v2.md + dispatch-v2.md).

Pipeline: request schema validation â†’ request arbiter check (exactly once, #4)
â†’ retry loop [frame â†’ dispatch â†’ response schema validation â†’ response
arbiter check] â†’ 200 result; exhaustion â†’ 502 provider_failed.

Failure mapping (#1/#6): request-side arbiter transport failure â†’ 503
arbiter_unavailable (no dispatch); response-side arbiter transport failure is
a retryable attempt; arbiter configuration faults â†’ 500 internal_error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from llmdmz.core import storage
from llmdmz.core.config import Config
from llmdmz.core.models import Action, ActionVersion, Agent
from llmdmz.dispatch.adapters import (
    build_structured_framing,
    build_unstructured_framing,
)
from llmdmz.dispatch.interfaces import (
    ArbiterClient,
    ArbiterTransportError,
    Framing,
    ProviderTransport,
)
from llmdmz.registry import validate_payload


@dataclass
class InvokeResult:
    status: int
    code: str | None = None  # None on success
    result: dict[str, Any] | None = None
    detail: Any = field(default=None)


def run_invoke(
    session: Session,
    config: Config,
    *,
    action: Action,
    active: ActionVersion,
    agent: Agent,
    request_payload: Any,
    arbiter: ArbiterClient,
    transport: ProviderTransport,
) -> InvokeResult:
    payload = active.payload
    instructions = payload.get("provider_instructions", "")
    request_arbiter_instructions = payload.get("request_arbiter_instructions", "")
    response_arbiter_instructions = payload.get("response_arbiter_instructions", "")
    response_schema = payload["response_schema"]

    # 1. Structural request validation (terminal, transparent detail).
    errors = validate_payload(payload["request_schema"], request_payload)
    if errors:
        return InvokeResult(422, "request_schema_invalid", detail={"errors": errors})

    # 2. Request arbiter check â€” runs exactly once (#4).
    try:
        verdict = arbiter.check(
            side="request",
            action_id=action.id,
            payload=request_payload,
            extra_instructions=request_arbiter_instructions,
        )
    except ArbiterTransportError as exc:
        return InvokeResult(503, "arbiter_unavailable", detail={"reason": str(exc)})
    # ArbiterConfigFault propagates -> 500 internal_error (app error handler).
    verdict_dict = {"approved": verdict.approved, "reason": verdict.reason}
    if not verdict.approved:
        return InvokeResult(422, "arbiter_rejected", detail=verdict_dict)

    # Request accepted â€” log it, then dispatch.
    request_row = storage.log_request(
        session,
        action_id=action.id,
        agent_id=agent.id,
        active_version_id=active.id,
        request_payload=request_payload,
        outcome="completed",
        request_verdict=verdict_dict,
        finished=False,
    )

    delivery = agent.delivery_config or {}
    retries = int(delivery.get("retries", config.dispatch_retries))
    timeout = int(delivery.get("timeout", config.dispatch_timeout))
    protocol = delivery.get("protocol", "post")

    previous_error: str | None = None
    total_attempts = retries + 1
    for attempt_number in range(1, total_attempts + 1):
        framing = _build_framing(
            protocol=protocol,
            instructions=instructions,
            response_schema=response_schema,
            request_payload=request_payload,
            delivery=delivery,
            timeout=timeout,
            previous_error=previous_error,
        )
        attempt_row = storage.log_attempt(
            session,
            request_id=request_row.id,
            attempt_number=attempt_number,
            framing=_framing_log(framing),
        )
        previous_error = _run_attempt(
            session,
            arbiter=arbiter,
            transport=transport,
            action=action,
            request_row=request_row,
            attempt_row=attempt_row,
            framing=framing,
            response_schema=response_schema,
            response_arbiter_instructions=response_arbiter_instructions,
        )
        if previous_error is None:
            return InvokeResult(
                200,
                result={
                    "result": request_row.response_payload,
                    "action": action.id,
                    "version": active.version_number,
                },
            )

    storage.finish_request(session, request_row, outcome="provider_failed")
    # The client is told the provider failed, not why (dispatch-v2.md).
    return InvokeResult(502, "provider_failed")


def _run_attempt(
    session: Session,
    *,
    arbiter: ArbiterClient,
    transport: ProviderTransport,
    action: Action,
    request_row,
    attempt_row,
    framing: Framing,
    response_schema: dict,
    response_arbiter_instructions: str,
) -> str | None:
    """One dispatch attempt. Returns None on success, else the retry-injected error."""
    outcome = transport.deliver(framing)
    if outcome.error_class is not None or outcome.payload is None:
        attempt_row.error_class = outcome.error_class or "protocol"
        attempt_row.error_detail = outcome.error_detail
        return f"transport error ({attempt_row.error_class}): {outcome.error_detail}"

    candidate = outcome.payload
    errors = validate_payload(response_schema, candidate)
    if errors:
        attempt_row.error_class = "response_schema_invalid"
        attempt_row.error_detail = "; ".join(errors)
        return "response schema violations: " + "; ".join(errors)

    try:
        r_verdict = arbiter.check(
            side="response",
            action_id=action.id,
            payload=candidate,
            extra_instructions=response_arbiter_instructions,
        )
    except ArbiterTransportError as exc:
        # Response-side arbiter outage = retryable attempt (#1).
        attempt_row.error_class = "arbiter_transport"
        attempt_row.error_detail = str(exc)
        return f"arbiter unavailable: {exc}"

    if not r_verdict.approved:
        attempt_row.error_class = "arbiter_rejected"
        attempt_row.error_detail = r_verdict.reason
        return f"arbiter rejected your response: {r_verdict.reason}"

    storage.finish_request(
        session, request_row, outcome="completed", response_payload=candidate
    )
    return None


def _build_framing(
    *,
    protocol: str,
    instructions: str,
    response_schema: dict[str, Any],
    request_payload: dict[str, Any],
    delivery: dict[str, Any],
    timeout: int,
    previous_error: str | None,
) -> Framing:
    if protocol == "completions":
        system, user = build_structured_framing(
            instructions=instructions,
            response_schema=response_schema,
            request_payload=request_payload,
            previous_error=previous_error,
        )
        return Framing(
            protocol=protocol,
            system_prompt=system,
            user_prompt=user,
            model=delivery.get("model", ""),
            endpoint=delivery.get("endpoint", ""),
            headers=delivery.get("headers"),
            timeout=timeout,
        )
    text = build_unstructured_framing(
        instructions=instructions,
        response_schema=response_schema,
        request_payload=request_payload,
        previous_error=previous_error,
    )
    return Framing(
        protocol=protocol,
        text=text,
        endpoint=delivery.get("endpoint", ""),
        command=delivery.get("command", ""),
        headers=delivery.get("headers"),
        timeout=timeout,
    )


def _framing_log(framing: Framing) -> dict[str, Any]:
    """Observability copy of the framing (dispatch-v2.md Observability)."""
    log: dict[str, Any] = {"protocol": framing.protocol}
    if framing.protocol == "completions":
        log["system_prompt"] = framing.system_prompt
        log["user_prompt"] = framing.user_prompt
        log["model"] = framing.model
    else:
        log["text"] = framing.text
    return log
