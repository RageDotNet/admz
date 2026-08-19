"""T4.12: structural JSON diff unit tests (#24)."""

from __future__ import annotations

from llmdmz.core.jsondiff import canonical, diff, diff_payloads

SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "company": {"type": "string"},
    },
    "required": ["name"],
    "additionalProperties": False,
}
SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 2},  # changed (nested)
        "email": {"type": "string", "format": "email"},  # added
        # "company" removed
    },
    "required": ["name", "email"],  # list changed
    "additionalProperties": False,
}


def test_canonical_is_key_order_insensitive():
    assert canonical({"a": 1, "b": 2}) == canonical({"b": 2, "a": 1})
    assert canonical({"a": {"x": 1, "y": 2}}) == canonical({"a": {"y": 2, "x": 1}})
    assert canonical([1, 2]) != canonical([2, 1])  # arrays are ordered


def test_equal_trees_no_diff():
    assert diff(SCHEMA_V1, dict(SCHEMA_V1)) == []


def test_nested_change():
    entries = diff(SCHEMA_V1, SCHEMA_V2)
    by_op = {}
    for e in entries:
        by_op.setdefault(e["op"], []).append(e)
    changed = {e["path"] for e in by_op["changed"]}
    assert "properties.name.minLength" in changed
    assert changed == {"properties.name.minLength", "required"}  # list vs list len change
    added = {e["path"] for e in by_op["added"]}
    assert "properties.email" in added
    removed = {e["path"] for e in by_op["removed"]}
    assert "properties.company" in removed


def test_type_change_is_changed():
    entries = diff({"a": 1}, {"a": "one"})
    assert entries == [{"op": "changed", "path": "a", "old": 1, "new": "one"}]


def test_payload_diff_per_field():
    old = {"description": "v1", "request_schema": SCHEMA_V1, "client_instructions": "x"}
    new = {"description": "v2", "request_schema": SCHEMA_V2, "client_instructions": "x"}
    result = diff_payloads(old, new)
    assert set(result) == {"description", "request_schema"}
    assert result["description"][0]["new"] == "v2"
    assert any(e["path"] == "request_schema.properties.email" for e in result["request_schema"])
