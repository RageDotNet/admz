"""Trusted internal A2A requestee that fulfills DMZ schema operations."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from python_a2a import A2AServer, Task, TaskState, TaskStatus, run_server

from crmtool import search_contacts
from dmz.a2a_protocol import extract_llmdmz_envelope
from llm_logging import get_logger

load_dotenv()

logger = get_logger("a2a_requestee")


def fulfill_crm_search(payload: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []

    def add_matches(query: str) -> None:
        for contact in search_contacts(query):
            if contact["id"] not in seen:
                seen.add(contact["id"])
                records.append(contact)

    if name := payload.get("name"):
        add_matches(str(name))
    if company := payload.get("company"):
        add_matches(str(company))

    return {"records": records}


HANDLERS = {
    "crm_search": fulfill_crm_search,
}


class RequesteeServer(A2AServer):
    def handle_task(self, task: Task) -> Task:
        envelope = extract_llmdmz_envelope(task)
        if envelope is None or envelope.get("type") != "request":
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"error": "Expected llmdmz request envelope in task metadata or message"},
            )
            task.artifacts = [
                {
                    "parts": [
                        {
                            "type": "text",
                            "text": (
                                "Send a DMZ request envelope with schema_id, request_id, "
                                "and request_payload."
                            ),
                        }
                    ]
                }
            ]
            return task

        schema_id = envelope.get("schema_id")
        request_id = envelope.get("request_id")
        request_payload = envelope.get("request_payload")
        response_schema = envelope.get("response_schema")

        if not schema_id or not request_id or not isinstance(request_payload, dict):
            return self._fail(task, "schema_id, request_id, and request_payload are required")

        handler = HANDLERS.get(schema_id)
        if handler is None:
            return self._fail(task, f"Unsupported schema_id: {schema_id}")

        logger.info(
            "Requestee handling request_id=%s schema_id=%s payload=%s",
            request_id,
            schema_id,
            json.dumps(request_payload),
        )

        try:
            response_payload = handler(request_payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Requestee handler failed request_id=%s", request_id)
            return self._fail(task, f"Handler error: {exc}")

        body = {
            "llmdmz": {
                "type": "response",
                "request_id": request_id,
                "schema_id": schema_id,
                "response_payload": response_payload,
            }
        }
        if response_schema:
            body["llmdmz"]["response_schema"] = response_schema

        task.artifacts = [
            {
                "parts": [
                    {"type": "data", "data": body},
                    {"type": "text", "text": json.dumps(response_payload, indent=2)},
                ]
            }
        ]
        task.metadata = body
        task.status = TaskStatus(state=TaskState.COMPLETED)
        logger.info("Requestee completed request_id=%s records=%d", request_id, len(response_payload.get("records", [])))
        return task

    def _fail(self, task: Task, reason: str) -> Task:
        task.status = TaskStatus(state=TaskState.FAILED, message={"error": reason})
        task.artifacts = [{"parts": [{"type": "error", "message": reason}]}]
        return task


def main() -> None:
    host = os.getenv("A2A_REQUESTEE_HOST", "127.0.0.1")
    port = int(os.getenv("A2A_REQUESTEE_PORT", "5001"))
    url = os.getenv("A2A_REQUESTEE_URL", f"http://{host}:{port}")

    agent = RequesteeServer(
        url=url,
        name="LLM DMZ Requestee",
        description="Trusted internal A2A agent that fulfills schema-bound DMZ requests",
        version="1.0.0",
    )
    run_server(agent, host=host, port=port)


if __name__ == "__main__":
    main()
