"""T3.15: invoke pipeline integration tests with injected fakes (#31)."""

from __future__ import annotations

import json

from sqlalchemy import select
from tests.test_registry import CRM_SEARCH

from llmdmz.core.models import DispatchAttempt, Enrollment, Request

GOOD_RESPONSE = {"contacts": [{"name": "Ada", "company": "Lovelace", "status": "ok"}]}


class ApprovingArbiter:
    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import Verdict

        return Verdict(approved=True, reason="ok")


class RejectingRequestArbiter(ApprovingArbiter):
    def __init__(self, reason="injection detected"):
        self.reason = reason

    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import Verdict

        if side == "request":
            return Verdict(approved=False, reason=self.reason)
        return Verdict(approved=True, reason="ok")


class RejectingResponseArbiter(ApprovingArbiter):
    def __init__(self, reason="exfiltration"):
        self.reason = reason
        self.request_calls = 0
        self.rejected_once = False

    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import Verdict

        if side == "request":
            self.request_calls += 1
        if side == "response" and not self.rejected_once:
            self.rejected_once = True
            return Verdict(approved=False, reason=self.reason)
        return Verdict(approved=True, reason="ok")


class TransportErrorArbiterRequest(ApprovingArbiter):
    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import ArbiterTransportError

        raise ArbiterTransportError("rate limited")


class TransportErrorArbiterResponse:
    """Request approves; response side raises transport errors."""

    def __init__(self):
        self.request_calls = 0
        self.rejected_once = False

    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import ArbiterTransportError, Verdict

        if side == "request":
            self.request_calls += 1
            return Verdict(approved=True, reason="ok")
        raise ArbiterTransportError("503 from openrouter")


class ScriptedTransport:
    """Returns queued ProviderResults in order."""

    def __init__(self, results):
        self.results = list(results)
        self.framings = []

    def deliver(self, framing):
        from llmdmz.dispatch.interfaces import ProviderResult

        self.framings.append(framing)
        r = self.results.pop(0)
        if isinstance(r, dict):
            return ProviderResult(payload=r)
        return r


def error_result(cls, detail):
    from llmdmz.dispatch.interfaces import ProviderResult

    return ProviderResult(error_class=cls, error_detail=detail)


def _hdr(key):
    return {"Authorization": f"Bearer {key}"}


def _enrolled_action(app_fixture, client_http):
    """Active crm_search + enrolled client + provider delivery config."""
    from tests.test_api_actions import _approve_v1

    app, provider_key, client_key = app_fixture
    client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
    _approve_v1(app_fixture)
    with app.app_context():
        s = app.extensions["DMZ_SESSION_FACTORY"]()
        from llmdmz.core.models import Agent

        agent = s.scalars(select(Agent).where(Agent.name == "client")).first()
        s.add(Enrollment(agent_id=agent.id, action_id="crm_search", state="enrolled"))
        prov = s.scalars(select(Agent).where(Agent.name == "provider")).first()
        prov.delivery_config = {"protocol": "post", "endpoint": "https://x", "retries": 2}
        s.commit()
        s.close()
    return client_key


def _invoke(client_http, key, payload=None, arbiter=None, transport=None):
    app = client_http.application
    if arbiter is not None:
        app.extensions["DMZ_ARBITER"] = arbiter
    else:
        app.extensions.pop("DMZ_ARBITER", None)
    if transport is not None:
        app.extensions["DMZ_TRANSPORT"] = transport
    else:
        app.extensions.pop("DMZ_TRANSPORT", None)
    return client_http.post(
        "/v2/actions/crm_search/invoke",
        json=payload if payload is not None else {"name": "Ada"},
        headers=_hdr(key),
    )


