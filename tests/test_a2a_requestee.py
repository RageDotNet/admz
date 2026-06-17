"""Tests for a2a_requestee.py schema handlers."""

from __future__ import annotations

from pathlib import Path

import pytest
from python_a2a import Task, TaskState

from a2a_requestee import RequesteeServer, fulfill_crm_add_note
from crmtool import CRM
from tests.conftest import CRM_ADD_NOTE_REQUEST


def test_fulfill_crm_add_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    crm_path = tmp_path / "crm.json"
    monkeypatch.setattr("crmtool.CRM_DATA_PATH", crm_path)
    monkeypatch.setattr("a2a_requestee.add_contact_note", CRM(crm_path).add_note)

    result = fulfill_crm_add_note(CRM_ADD_NOTE_REQUEST)
    assert result["record"]["id"] == "c001"
    assert CRM_ADD_NOTE_REQUEST["note"] in result["record"]["notes"]


def test_requestee_handles_crm_add_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    crm_path = tmp_path / "crm.json"
    monkeypatch.setattr("crmtool.CRM_DATA_PATH", crm_path)
    monkeypatch.setattr("a2a_requestee.add_contact_note", CRM(crm_path).add_note)

    envelope = {
        "llmdmz": {
            "type": "request",
            "schema_id": "crm_add_note",
            "request_id": "req-note-1",
            "request_payload": CRM_ADD_NOTE_REQUEST,
        }
    }
    task = Task(id="req-note-1", metadata=envelope)
    result = RequesteeServer(url="http://test").handle_task(task)

    assert result.status.state == TaskState.COMPLETED
    payload = result.metadata["llmdmz"]["response_payload"]
    assert payload["record"]["id"] == "c001"
    assert CRM_ADD_NOTE_REQUEST["note"] in payload["record"]["notes"]
