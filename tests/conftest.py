"""Shared pytest fixtures and helpers."""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import MagicMock

import pytest
from python_a2a import Task, TaskState, TaskStatus
from python_a2a.server.http import create_flask_app

from a2admz import A2ADmzGateway
from dmz.storage import Storage
from dmz.tasks import process_request, process_response


CRM_CONTACT = {
    "id": "c001",
    "name": "Jane Smith",
    "email": "jane.smith@acmecorp.com",
    "company": "Acme Corp",
    "phone": "+1-555-0101",
    "status": "active",
    "notes": "Enterprise renewal due Q3.",
}

CRM_REQUEST = {"company": "Acme Corp"}
CRM_RESPONSE = {"records": [CRM_CONTACT]}

CRM_ADD_NOTE_REQUEST = {"contact_id": "c001", "note": "Follow-up call scheduled for next week."}
CRM_ADD_NOTE_RESPONSE = {
    "record": {
        **CRM_CONTACT,
        "notes": f"{CRM_CONTACT['notes']}\n{CRM_ADD_NOTE_REQUEST['note']}",
    }
}

EXT_HEADERS = {"X-Agent-Id": "ext_agent", "X-Agent-Key": "ext-dev-key-change-me"}
INT_HEADERS = {"X-Agent-Id": "int_agent", "X-Agent-Key": "int-dev-key-change-me"}
REV_HEADERS = {"X-Agent-Id": "reviewer1", "X-Agent-Key": "review-dev-key-change-me"}


@pytest.fixture
def test_storage(tmp_path: pytest.TempPathFactory) -> Storage:
    return Storage(tmp_path / "test.db")


@pytest.fixture
def patch_storage(test_storage: Storage, monkeypatch: pytest.MonkeyPatch) -> Storage:
    """Use isolated SQLite DB across llmdmz, tasks, and a2admz."""
    monkeypatch.setattr("llmdmz.storage", test_storage)
    monkeypatch.setattr("dmz.tasks.Storage", lambda *args, **kwargs: test_storage)
    return test_storage


@pytest.fixture
def arbiter_approve(monkeypatch: pytest.MonkeyPatch) -> None:
    def _approve_request(schema_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"approved": True, "reason": "test-approved-request"}

    def _approve_response(
        schema_id: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
        operation_description: str | None = None,
    ) -> dict[str, Any]:
        return {"approved": True, "reason": "test-approved-response"}

    for target in (
        "dmz.arbiter.check_request",
        "dmz.arbiter.check_response",
        "dmz.tasks.check_request",
        "dmz.tasks.check_response",
        "a2admz.check_request",
        "a2admz.check_response",
    ):
        monkeypatch.setattr(
            target,
            _approve_request if target.endswith("check_request") else _approve_response,
        )


@pytest.fixture
def arbiter_reject_request(monkeypatch: pytest.MonkeyPatch) -> None:
    reject = lambda schema_id, payload: {"approved": False, "reason": "malicious"}
    for target in ("dmz.arbiter.check_request", "dmz.tasks.check_request", "a2admz.check_request"):
        monkeypatch.setattr(target, reject)


@pytest.fixture
def arbiter_reject_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def _approve_request(schema_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"approved": True, "reason": "ok"}

    reject_response = lambda *args, **kwargs: {"approved": False, "reason": "exfiltration"}
    for target in ("dmz.arbiter.check_request", "dmz.tasks.check_request", "a2admz.check_request"):
        monkeypatch.setattr(target, _approve_request)
    for target in ("dmz.arbiter.check_response", "dmz.tasks.check_response", "a2admz.check_response"):
        monkeypatch.setattr(target, reject_response)


@pytest.fixture
def sync_celery_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llmdmz.process_request.delay", lambda request_id: process_request(request_id))
    monkeypatch.setattr(
        "llmdmz.process_response.delay",
        lambda request_id, payload: process_response(request_id, payload),
    )


@pytest.fixture
def llmdmz_client(patch_storage: Storage, sync_celery_tasks: None, arbiter_approve: None):
    import llmdmz

    return llmdmz.app.test_client()


@pytest.fixture
def a2a_gateway(patch_storage: Storage, arbiter_approve: None) -> A2ADmzGateway:
    gateway = A2ADmzGateway(url="http://testserver")
    gateway.storage = patch_storage
    return gateway


@pytest.fixture
def a2a_flask_app(a2a_gateway: A2ADmzGateway):
    from pathlib import Path

    from dmz.admin_routes import register_admin_routes
    from dmz.review_routes import register_review_routes

    app = create_flask_app(a2a_gateway)
    app.template_folder = str(Path(__file__).resolve().parent.parent / "templates")
    register_review_routes(app, agent_registry=a2a_gateway.agent_registry, storage=a2a_gateway.storage)
    register_admin_routes(
        app,
        agent_registry=a2a_gateway.agent_registry,
        schema_registry=a2a_gateway.schema_registry,
        storage=a2a_gateway.storage,
    )
    return app


def make_a2a_task(
    *,
    request_id: str = "req-test-001",
    schema_id: str = "crm_search",
    payload: dict[str, Any] | None = None,
) -> Task:
    payload = payload if payload is not None else CRM_REQUEST
    envelope = {"llmdmz": {"schema_id": schema_id, "request_id": request_id, "payload": payload}}
    return Task(
        id=request_id,
        metadata=envelope,
        message={"role": "user", "parts": [{"type": "data", "data": envelope}]},
    )


def mock_requestee_task(response_payload: dict[str, Any] | None = None) -> Task:
    payload = response_payload if response_payload is not None else CRM_RESPONSE
    task = Task(id="req-test-001")
    task.status = TaskStatus(state=TaskState.COMPLETED)
    task.metadata = {"llmdmz": {"response_payload": payload}}
    task.artifacts = [{"parts": [{"type": "data", "data": {"llmdmz": {"response_payload": payload}}}]}]
    return task


@pytest.fixture
def mock_a2a_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, Any] | None], None]:
    def _configure(response_payload: dict[str, Any] | None = None) -> None:
        result_task = mock_requestee_task(response_payload)

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def _send_task(self, task):
                return result_task

        monkeypatch.setattr("a2admz.A2AClient", FakeClient)

    _configure()
    return _configure
