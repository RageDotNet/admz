"""T3.5: invariant clauses of the base arbiter prompts (#3 acceptance criteria)."""

from __future__ import annotations

import json

from admz.dispatch.arbiter_prompts import REQUEST_BASE_PROMPT, RESPONSE_BASE_PROMPT

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


def test_response_prompt_has_benign_content_guidance():
    """The response arbiter must not reject ordinary free-text record fields."""
    p = RESPONSE_BASE_PROMPT
    assert "Judgment guidance" in p
    assert "NOT attacks" in p
    assert "imperatively addressed to a model" in p
    assert "AUTHORITATIVE CONTRACT" in REQUEST_BASE_PROMPT
    assert "AUTHORITATIVE CONTRACT" in p
    assert "field descriptions" in p


def test_risk_focus_sections_rule_out_false_positive_classes():
    """Each focus section must name the observed false-positive grounds."""
    from admz.dispatch.arbiter_prompts import (
        EXFILTRATION_RISK_FOCUS,
        INJECTION_RISK_FOCUS,
    )

    for clause in (
        "PROMPT INJECTION",
        "repetit",  # duplicated/repetitive text
        "could be",  # "could be interpreted" hedging
        "greetings",
    ):
        assert clause in INJECTION_RISK_FOCUS
    for clause in (
        "DATA EXFILTRATION",
        "repetit",  # appended notes repeat text
        "redundancy",
        "bulk dumps",
    ):
        assert clause in EXFILTRATION_RISK_FOCUS


def test_resolve_risk_focus_unknown_is_empty_and_defaults_resolve():
    from admz.dispatch.arbiter_prompts import resolve_prompts, resolve_risk_focus

    assert resolve_risk_focus("") == ""
    assert resolve_risk_focus("nonsense") == ""
    req, resp = resolve_prompts()
    assert "ONLY valid JSON" in req and "ONLY valid JSON" in resp


def test_config_overrides_replace_prompts(monkeypatch):
    from admz.dispatch import arbiter_prompts as ap

    monkeypatch.setattr(
        ap, "_config_overrides",
        lambda: {
            "arbiter_request_prompt": "CUSTOM REQUEST",
            "arbiter_response_prompt": "",
            "arbiter_injection_focus": "CUSTOM INJECTION",
            "arbiter_exfiltration_focus": "",
        },
    )
    req, resp = ap.resolve_prompts()
    assert req == "CUSTOM REQUEST"
    assert resp == ap.RESPONSE_BASE_PROMPT  # empty override falls back
    assert ap.resolve_risk_focus("injection") == "CUSTOM INJECTION"
    assert ap.resolve_risk_focus("exfiltration") == ap.EXFILTRATION_RISK_FOCUS


def test_arbiter_context_prepends_risk_focus():
    from admz.core.models import Action
    from admz.dispatch.pipeline import _arbiter_context

    action = Action(id="crm_add_note", owner_agent_id="a" * 36)
    ctx = _arbiter_context(
        action=action,
        action_description="Append a note.",
        provider_instructions="",
        request_schema={"type": "object"},
        risk="exfiltration",
    )
    assert "RISK FOCUS" in ctx
    assert "DATA EXFILTRATION" in ctx
    assert ctx.index("RISK FOCUS") < ctx.index("AUTHORITATIVE ACTION CONTRACT")
    plain = _arbiter_context(
        action=action,
        action_description="Append a note.",
        provider_instructions="",
        request_schema={"type": "object"},
    )
    assert "RISK FOCUS" not in plain


