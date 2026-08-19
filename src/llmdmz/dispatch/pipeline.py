"""T3.11-T3.14: the synchronous invoke pipeline (system-prd-v2.md + dispatch-v2.md).

Pipeline: request schema validation â†’ request arbiter check (exactly once, #4)
â†’ retry loop [frame â†’ dispatch â†’ response schema validation â†’ response
arbiter check] â†’ 200 result; exhaustion â†’ 502 provider_failed.

Failure mapping (#1/#6): request-side arbiter transport failure â†’ 503
arbiter_unavailable (no dispatch); response-side arbiter transport failure is
a retryable attempt; arbiter configuration faults â†’ 500 internal_error.
"""

from __future__ import annotations

import json
import logging
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
from llmdmz.dispatch.arbiter_prompts import resolve_risk_focus
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


_log = logging.getLogger("llmdmz.dispatch")


def _log_step(event: str, request_id: str | None = None, **fields: Any) -> None:
    """Log a pipeline step. Uses the Flask app logger when in an app context
    (so lines appear in the flask server logs), else a module logger."""
    rid = f" req={request_id[:8]}" if request_id else ""
    extra = "".join(f" {k}={v}" for k, v in fields.items())
    msg = f"[dispatch] {event}{rid}{extra}"
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            current_app.logger.info(msg)
            return
    except Exception:  # pragma: no cover - logging must never break dispatch
        pass
    _log.info(msg)


