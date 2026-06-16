"""A2A message envelope helpers for the LLM DMZ gateway."""

from __future__ import annotations

import json
from typing import Any

from python_a2a import Task, TaskState, TaskStatus


def _json_from_text(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_llmdmz_envelope(task: Task) -> dict[str, Any] | None:
    """Extract a DMZ request envelope from task metadata or message content."""
    metadata = task.metadata or {}
    if isinstance(metadata, dict) and "llmdmz" in metadata:
        envelope = metadata["llmdmz"]
        return envelope if isinstance(envelope, dict) else None

    message = task.message or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, dict):
            if content.get("type") == "text":
                parsed = _json_from_text(str(content.get("text", "")))
                if parsed and "llmdmz" in parsed:
                    return parsed["llmdmz"]
                if parsed and parsed.get("schema_id") and parsed.get("payload") is not None:
                    return parsed
            if content.get("type") == "data" and isinstance(content.get("data"), dict):
                data = content["data"]
                if "llmdmz" in data:
                    return data["llmdmz"]
                if data.get("schema_id") and data.get("payload") is not None:
                    return data

        if "parts" in message and isinstance(message["parts"], list):
            for part in message["parts"]:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    parsed = _json_from_text(str(part.get("text", "")))
                    if parsed:
                        if "llmdmz" in parsed:
                            return parsed["llmdmz"]
                        if parsed.get("schema_id") and parsed.get("payload") is not None:
                            return parsed
                if part.get("type") == "data" and isinstance(part.get("data"), dict):
                    data = part["data"]
                    if "llmdmz" in data:
                        return data["llmdmz"]
                    if data.get("schema_id") and data.get("payload") is not None:
                        return data

    return None


def extract_response_payload(task: Task) -> dict[str, Any] | None:
    """Extract a DMZ response payload from a requestee task."""
    metadata = task.metadata or {}
    if isinstance(metadata, dict):
        llmdmz = metadata.get("llmdmz")
        if isinstance(llmdmz, dict) and llmdmz.get("response_payload") is not None:
            return llmdmz["response_payload"]

    for artifact in task.artifacts or []:
        for part in artifact.get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "data" and isinstance(part.get("data"), dict):
                data = part["data"]
                llmdmz = data.get("llmdmz")
                if isinstance(llmdmz, dict) and llmdmz.get("response_payload") is not None:
                    return llmdmz["response_payload"]
                if data.get("response_payload") is not None:
                    return data["response_payload"]
            if part.get("type") == "text":
                parsed = _json_from_text(str(part.get("text", "")))
                if parsed:
                    if parsed.get("response_payload") is not None:
                        return parsed["response_payload"]
                    if parsed.get("records") is not None:
                        return parsed

    text = task.get_text()
    if text:
        parsed = _json_from_text(text)
        if parsed:
            if parsed.get("response_payload") is not None:
                return parsed["response_payload"]
            if parsed.get("records") is not None:
                return parsed
    return None


def build_requestor_response_task(
    *,
    task: Task,
    request_id: str,
    schema_id: str,
    response_payload: dict[str, Any],
    notes: str | None = None,
) -> Task:
    body = {
        "llmdmz": {
            "type": "response",
            "request_id": request_id,
            "schema_id": schema_id,
            "response_payload": response_payload,
        }
    }
    if notes:
        body["llmdmz"]["notes"] = notes

    task.artifacts = [
        {
            "parts": [
                {"type": "data", "data": body},
                {"type": "text", "text": json.dumps(response_payload, indent=2)},
            ]
        }
    ]
    task.status = TaskStatus(state=TaskState.COMPLETED)
    task.metadata = {**(task.metadata or {}), "llmdmz": body["llmdmz"]}
    return task


def build_requestee_task(
    *,
    request_id: str,
    schema_id: str,
    request_payload: dict[str, Any],
    response_schema: dict[str, Any],
    description: str,
) -> Task:
    envelope = {
        "llmdmz": {
            "type": "request",
            "request_id": request_id,
            "schema_id": schema_id,
            "request_payload": request_payload,
            "response_schema": response_schema,
            "instructions": (
                f"Fulfill this {schema_id} request. "
                f"Return a response_payload object that validates against the provided response_schema. "
                f"{description}"
            ),
        }
    }
    return Task(
        id=request_id,
        message={
            "role": "user",
            "parts": [
                {
                    "type": "text",
                    "text": envelope["llmdmz"]["instructions"],
                },
                {"type": "data", "data": envelope},
            ],
        },
        metadata=envelope,
    )


def build_waiting_task(task: Task, *, request_id: str, reason: str, review_id: str | None = None) -> Task:
    task.status = TaskStatus(
        state=TaskState.INPUT_REQUIRED,
        message={"llmdmz": {"request_id": request_id, "reason": reason, "review_id": review_id}},
    )
    task.artifacts = [
        {
            "parts": [
                {
                    "type": "text",
                    "text": (
                        f"Request {request_id} requires human review before it can proceed.\n"
                        f"Reason: {reason}"
                        + (f"\nReview ID: {review_id}" if review_id else "")
                    ),
                }
            ]
        }
    ]
    task.metadata = {
        **(task.metadata or {}),
        "llmdmz_status": "pending_review",
        "llmdmz_request_id": request_id,
        "llmdmz_review_id": review_id,
    }
    return task


def build_failed_task(task: Task, *, request_id: str, reason: str) -> Task:
    task.status = TaskStatus(
        state=TaskState.FAILED,
        message={"llmdmz": {"request_id": request_id, "reason": reason}},
    )
    task.artifacts = [{"parts": [{"type": "error", "message": reason}]}]
    task.metadata = {
        **(task.metadata or {}),
        "llmdmz_status": "failed",
        "llmdmz_request_id": request_id,
    }
    return task
