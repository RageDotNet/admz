"""A2A protocol gateway/proxy for the LLM DMZ."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import request as flask_request
from python_a2a import A2AClient, A2AServer, Task, TaskState, TaskStatus, run_server
from python_a2a.server.http import create_flask_app

from dmz.a2a_protocol import (
    build_failed_task,
    build_requestee_task,
    build_requestor_response_task,
    build_waiting_task,
    extract_llmdmz_envelope,
    extract_response_payload,
)
from dmz.agents import AgentRegistry, AuthError
from dmz.arbiter import check_request, check_response
from dmz.admin_routes import register_admin_routes
from dmz.review_routes import register_review_routes
from dmz.schemas import SchemaRegistry
from dmz.storage import Storage
from llm_logging import get_logger

load_dotenv()

logger = get_logger("a2admz")


class A2ADmzGateway(A2AServer):
    """A2A-facing DMZ proxy with schema and arbiter validation."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.agent_registry = AgentRegistry()
        self.schema_registry = SchemaRegistry()
        self.storage = Storage()

    def _authenticate_requestor(self) -> str:
        agent_id = flask_request.headers.get("X-Agent-Id")
        agent_key = flask_request.headers.get("X-Agent-Key")
        context = self.agent_registry.authenticate(agent_id, agent_key)
        if context.role != "requestor":
            raise AuthError("Only requestor agents may submit DMZ requests via A2A")
        return context.agent_id

    def _normalize_envelope(self, envelope: dict[str, Any], task: Task) -> dict[str, Any]:
        schema_id = envelope.get("schema_id")
        request_id = envelope.get("request_id") or task.id or str(uuid.uuid4())
        payload = envelope.get("payload")
        if payload is None and envelope.get("request_payload") is not None:
            payload = envelope["request_payload"]
        if not schema_id or not isinstance(payload, dict):
            raise ValueError("schema_id and payload object are required in the llmdmz envelope")
        return {
            "schema_id": schema_id,
            "request_id": request_id,
            "payload": payload,
        }

    def _send_to_review(
        self,
        *,
        request_id: str,
        review_type: str,
        reason: str,
        payload_snapshot: dict[str, Any],
    ) -> str:
        item = self.storage.enqueue_review(
            request_id=request_id,
            review_type=review_type,
            reason=reason,
            payload_snapshot=payload_snapshot,
        )
        self.storage.update_request(request_id, status=f"pending_review_{review_type}")
        return item.id

    def _validate_request(self, schema_id: str, payload: dict[str, Any]) -> None:
        self.schema_registry.validate_request(schema_id, payload)

    def _validate_response(self, schema_id: str, payload: dict[str, Any]) -> None:
        self.schema_registry.validate_response(schema_id, payload)

    def _forward_to_requestee(
        self,
        *,
        binding,
        request_id: str,
        schema_id: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not binding.requestee_a2a_url:
            raise RuntimeError(f"No requestee_a2a_url configured for schema {schema_id}")

        pair = self.schema_registry.get(schema_id)
        requestee_task = build_requestee_task(
            request_id=request_id,
            schema_id=schema_id,
            request_payload=request_payload,
            response_schema=pair.response_schema,
            description=binding.description,
        )

        requestee_agent = self.agent_registry.get(binding.requestee_id)
        headers: dict[str, str] = {}
        if requestee_agent:
            headers = {
                "X-Agent-Id": requestee_agent.id,
                "X-Agent-Key": requestee_agent.key,
            }

        logger.info(
            "Forwarding to requestee url=%s request_id=%s schema_id=%s",
            binding.requestee_a2a_url,
            request_id,
            schema_id,
        )
        client = A2AClient(binding.requestee_a2a_url, headers=headers, google_a2a_compatible=True)
        result_task = client._send_task(requestee_task)  # noqa: SLF001 - python-a2a task API

        if result_task.status.state in {TaskState.FAILED, TaskState.CANCELED}:
            raise RuntimeError(f"Requestee failed: {result_task.status.message}")

        response_payload = extract_response_payload(result_task)
        if response_payload is None:
            raise RuntimeError("Requestee returned no response_payload")
        return response_payload

    def _continue_existing(self, task: Task, record) -> Task | None:
        request_id = record.request_id
        schema_id = record.schema_id
        binding = self.schema_registry.get(schema_id).binding

        if record.status == "completed" and record.response_payload is not None:
            return build_requestor_response_task(
                task=task,
                request_id=request_id,
                schema_id=schema_id,
                response_payload=record.response_payload,
                notes=record.arbiter_response_notes,
            )

        if record.status == "pending_requestee":
            try:
                response_payload = self._forward_to_requestee(
                    binding=binding,
                    request_id=request_id,
                    schema_id=schema_id,
                    request_payload=record.request_payload,
                )
            except Exception as exc:  # noqa: BLE001
                review_id = self._send_to_review(
                    request_id=request_id,
                    review_type="response",
                    reason=f"Requestee error: {exc}",
                    payload_snapshot={"error": str(exc)},
                )
                return build_waiting_task(task, request_id=request_id, reason=str(exc), review_id=review_id)

            try:
                self._validate_response(schema_id, response_payload)
                pair = self.schema_registry.get(schema_id)
                verdict = check_response(
                    schema_id,
                    record.request_payload,
                    response_payload,
                    response_schema=pair.response_schema,
                    operation_description=binding.description,
                )
            except Exception as exc:  # noqa: BLE001
                review_id = self._send_to_review(
                    request_id=request_id,
                    review_type="response",
                    reason=f"Response validation failed: {exc}",
                    payload_snapshot=response_payload,
                )
                return build_waiting_task(task, request_id=request_id, reason=str(exc), review_id=review_id)

            if not verdict["approved"]:
                review_id = self._send_to_review(
                    request_id=request_id,
                    review_type="response",
                    reason=f"Arbiter rejected response: {verdict['reason']}",
                    payload_snapshot=response_payload,
                )
                self.storage.update_request(request_id, arbiter_response_notes=verdict["reason"])
                return build_waiting_task(
                    task,
                    request_id=request_id,
                    reason=verdict["reason"],
                    review_id=review_id,
                )

            self.storage.update_request(
                request_id,
                status="completed",
                response_payload=response_payload,
                arbiter_response_notes=verdict["reason"],
            )
            return build_requestor_response_task(
                task=task,
                request_id=request_id,
                schema_id=schema_id,
                response_payload=response_payload,
                notes=verdict["reason"],
            )

        if record.status.startswith("pending_review"):
            review_id = None
            reviews = self.storage.list_pending_reviews(limit=200)
            for item in reviews:
                if item.request_id == request_id:
                    review_id = item.id
                    break
            reason = record.validation_errors or record.arbiter_request_notes or "Awaiting human review"
            return build_waiting_task(task, request_id=request_id, reason=str(reason), review_id=review_id)

        if record.status == "rejected":
            return build_failed_task(task, request_id=request_id, reason="Request was rejected")

        return None

    def handle_task(self, task: Task) -> Task:
        try:
            return self._handle_task_impl(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled gateway error task_id=%s", task.id)
            request_id = task.id
            envelope = extract_llmdmz_envelope(task)
            if envelope and envelope.get("request_id"):
                request_id = envelope["request_id"]
            return build_failed_task(task, request_id=request_id, reason=f"Gateway error: {exc}")

    def _handle_task_impl(self, task: Task) -> Task:
        try:
            requestor_id = self._authenticate_requestor()
        except AuthError as exc:
            return build_failed_task(task, request_id=task.id, reason=str(exc))

        raw_envelope = extract_llmdmz_envelope(task)
        if raw_envelope is None:
            return build_failed_task(
                task,
                request_id=task.id,
                reason=(
                    "Missing llmdmz envelope. Include metadata.llmdmz or a JSON message with "
                    "schema_id, request_id, and payload."
                ),
            )

        try:
            envelope = self._normalize_envelope(raw_envelope, task)
        except ValueError as exc:
            return build_failed_task(task, request_id=task.id, reason=str(exc))

        schema_id = envelope["schema_id"]
        request_id = envelope["request_id"]
        payload = envelope["payload"]

        try:
            binding = self.schema_registry.get(schema_id).binding
        except KeyError as exc:
            return build_failed_task(task, request_id=request_id, reason=str(exc))

        if binding.requestor_id != requestor_id:
            return build_failed_task(
                task,
                request_id=request_id,
                reason=f"Requestor {requestor_id} is not authorized for schema {schema_id}",
            )

        logger.info(
            "A2A DMZ request received request_id=%s schema_id=%s requestor=%s",
            request_id,
            schema_id,
            requestor_id,
        )

        try:
            existing = self.storage.get_request(request_id)
        except KeyError:
            existing = None

        if existing is not None:
            continued = self._continue_existing(task, existing)
            if continued is not None:
                return continued

        if existing is None:
            try:
                self.storage.create_request(
                    request_id=request_id,
                    schema_id=schema_id,
                    requestor_id=requestor_id,
                    requestee_id=binding.requestee_id,
                    request_payload=payload,
                )
            except Exception:
                existing = self.storage.get_request(request_id)

        try:
            self._validate_request(schema_id, payload)
            verdict = check_request(schema_id, payload)
        except Exception as exc:  # noqa: BLE001
            review_id = self._send_to_review(
                request_id=request_id,
                review_type="request",
                reason=f"Request validation failed: {exc}",
                payload_snapshot=payload,
            )
            self.storage.update_request(request_id, validation_errors=str(exc))
            return build_waiting_task(task, request_id=request_id, reason=str(exc), review_id=review_id)

        if not verdict["approved"]:
            review_id = self._send_to_review(
                request_id=request_id,
                review_type="request",
                reason=f"Arbiter rejected request: {verdict['reason']}",
                payload_snapshot=payload,
            )
            self.storage.update_request(request_id, arbiter_request_notes=verdict["reason"])
            return build_waiting_task(
                task,
                request_id=request_id,
                reason=verdict["reason"],
                review_id=review_id,
            )

        self.storage.update_request(
            request_id,
            status="pending_requestee",
            arbiter_request_notes=verdict["reason"],
        )
        record = self.storage.get_request(request_id)
        continued = self._continue_existing(task, record)
        if continued is not None:
            return continued

        return build_failed_task(task, request_id=request_id, reason="Unexpected gateway state")


def main() -> None:
    host = os.getenv("A2A_DMZ_HOST", "127.0.0.1")
    port = int(os.getenv("A2A_DMZ_PORT", "5000"))
    url = os.getenv("A2A_DMZ_URL", f"http://{host}:{port}")

    gateway = A2ADmzGateway(
        url=url,
        name="LLM DMZ A2A Gateway",
        description=(
            "Schema-validated, LLM-arbitrated A2A proxy between untrusted requestors "
            "and trusted internal requestees"
        ),
        version="1.0.0",
    )

    app = create_flask_app(gateway)
    app.template_folder = str(Path(__file__).resolve().parent / "templates")
    register_review_routes(app, agent_registry=gateway.agent_registry, storage=gateway.storage)
    register_admin_routes(
        app,
        agent_registry=gateway.agent_registry,
        schema_registry=gateway.schema_registry,
        storage=gateway.storage,
    )

    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"Starting A2A DMZ gateway on http://{host}:{port}/a2a")
    print(f"Review API available at http://{host}:{port}/api/v1/review/pending")
    print(f"Admin UI available at http://{host}:{port}/admin")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
