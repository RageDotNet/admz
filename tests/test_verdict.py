"""T3.3: verdict parser unit tests."""

from __future__ import annotations

from llmdmz.dispatch.verdict import parse_verdict


def test_clean_json():
    v = parse_verdict('{"approved": true, "reason": "Payload matches declared schema."}')
    assert v.approved is True
    assert v.reason == "Payload matches declared schema."


def test_rejection():
    v = parse_verdict('{"approved": false, "reason": "Instructions detected in data field."}')
    assert v.approved is False


def test_missing_reason_defaults():
    v = parse_verdict('{"approved": true}')
    assert v.reason == "No reason provided"


def test_bool_coercion():
    assert parse_verdict('{"approved": "true"}').approved is True
    assert parse_verdict('{"approved": "False"}').approved is False
    assert parse_verdict('{"approved": 1}').approved is True
    assert parse_verdict('{"approved": 0}').approved is False


def test_fenced_json():
    v = parse_verdict('```json\n{"approved": true, "reason": "ok"}\n```')
    assert v.approved is True


def test_prose_wrapped_json():
    v = parse_verdict(
        'After review I conclude: {"approved": false, "reason": "exfiltration risk"} '
        "as my final answer."
    )
    assert v.approved is False
    assert v.reason == "exfiltration risk"


def test_first_brace_block_wins():
    v = parse_verdict('noise {"approved": true, "reason": "first"} more {"approved": false}')
    assert v.approved is True and v.reason == "first"


def test_garbage_is_failed_check():
    for garbage in ("", "no json here at all", "{broken", '{"message": "hi"}', "[1,2,3]", "42"):
        v = parse_verdict(garbage)
        assert v.approved is False
        assert "not parseable" in v.reason


def test_non_string_input():
    assert parse_verdict(None).approved is False  # type: ignore[arg-type]