def _arbiter_context(
    *,
    action: Action,
    action_description: str,
    provider_instructions: str,
    request_schema: dict,
    response_schema: dict | None = None,
    original_request: Any = None,
    risk: str = "",
) -> str:
    """Authoritative context for an arbiter evaluation.

    The arbiter must judge payloads against the action's declared contract:
    its schemas (including each field's description — what the field means and
    why it may contain), the action's name/description, and the provider's
    operating instructions. All of these are authoritative and sanctioned by
    the DMZ operator: content that matches them is allowed.
    """
    lines = [
        "AUTHORITATIVE ACTION CONTRACT — the following is defined by the DMZ",
        "operator and is trusted, sanctioned, and ALLOWED. Content matching",
        "this contract (including any field descriptions below, which define",
        "what each field may legitimately contain) must be APPROVED:",
        "",
        f"Action name: {action.id}",
    ]
    if risk:
        focus = resolve_risk_focus(risk)
        if focus:
            lines.insert(0, focus)
    if action_description:
        lines.append(f"Action description: {action_description}")
    if provider_instructions:
        lines.append(
            "Provider instructions (authoritative; the provider is expected "
            f"to follow these): {provider_instructions}"
        )
    lines.append("")
    lines.append(
        "Request schema (authoritative; a request payload that validates "
        "against this schema and matches its field descriptions is allowed):"
    )
    lines.append(json.dumps(request_schema, ensure_ascii=False, indent=2))
    if response_schema is not None:
        lines.append("")
        lines.append(
            "Response schema (authoritative; a response payload that validates "
            "against this schema and matches its field descriptions — e.g. an "
            "email or phone field whose description permits contact details — "
            "is allowed):"
        )
        lines.append(json.dumps(response_schema, ensure_ascii=False, indent=2))
    if original_request is not None:
        lines.append("")
        lines.append(
            "The client's original request for this dispatch (judge the "
            "response against it):"
        )
        lines.append(json.dumps(original_request, ensure_ascii=False, indent=2))
    return "\n".join(lines)


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
    action_description = str(payload.get("description", ""))
    request_ctx = _arbiter_context(
        action=action,
        action_description=action_description,
        provider_instructions=instructions,
        request_schema=payload["request_schema"],
        risk=payload.get("request_risk", ""),
    )
    if request_arbiter_instructions:
        request_ctx = f"{request_arbiter_instructions}\n\n{request_ctx}"
    response_ctx = _arbiter_context(
        action=action,
        action_description=action_description,
        provider_instructions=instructions,
        request_schema=payload["request_schema"],
        response_schema=response_schema,
        original_request=request_payload,
        risk=payload.get("response_risk", ""),
    )
    if response_arbiter_instructions:
        response_ctx = f"{response_arbiter_instructions}\n\n{response_ctx}"

    # 0. Log the request the moment it arrives so it shows in-flight in the
    # console request log while the pipeline works on it.
    request_row = storage.log_request(
        session,
        action_id=action.id,
        agent_id=agent.id,
        active_version_id=active.id,
        request_payload=request_payload,
        outcome="received",
        finished=False,
    )
    _log_step("received request", request_row.id, action=action.id, agent=agent.id)
    # 1. Structural request validation (terminal, transparent detail).
    errors = validate_payload(payload["request_schema"], request_payload)
    if errors:
        storage.finish_request(session, request_row, outcome="request_schema_invalid")
        _log_step("request schema invalid", request_row.id, errors=errors)
        return InvokeResult(422, "request_schema_invalid", detail={"errors": errors})

    # 2. Request arbiter check â€” runs exactly once (#4).
    storage.set_request_state(session, request_row, outcome="arbiter_reviewing_request")
    _log_step("arbiter reviewing request", request_row.id, action=action.id)
    try:
        verdict = arbiter.check(
            side="request",
            action_id=action.id,
            payload=request_payload,
            extra_instructions=request_ctx,
        )
    except ArbiterTransportError as exc:
        storage.finish_request(session, request_row, outcome="arbiter_unavailable")
        _log_step("request arbiter unavailable", request_row.id, reason=str(exc))
        return InvokeResult(503, "arbiter_unavailable", detail={"reason": str(exc)})
    # ArbiterConfigFault propagates -> 500 internal_error (app error handler).
    verdict_dict = {"approved": verdict.approved, "reason": verdict.reason}
    if not verdict.approved:
        storage.finish_request(
            session, request_row, outcome="arbiter_rejected", request_verdict=verdict_dict
        )
        _log_step("arbiter rejected request", request_row.id, reason=verdict.reason)
        return InvokeResult(422, "arbiter_rejected", detail=verdict_dict)
    _log_step("arbiter approved request", request_row.id)
    request_row.request_verdict = verdict_dict

    delivery = agent.delivery_config or {}
    retries = int(delivery.get("retries", config.dispatch_retries))
    timeout = int(delivery.get("timeout", config.dispatch_timeout))
    protocol = delivery.get("protocol", "post")

    previous_error: str | None = None
    total_attempts = retries + 1
    for attempt_number in range(1, total_attempts + 1):
        storage.set_request_state(session, request_row, outcome="dispatching")
        _log_step("dispatching to provider", request_row.id, attempt=attempt_number, protocol=protocol)
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
            request_payload=request_payload,
        )
        # Commit immediately: the attempt row (with its request payload) must
        # be durable before we hand off to the provider transport, which may
        # use other sessions; we also mutate this row post-delivery.
        session.commit()
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
            response_ctx=response_ctx,
        )
        if previous_error is None:
            _log_step("request completed", request_row.id)
            return InvokeResult(
                200,
                result={
                    "result": request_row.response_payload,
                    "action": action.id,
                    "version": active.version_number,
                },
            )

    storage.finish_request(
        session, request_row, outcome="provider_failed"
    )
    _log_step(
        "provider failed (retries exhausted)", request_row.id,
        attempts=total_attempts, final_error=previous_error,
    )
    # The client is told the provider failed, not why (dispatch-v2.md) — but the
    # final attempt's failure is surfaced in `detail` for operator diagnosis.
    return InvokeResult(
        502,
        "provider_failed",
        detail={"final_error": previous_error, "attempts": total_attempts},
    )


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
    response_ctx: str,
) -> str | None:
    """One dispatch attempt. Returns None on success, else the retry-injected error."""
    _log_step("delivery to provider", request_row.id, attempt=attempt_row.attempt_number)
    outcome = transport.deliver(framing)
    if outcome.error_class is not None or outcome.payload is None:
        attempt_row.error_class = outcome.error_class or "protocol"
        attempt_row.error_detail = outcome.error_detail
        _log_step("transport error", request_row.id, attempt=attempt_row.attempt_number, error=attempt_row.error_class)
        return f"transport error ({attempt_row.error_class}): {outcome.error_detail}"

    candidate = outcome.payload
    # Persist the candidate now, before any rejection path, so operators can
    # inspect exactly what the provider returned on every attempt.
    attempt_row.response_payload = candidate
    errors = validate_payload(response_schema, candidate)
    if errors:
        attempt_row.error_class = "response_schema_invalid"
        attempt_row.error_detail = "; ".join(errors)
        _log_step("response schema violations", request_row.id, attempt=attempt_row.attempt_number)
        return "response schema violations: " + "; ".join(errors)

    storage.set_request_state(session, request_row, outcome="arbiter_reviewing_response")
    _log_step("arbiter reviewing response", request_row.id, attempt=attempt_row.attempt_number)
    # Give the arbiter the full authoritative contract: action description,
    # provider instructions, both schemas (with field descriptions), and the
    # original request, so it can judge scope instead of screening blind.
    extra = response_ctx
    try:
        r_verdict = arbiter.check(
            side="response",
            action_id=action.id,
            payload=candidate,
            extra_instructions=extra,
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
