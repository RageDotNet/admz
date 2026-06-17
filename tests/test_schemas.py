"""Tests for dmz.schemas."""

from __future__ import annotations

import pytest

from dmz.schemas import SchemaRegistry
from tests.conftest import CRM_CONTACT, CRM_REQUEST, CRM_RESPONSE


@pytest.fixture
def registry() -> SchemaRegistry:
    return SchemaRegistry()


def test_list_schemas(registry: SchemaRegistry) -> None:
    schemas = registry.list_schemas()
    assert any(item["id"] == "crm_search" for item in schemas)


def test_validate_request_valid(registry: SchemaRegistry) -> None:
    registry.validate_request("crm_search", CRM_REQUEST)
    registry.validate_request("crm_search", {"name": "Jane Smith"})


def test_validate_request_invalid(registry: SchemaRegistry) -> None:
    with pytest.raises(Exception):
        registry.validate_request("crm_search", {})


def test_validate_request_unknown_schema(registry: SchemaRegistry) -> None:
    with pytest.raises(KeyError, match="Unknown schema_id"):
        registry.validate_request("missing", CRM_REQUEST)


def test_validate_response_valid(registry: SchemaRegistry) -> None:
    registry.validate_response("crm_search", CRM_RESPONSE)
    registry.validate_response("crm_search", {"records": []})


def test_validate_response_invalid_record(registry: SchemaRegistry) -> None:
    with pytest.raises(Exception):
        registry.validate_response("crm_search", {"records": [{"id": "x"}]})


def test_validate_response_invalid_status(registry: SchemaRegistry) -> None:
    bad = {"records": [{**CRM_CONTACT, "status": "invalid"}]}
    with pytest.raises(Exception):
        registry.validate_response("crm_search", bad)
