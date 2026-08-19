"""Tests for dmz.a2a_protocol helpers."""

from __future__ import annotations

from python_a2a import Task, TaskState

from dmz.a2a_protocol import (
    build_failed_task,
    build_requestor_response_task,
    build_waiting_task,
    extract_llmdmz_envelope,
    extract_response_payload,
)
from tests.conftest import CRM_REQUEST, CRM_RESPONSE, make_a2a_task


def test_extract_envelope_from_metadata() -> None:
    task = make_a2a_task()
    envelope = extract_llmdmz_envelope(task)
    assert envelope is not None
    assert envelope["schema_id"] == "crm_search"
    assert envelope["payload"] == CRM_REQUEST


def test_extract_envelope_missing() -> None:
    task = Task(id="empty")
    assert extract_llmdmz_envelope(task) is None


def test_extract_response_payload_from_metadata() -> None:
    task = Task(id="r1")
    task.metadata = {"llmdmz": {"response_payload": CRM_RESPONSE}}
    assert extract_response_payload(task) == CRM_RESPONSE


def test_extract_response_payload_from_artifact_text() -> None:
    task = Task(id="r1")
    task.artifacts = [{"parts": [{"type": "text", "text": '{"records": []}'}]}]
    assert extract_response_payload(task) == {"records": []}


def test_build_requestor_response_task() -> None:
    task = Task(id="r1")
    result = build_requestor_response_task(
        task=task,
        request_id="r1",
        schema_id="crm_search",
        response_payload=CRM_RESPONSE,
    )
    assert result.status.state == TaskState.COMPLETED
    assert result.metadata["llmdmz"]["response_payload"] == CRM_RESPONSE


def test_build_waiting_task() -> None:
    task = Task(id="r1")
    result = build_waiting_task(task, request_id="r1", reason="review needed", review_id="rev-1")
    assert result.status.state == TaskState.INPUT_REQUIRED
    assert result.metadata["llmdmz_review_id"] == "rev-1"


def test_build_failed_task() -> None:
    task = Task(id="r1")
    result = build_failed_task(task, request_id="r1", reason="nope")
    assert result.status.state == TaskState.FAILED
