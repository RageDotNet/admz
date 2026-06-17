"""Tests for dmz.arbiter with mocked LiteLLM."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dmz.arbiter import check_request, check_response, _parse_verdict
from tests.conftest import CRM_REQUEST, CRM_RESPONSE


def test_parse_verdict_raw_json() -> None:
    assert _parse_verdict('{"approved": true, "reason": "ok"}') == {"approved": True, "reason": "ok"}


def test_parse_verdict_embedded_json() -> None:
    text = 'Here is my verdict: {"approved": false, "reason": "bad"}'
    assert _parse_verdict(text)["approved"] is False


def test_parse_verdict_invalid_raises() -> None:
    with pytest.raises(ValueError, match="non-JSON"):
        _parse_verdict("not json at all")


def test_check_request_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"approved": true, "reason": "clean"}'))]
    monkeypatch.setattr("dmz.arbiter.completion", lambda **kwargs: mock_response)
    monkeypatch.setattr("dmz.arbiter._require_api_key", lambda: "test-key")

    verdict = check_request("crm_search", CRM_REQUEST)
    assert verdict["approved"] is True


def test_check_request_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"approved": false, "reason": "attack"}'))]
    monkeypatch.setattr("dmz.arbiter.completion", lambda **kwargs: mock_response)
    monkeypatch.setattr("dmz.arbiter._require_api_key", lambda: "test-key")

    verdict = check_request("crm_search", CRM_REQUEST)
    assert verdict["approved"] is False


def test_check_response_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"approved": true, "reason": "scoped"}'))]
    monkeypatch.setattr("dmz.arbiter.completion", lambda **kwargs: mock_response)
    monkeypatch.setattr("dmz.arbiter._require_api_key", lambda: "test-key")

    verdict = check_response("crm_search", CRM_REQUEST, CRM_RESPONSE)
    assert verdict["approved"] is True


def test_check_request_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("dmz.arbiter.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        check_request("crm_search", CRM_REQUEST)