class TestInvokeHappyPath:
    def test_200_result_and_logging(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([GOOD_RESPONSE])
        resp = _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["action"] == "crm_search" and body["version"] == 1
        assert body["result"] == GOOD_RESPONSE
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            req = s.scalars(select(Request).where(Request.action_id == "crm_search")).first()
            assert req.outcome == "completed" and req.response_payload == GOOD_RESPONSE
            assert req.request_verdict == {"approved": True, "reason": "ok"}
            attempts = s.scalars(select(DispatchAttempt)).all()
            assert len(attempts) == 1 and attempts[0].error_class is None
            s.close()

    def test_framing_contains_schema_and_request(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([GOOD_RESPONSE])
        _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        text = transport.framings[0].text
        assert "REQUEST JSON FOLLOWS:" in text
        assert json.dumps({"name": "Ada"}) in text

    def test_invoke_preserves_utf8_emoji_in_framing(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([GOOD_RESPONSE])
        resp = _invoke(
            client_http,
            key,
            payload={"name": "🦞"},
            arbiter=ApprovingArbiter(),
            transport=transport,
        )
        assert resp.status_code == 200
        assert "🦞" in transport.framings[0].text
        assert "\\ud83e\\udd9e" not in transport.framings[0].text

    def test_dispatch_uses_provider_delivery_not_caller(self, app_fixture, client_http):
        """A dual-role client with no (or unrelated) delivery config must still
        dispatch via the action owner's endpoint. Regression: invoke used the
        caller's delivery_config, so a client like 'red' POSTed to ''."""
        key = _enrolled_action(app_fixture, client_http)
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            from llmdmz.core.models import Agent

            caller = s.scalars(select(Agent).where(Agent.name == "client")).first()
            caller.is_provider = True
            caller.delivery_config = {
                "protocol": "exec",
                "command": "should-not-run",
                "retries": 0,
            }
            s.commit()
            s.close()
        transport = ScriptedTransport([GOOD_RESPONSE])
        resp = _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        assert resp.status_code == 200
        framing = transport.framings[0]
        assert framing.protocol == "post"
        assert framing.endpoint == "https://x"
        assert framing.command == ""
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            attempt = s.scalars(select(DispatchAttempt)).first()
            assert attempt is not None
            assert attempt.framing["protocol"] == "post"
            assert attempt.framing["endpoint"] == "https://x"
            s.close()


class TestInvokeRejections:
    def test_in_flight_states_visible_during_dispatch(self, app_fixture, client_http):
        """The request row is committed at each pipeline step so the admin
        console's request log shows live progress (received → ... → completed)."""
        key = _enrolled_action(app_fixture, client_http)
        app, _, _ = app_fixture
        observed = {}

        class ObservingTransport(ScriptedTransport):
            def deliver(self, framing):
                with app.app_context():
                    s = app.extensions["DMZ_SESSION_FACTORY"]()
                    row = s.scalars(
                        select(Request).where(Request.action_id == "crm_search")
                    ).first()
                    observed["during_dispatch"] = row.outcome
                    s.close()
                return super().deliver(framing)

        resp = _invoke(
            client_http, key, arbiter=ApprovingArbiter(), transport=ObservingTransport([GOOD_RESPONSE])
        )
        assert resp.status_code == 200
        assert observed["during_dispatch"] == "dispatching"
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            req = s.scalars(select(Request).where(Request.action_id == "crm_search")).first()
            assert req.outcome == "completed" and req.finished_at is not None
            s.close()

    def test_request_schema_invalid(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        resp = _invoke(
            client_http, key, payload={"nope": True}, arbiter=ApprovingArbiter(),
            transport=ScriptedTransport([]),
        )
        assert resp.status_code == 422
        body = resp.get_json()["error"]
        assert body["code"] == "request_schema_invalid"
        assert body["detail"]["errors"]

    def test_arbiter_rejected_verbatim_reason(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        arbiter = RejectingRequestArbiter(reason="prompt injection in name field")
        resp = _invoke(client_http, key, arbiter=arbiter, transport=ScriptedTransport([]))
        assert resp.status_code == 422
        body = resp.get_json()["error"]
        assert body["code"] == "arbiter_rejected"
        assert body["detail"] == {"approved": False, "reason": "prompt injection in name field"}

    def test_request_arbiter_outage_503_no_dispatch(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([])
        resp = _invoke(
            client_http, key, arbiter=TransportErrorArbiterRequest(), transport=transport
        )
        assert resp.status_code == 503
        assert resp.get_json()["error"]["code"] == "arbiter_unavailable"
        assert transport.framings == []  # no dispatch happened
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            rows = s.scalars(select(Request)).all()
            # Logged as a terminal arbiter_unavailable request (in-flight logging).
            assert len(rows) == 1 and rows[0].outcome == "arbiter_unavailable"
            s.close()

    def test_not_enrolled(self, app_fixture, client_http):
        from tests.test_api_actions import _approve_v1

        app, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        resp = _invoke(
            client_http, client_key, arbiter=ApprovingArbiter(), transport=ScriptedTransport([])
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "not_enrolled"


class TestInvokeRetries:
    def test_retry_exhaustion_502(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([
            error_result("transport", "conn refused"),
            error_result("timeout", "timed out"),
            error_result("protocol", "unparseable"),
        ])
        resp = _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        assert resp.status_code == 502
        assert resp.get_json()["error"]["code"] == "provider_failed"
        # The client is NOT told why the provider output was invalid.
        detail = resp.get_json()["error"].get("detail") or {}
        assert detail.get("attempts") == 3
        assert "unparseable" in str(detail.get("final_error"))
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            attempts = s.scalars(select(DispatchAttempt)).all()
            assert len(attempts) == 3  # default retries=2 -> 3 attempts
            assert [a.error_class for a in attempts] == ["transport", "timeout", "protocol"]
            req = s.scalars(select(Request)).first()
            assert req.outcome == "provider_failed"
            s.close()

    def test_retry_injection_content(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([
            {"contacts": "not-an-array"},  # schema-invalid
            GOOD_RESPONSE,
        ])
        resp = _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        assert resp.status_code == 200
        second = transport.framings[1].text
        assert "ERRORS FROM YOUR PREVIOUS INVOCATION" in second
        assert "response schema violations" in second

    def test_response_arbiter_rejection_retries_then_succeeds(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([GOOD_RESPONSE, GOOD_RESPONSE])
        arbiter = RejectingResponseArbiter(reason="notes contain credentials")
        resp = _invoke(client_http, key, arbiter=arbiter, transport=transport)
        assert resp.status_code == 200
        assert "arbiter rejected your response: notes contain credentials" in (
            transport.framings[1].text
        )
        assert arbiter.request_calls == 1  # request check ran exactly once (#4)

    def test_response_arbiter_outage_is_retryable(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([GOOD_RESPONSE] * 3)
        resp = _invoke(
            client_http, key, arbiter=TransportErrorArbiterResponse(), transport=transport
        )
        assert resp.status_code == 502  # exhaustion, not 503
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            attempts = s.scalars(select(DispatchAttempt)).all()
            assert len(attempts) == 3
            assert attempts[0].error_class == "arbiter_transport"
            s.close()

    def test_request_verdict_immutable_across_retries(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([{"contacts": "bad"}, GOOD_RESPONSE])
        _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            req = s.scalars(select(Request)).first()
            assert req.request_verdict == {"approved": True, "reason": "ok"}
            s.close()

    def test_transport_succeeds_second_attempt(self, app_fixture, client_http):
        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport([error_result("transport", "reset"), GOOD_RESPONSE])
        resp = _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)
        assert resp.status_code == 200
