"""Tests for Celery validation tasks (run synchronously in tests)."""

from __future__ import annotations

import pytest

from dmz.storage import Storage
from dmz.tasks import process_request, process_response
from tests.conftest import CRM_REQUEST, CRM_RESPONSE


@pytest.fixture
def seeded_storage(test_storage: Storage) -> Storage:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    return test_storage


def test_process_request_approved(
    monkeypatch: pytest.MonkeyPatch,
    seeded_storage: Storage,
    arbiter_approve: None,
) -> None:
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: seeded_storage)
    result = process_request("req-1")
    assert result["status"] == "pending_requestee"
    assert seeded_storage.get_request("req-1").status == "pending_requestee"


def test_process_request_schema_invalid(
    monkeypatch: pytest.MonkeyPatch,
    test_storage: Storage,
    arbiter_approve: None,
) -> None:
    test_storage.create_request(
        request_id="req-bad",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload={},
    )
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: test_storage)
    result = process_request("req-bad")
    assert result["status"] == "pending_review_request"
    assert test_storage.get_request("req-bad").status == "pending_review_request"
    assert len(test_storage.list_pending_reviews()) == 1


def test_process_request_arbiter_rejects(
    monkeypatch: pytest.MonkeyPatch,
    seeded_storage: Storage,
    arbiter_reject_request: None,
) -> None:
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: seeded_storage)
    result = process_request("req-1")
    assert result["status"] == "pending_review_request"


def test_process_response_approved(
    monkeypatch: pytest.MonkeyPatch,
    seeded_storage: Storage,
    arbiter_approve: None,
) -> None:
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: seeded_storage)
    process_request("req-1")
    result = process_response("req-1", CRM_RESPONSE)
    assert result["status"] == "completed"
    record = seeded_storage.get_request("req-1")
    assert record.status == "completed"
    assert record.response_payload == CRM_RESPONSE


def test_process_response_schema_invalid(
    monkeypatch: pytest.MonkeyPatch,
    seeded_storage: Storage,
    arbiter_approve: None,
) -> None:
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: seeded_storage)
    process_request("req-1")
    result = process_response("req-1", {"records": [{"id": "only"}]})
    assert result["status"] == "pending_review_response"


def test_process_response_arbiter_rejects(
    monkeypatch: pytest.MonkeyPatch,
    seeded_storage: Storage,
    arbiter_reject_response: None,
) -> None:
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: seeded_storage)
    process_request("req-1")
    result = process_response("req-1", CRM_RESPONSE)
    assert result["status"] == "pending_review_response"
