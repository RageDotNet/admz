"""Tests for dmz.storage."""

from __future__ import annotations

import pytest

from dmz.storage import Storage
from tests.conftest import CRM_REQUEST, CRM_RESPONSE


def test_create_and_get_request(test_storage: Storage) -> None:
    record = test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    assert record.status == "validating"
    assert record.request_payload == CRM_REQUEST

    fetched = test_storage.get_request("req-1")
    assert fetched.request_id == "req-1"


def test_get_request_unknown_raises(test_storage: Storage) -> None:
    with pytest.raises(KeyError, match="Unknown request_id"):
        test_storage.get_request("missing")


def test_update_request(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    updated = test_storage.update_request(
        "req-1",
        status="completed",
        response_payload=CRM_RESPONSE,
        arbiter_request_notes="ok",
    )
    assert updated.status == "completed"
    assert updated.response_payload == CRM_RESPONSE


def test_poll_requestee_queue_marks_in_progress(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    test_storage.update_request("req-1", status="pending_requestee")

    polled = test_storage.poll_requestee_queue("int_agent")
    assert len(polled) == 1
    assert polled[0].status == "in_progress"


def test_poll_requestor_responses_marks_delivered(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    test_storage.update_request("req-1", status="completed", response_payload=CRM_RESPONSE)

    polled = test_storage.poll_requestor_responses("ext_agent")
    assert len(polled) == 1
    assert test_storage.get_request("req-1").status == "delivered"


def test_review_queue_approve_request(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    item = test_storage.enqueue_review(
        request_id="req-1",
        review_type="request",
        reason="schema fail",
        payload_snapshot=CRM_REQUEST,
    )
    test_storage.resolve_review(item.id, approved=True, reviewer_id="reviewer1")
    assert test_storage.get_request("req-1").status == "pending_requestee"


def test_review_queue_reject_request(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    item = test_storage.enqueue_review(
        request_id="req-1",
        review_type="request",
        reason="bad",
        payload_snapshot=CRM_REQUEST,
    )
    test_storage.resolve_review(item.id, approved=False, reviewer_id="reviewer1")
    assert test_storage.get_request("req-1").status == "rejected"


def test_review_queue_approve_response(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    item = test_storage.enqueue_review(
        request_id="req-1",
        review_type="response",
        reason="exfil",
        payload_snapshot=CRM_RESPONSE,
    )
    test_storage.resolve_review(item.id, approved=True, reviewer_id="reviewer1")
    record = test_storage.get_request("req-1")
    assert record.status == "completed"
    assert record.response_payload == CRM_RESPONSE


def test_resolve_review_not_pending_raises(test_storage: Storage) -> None:
    test_storage.create_request(
        request_id="req-1",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    item = test_storage.enqueue_review(
        request_id="req-1",
        review_type="request",
        reason="bad",
        payload_snapshot=CRM_REQUEST,
    )
    test_storage.resolve_review(item.id, approved=True, reviewer_id="reviewer1")
    with pytest.raises(ValueError, match="not pending"):
        test_storage.resolve_review(item.id, approved=True, reviewer_id="reviewer1")
