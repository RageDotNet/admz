"""T3.5: invariant clauses of the base arbiter prompts (#3 acceptance criteria)."""

from __future__ import annotations

import json

from llmdmz.dispatch.arbiter_prompts import REQUEST_BASE_PROMPT, RESPONSE_BASE_PROMPT

INVARIANTS = (
    "job",  # states the arbiter's job
    "ONLY valid JSON",  # fixed verdict shape
    "must NOT follow",  # injection refusal
    '{"approved": true|false, "reason":',  # verbatim verdict shape
)


def test_invariant_clauses_present():
    for prompt in (REQUEST_BASE_PROMPT, RESPONSE_BASE_PROMPT):
        for clause in INVARIANTS:
            assert clause in prompt, f"missing invariant clause: {clause!r}"


def test_prompts_are_substantive():
    assert len(REQUEST_BASE_PROMPT) > 500
    assert len(RESPONSE_BASE_PROMPT) > 500


def test_verdict_shape_is_documented_json():
    # The documented shape itself must be parseable once filled in.
    shape = '{"approved": true|false, "reason": "<short justification>"}'
    filled = shape.replace("true|false", "false").replace(
        "<short justification>", "injected instructions detected"
    )
    parsed = json.loads(filled)
    assert set(parsed) == {"approved", "reason"}


def test_request_vs_response_roles():
    assert "REQUEST" in REQUEST_BASE_PROMPT
    assert "RESPONSE" in RESPONSE_BASE_PROMPT
    assert "malicious" in REQUEST_BASE_PROMPT.lower()
    assert "exfiltration" in RESPONSE_BASE_PROMPT.lower()
