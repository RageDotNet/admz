"""Integration tests for llmdmz.py REST API."""

from __future__ import annotations

import pytest

from tests.conftest import CRM_REQUEST, CRM_RESPONSE, EXT_HEADERS, INT_HEADERS, REV_HEADERS


def test_health_no_auth(llmdmz_client) -> None:
    resp = llmdmz_client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_list_schemas_requires_auth(llmdmz_client) -> None:
    resp = llmdmz_client.get("/api/v1/schemas")
    assert resp.status_code == 401


def test_list_schemas_success(llmdmz_client) -> None:
    resp = llmdmz_client.get("/api/v1/schemas", headers=EXT_HEADERS)
    assert resp.status_code == 200
    assert any(s["id"] == "crm_search" for s in resp.get_json()["schemas"])


def test_submit_request_success(llmdmz_client, patch_storage) -> None:
    resp = llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-rest-1", "payload": CRM_REQUEST},
    )
    assert resp.status_code == 202
    assert resp.get_json()["request"]["request_id"] == "req-rest-1"
    assert patch_storage.get_request("req-rest-1").status == "pending_requestee"


def test_submit_request_missing_fields(llmdmz_client) -> None:
    resp = llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search"},
    )
    assert resp.status_code == 400


def test_submit_request_duplicate_id(llmdmz_client) -> None:
    payload = {"schema_id": "crm_search", "request_id": "req-dup", "payload": CRM_REQUEST}
    assert llmdmz_client.post("/api/v1/requests", headers=EXT_HEADERS, json=payload).status_code == 202
    resp = llmdmz_client.post("/api/v1/requests", headers=EXT_HEADERS, json=payload)
    assert resp.status_code == 400
    assert "already exists" in resp.get_json()["error"]


def test_submit_request_wrong_role(llmdmz_client) -> None:
    resp = llmdmz_client.post(
        "/api/v1/requests",
        headers=INT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-wrong", "payload": CRM_REQUEST},
    )
    assert resp.status_code == 401


def test_submit_request_invalid_schema_payload_goes_to_review(
    llmdmz_client,
    patch_storage,
) -> None:
    resp = llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-invalid", "payload": {}},
    )
    assert resp.status_code == 202
    record = patch_storage.get_request("req-invalid")
    assert record.status == "pending_review_request"


def test_submit_request_arbiter_reject(
    llmdmz_client,
    patch_storage,
    monkeypatch: pytest.MonkeyPatch,
    arbiter_reject_request: None,
) -> None:
    resp = llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-reject", "payload": CRM_REQUEST},
    )
    assert resp.status_code == 202
    assert patch_storage.get_request("req-reject").status == "pending_review_request"


def test_full_request_response_flow(llmdmz_client, patch_storage) -> None:
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-flow", "payload": CRM_REQUEST},
    )

    poll = llmdmz_client.get("/api/v1/requests/poll", headers=INT_HEADERS)
    assert poll.status_code == 200
    requests = poll.get_json()["requests"]
    assert len(requests) == 1
    assert requests[0]["request_id"] == "req-flow"

    submit_resp = llmdmz_client.post(
        "/api/v1/requests/req-flow/response",
        headers=INT_HEADERS,
        json={"payload": CRM_RESPONSE},
    )
    assert submit_resp.status_code == 202
    assert patch_storage.get_request("req-flow").status == "completed"

    responses = llmdmz_client.get("/api/v1/responses/poll", headers=EXT_HEADERS)
    assert responses.status_code == 200
    assert responses.get_json()["responses"][0]["response_payload"] == CRM_RESPONSE


def test_poll_requests_wrong_role(llmdmz_client) -> None:
    resp = llmdmz_client.get("/api/v1/responses/poll", headers=INT_HEADERS)
    assert resp.status_code == 401


def test_submit_response_unauthorized_requestee(llmdmz_client) -> None:
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-auth", "payload": CRM_REQUEST},
    )
    resp = llmdmz_client.post(
        "/api/v1/requests/req-auth/response",
        headers=EXT_HEADERS,
        json={"payload": CRM_RESPONSE},
    )
    assert resp.status_code == 401


def test_submit_response_before_ready(llmdmz_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llmdmz.process_request.delay", lambda request_id: None)
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-early", "payload": CRM_REQUEST},
    )
    resp = llmdmz_client.post(
        "/api/v1/requests/req-early/response",
        headers=INT_HEADERS,
        json={"payload": CRM_RESPONSE},
    )
    assert resp.status_code == 400
    assert "not ready" in resp.get_json()["error"]


def test_get_request_status(llmdmz_client) -> None:
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-status", "payload": CRM_REQUEST},
    )
    resp = llmdmz_client.get("/api/v1/requests/req-status", headers=EXT_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["request"]["request_id"] == "req-status"


def test_review_approve_request(llmdmz_client, patch_storage, arbiter_reject_request: None) -> None:
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-review", "payload": CRM_REQUEST},
    )
    reviews = llmdmz_client.get("/api/v1/review/pending", headers=REV_HEADERS).get_json()["reviews"]
    review_id = reviews[0]["id"]

    resp = llmdmz_client.post(f"/api/v1/review/{review_id}/approve", headers=REV_HEADERS, json={})
    assert resp.status_code == 200
    assert patch_storage.get_request("req-review").status == "pending_requestee"


def test_review_reject_request(llmdmz_client, patch_storage, arbiter_reject_request: None) -> None:
    llmdmz_client.post(
        "/api/v1/requests",
        headers=EXT_HEADERS,
        json={"schema_id": "crm_search", "request_id": "req-reject-review", "payload": CRM_REQUEST},
    )
    review_id = llmdmz_client.get("/api/v1/review/pending", headers=REV_HEADERS).get_json()["reviews"][0]["id"]
    llmdmz_client.post(f"/api/v1/review/{review_id}/reject", headers=REV_HEADERS, json={"notes": "no"})
    assert patch_storage.get_request("req-reject-review").status == "rejected"


def test_review_requires_reviewer_role(llmdmz_client) -> None:
    resp = llmdmz_client.get("/api/v1/review/pending", headers=EXT_HEADERS)
    assert resp.status_code == 401
