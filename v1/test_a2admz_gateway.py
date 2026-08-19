"""Integration tests for a2admz.py A2A gateway."""

from __future__ import annotations

import json

import pytest
from python_a2a import Task, TaskState

from tests.conftest import (
    CRM_ADD_NOTE_REQUEST,
    CRM_ADD_NOTE_RESPONSE,
    CRM_REQUEST,
    CRM_RESPONSE,
    EXT_HEADERS,
    REV_HEADERS,
    make_a2a_task,
    mock_requestee_task,
)


def _handle(gateway, task: Task, headers: dict | None = None) -> Task:
    if headers is None:
        headers = EXT_HEADERS
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context(headers=headers):
        return gateway.handle_task(task)


def test_a2a_successful_flow(a2a_gateway, mock_a2a_client, patch_storage) -> None:
    task = make_a2a_task(request_id="a2a-ok")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.COMPLETED
    assert result.metadata["llmdmz"]["response_payload"]["records"][0]["name"] == "Jane Smith"
    assert patch_storage.get_request("a2a-ok").status == "completed"


def test_a2a_crm_add_note_flow(a2a_gateway, mock_a2a_client, patch_storage) -> None:
    mock_a2a_client(CRM_ADD_NOTE_RESPONSE)
    task = make_a2a_task(
        request_id="a2a-add-note",
        schema_id="crm_add_note",
        payload=CRM_ADD_NOTE_REQUEST,
    )
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.COMPLETED
    record = result.metadata["llmdmz"]["response_payload"]["record"]
    assert record["id"] == "c001"
    assert CRM_ADD_NOTE_REQUEST["note"] in record["notes"]
    assert patch_storage.get_request("a2a-add-note").status == "completed"


def test_a2a_missing_envelope(a2a_gateway) -> None:
    task = Task(id="bad")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.FAILED
    assert "Missing llmdmz envelope" in str(result.status.message)


def test_a2a_missing_auth(a2a_gateway) -> None:
    task = make_a2a_task(request_id="a2a-noauth")
    result = _handle(a2a_gateway, task, headers={"X-Agent-Id": "", "X-Agent-Key": ""})
    assert result.status.state == TaskState.FAILED
    assert "Missing agent credentials" in str(result.status.message)


def test_a2a_wrong_role(a2a_gateway) -> None:
    task = make_a2a_task(request_id="a2a-role")
    from dmz.agents import AgentRegistry

    int_headers = {"X-Agent-Id": "int_agent", "X-Agent-Key": "int-dev-key-change-me"}
    app = __import__("flask").Flask(__name__)
    with app.test_request_context(headers=int_headers):
        result = a2a_gateway.handle_task(task)
    assert result.status.state == TaskState.FAILED
    assert "Only requestor agents" in str(result.status.message)


def test_a2a_invalid_schema_payload_goes_to_review(a2a_gateway, patch_storage) -> None:
    task = make_a2a_task(request_id="a2a-invalid", payload={})
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.INPUT_REQUIRED
    assert patch_storage.get_request("a2a-invalid").status == "pending_review_request"


def test_a2a_arbiter_rejects_request(a2a_gateway, patch_storage, arbiter_reject_request: None) -> None:
    task = make_a2a_task(request_id="a2a-reject-req")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.INPUT_REQUIRED
    assert patch_storage.get_request("a2a-reject-req").status == "pending_review_request"


def test_a2a_arbiter_rejects_response(
    a2a_gateway,
    patch_storage,
    mock_a2a_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _approve_request(schema_id, payload):
        return {"approved": True, "reason": "ok"}

    monkeypatch.setattr("a2admz.check_request", _approve_request)
    monkeypatch.setattr(
        "a2admz.check_response",
        lambda *args, **kwargs: {"approved": False, "reason": "exfiltration"},
    )

    task = make_a2a_task(request_id="a2a-reject-resp")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.INPUT_REQUIRED
    assert patch_storage.get_request("a2a-reject-resp").status == "pending_review_response"


def test_a2a_requestee_failure_goes_to_review(a2a_gateway, patch_storage, monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        def _send_task(self, task):
            raise RuntimeError("requestee down")

    monkeypatch.setattr("a2admz.A2AClient", BrokenClient)

    task = make_a2a_task(request_id="a2a-reqee-fail")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.INPUT_REQUIRED


def test_a2a_continue_after_review_approval(a2a_gateway, patch_storage, mock_a2a_client) -> None:
    task = make_a2a_task(request_id="a2a-resume")
    patch_storage.create_request(
        request_id="a2a-resume",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    patch_storage.update_request("a2a-resume", status="pending_requestee")

    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.COMPLETED


def test_a2a_returns_cached_completed(a2a_gateway, patch_storage) -> None:
    patch_storage.create_request(
        request_id="a2a-cached",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    patch_storage.update_request("a2a-cached", status="completed", response_payload=CRM_RESPONSE)

    task = make_a2a_task(request_id="a2a-cached")
    result = _handle(a2a_gateway, task)
    assert result.status.state == TaskState.COMPLETED
    assert result.metadata["llmdmz"]["response_payload"] == CRM_RESPONSE


def test_a2a_http_tasks_send(a2a_flask_app, mock_a2a_client, patch_storage) -> None:
    task = make_a2a_task(request_id="a2a-http")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": task.to_dict(),
    }
    client = a2a_flask_app.test_client()
    resp = client.post("/a2a/tasks/send", headers=EXT_HEADERS, json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["status"]["state"] == "completed"


def test_a2a_review_api(a2a_flask_app, patch_storage, arbiter_reject_request: None) -> None:
    gateway_app_client = a2a_flask_app.test_client()
    task = make_a2a_task(request_id="a2a-review-api")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": task.to_dict()}
    gateway_app_client.post("/a2a/tasks/send", headers=EXT_HEADERS, json=payload)

    reviews = gateway_app_client.get("/api/v1/review/pending", headers=REV_HEADERS).get_json()["reviews"]
    review_id = reviews[0]["id"]
    resp = gateway_app_client.post(f"/api/v1/review/{review_id}/approve", headers=REV_HEADERS, json={})
    assert resp.status_code == 200
    assert patch_storage.get_request("a2a-review-api").status == "pending_requestee"
