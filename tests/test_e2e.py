"""T5.1-T5.3: end-to-end scenarios with injected fakes (offline, #31)."""

from __future__ import annotations

from sqlalchemy import select

from llmdmz.core import storage
from llmdmz.core.models import Action, Agent, Enrollment, Request
from tests.test_registry import CRM_SEARCH

ADMIN_TOKEN = "dmzadm_testtoken0000000000000000000000000"
GOOD = {"contacts": [{"name": "Ada", "company": "Lovelace", "status": "ok"}]}


class ApprovingArbiter:
    def check(self, *, side, action_id, payload, extra_instructions=""):
        from llmdmz.dispatch.interfaces import Verdict

        return Verdict(approved=True, reason="ok")


class ScriptedTransport:
    def __init__(self, results):
        self.results = list(results)
        self.framings = []

    def deliver(self, framing):
        from llmdmz.dispatch.interfaces import ProviderResult

        self.framings.append(framing)
        r = self.results.pop(0)
        return ProviderResult(payload=r) if isinstance(r, dict) else r


def _hdr(key):
    return {"Authorization": f"Bearer {key}"}


def _approve_pending_version(client_http):
    """Approve the sole submitted version via the admin-token API."""
    from llmdmz.core.db import session_scope

    app = client_http.application
    with app.test_request_context():
        with session_scope(app) as s:
            from llmdmz.core.models import ActionVersion

            v = s.scalars(
                select(ActionVersion).where(ActionVersion.state == "submitted")
            ).first()
            vid = v.id
    return client_http.post(
        f"/admin/action-version/{vid}/approve", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )


def _grant_enrollment(client_http, agent_id, action_id):
    """Grant the client's pending enrollment for the action (approve request)."""
    from llmdmz.core.db import session_scope

    app = client_http.application
    with app.test_request_context():
        with session_scope(app) as s:
            e = s.scalars(
                select(Enrollment).where(
                    Enrollment.agent_id == agent_id, Enrollment.action_id == action_id
                )
            ).first()
            eid = e.id
    return client_http.post(
        f"/admin/enrollment/{eid}/approve", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )


class TestScenario1FullHappyPath:  # T5.1
    def test_register_approve_enroll_grant_invoke(self, app_fixture, client_http):
        app, provider_key, client_key = app_fixture
        # 1. Provider registers the action.
        assert client_http.post(
            "/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key)
        ).status_code == 201
        # 2. Admin approves (via admin-token console API).
        assert _approve_pending_version(client_http).status_code == 200
        # 3. Client requests enrollment; admin grants it.
        assert client_http.post(
            "/v2/actions/crm_search/enroll", headers=_hdr(client_key)
        ).status_code == 201
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            client = s.scalars(select(Agent).where(Agent.name == "client")).first()
            assert _grant_enrollment(client_http, client.id, "crm_search").status_code == 200
            s.close()
        # 4. Invoke succeeds (all fakes).
        app.extensions["DMZ_ARBITER"] = ApprovingArbiter()
        app.extensions["DMZ_TRANSPORT"] = ScriptedTransport([GOOD])
        resp = client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "Ada"}, headers=_hdr(client_key)
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["result"] == GOOD and body["action"] == "crm_search"
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            req = s.scalars(select(Request)).first()
            assert req.outcome == "completed"
            s.close()


class TestScenario2Withdrawal:  # T5.2 (#8/#10)
    def test_withdraw_404_reactivation_enrollment_survives(self, app_fixture, client_http):
        from llmdmz.dispatch.interfaces import ProviderResult

        app, provider_key, client_key = app_fixture
        app.extensions["DMZ_ARBITER"] = ApprovingArbiter()
        app.extensions["DMZ_TRANSPORT"] = ScriptedTransport([GOOD])
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_pending_version(client_http)
        client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            client = s.scalars(select(Agent).where(Agent.name == "client")).first()
            _grant_enrollment(client_http, client.id, "crm_search")
            enrollment_id = s.scalars(
                select(Enrollment).where(Enrollment.action_id == "crm_search")
            ).first().id
            s.close()
        assert client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "A"}, headers=_hdr(client_key)
        ).status_code == 200

        # Withdraw -> invoke returns 404.
        assert client_http.delete("/v2/actions/crm_search", headers=_hdr(provider_key)).status_code == 200
        assert client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "A"}, headers=_hdr(client_key)
        ).status_code == 404

        # New version approved -> auto-reactivation; enrollment still valid.
        app.extensions["DMZ_TRANSPORT"] = ScriptedTransport([GOOD])
        assert client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key)
        ).status_code == 201
        _approve_pending_version(client_http)
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            e = s.get(Enrollment, enrollment_id)
            assert e.state == "enrolled"  # carried forward, no re-enroll
            s.close()
        resp = client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "A"}, headers=_hdr(client_key)
        )
        assert resp.status_code == 200 and resp.get_json()["version"] == 2


class TestScenario3EdgePaths:  # T5.3
    def test_supersede_rejection_reset_retry_exhaustion_arbiter_outage(self, app_fixture, client_http):
        from llmdmz.dispatch.interfaces import ArbiterTransportError, ProviderResult, Verdict

        app, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_pending_version(client_http)
        # Supersede: v2 approved -> v1 superseded.
        client_http.put("/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_pending_version(client_http)
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            action = s.get(Action, "crm_search")
            assert [v.state for v in action.versions] == ["superseded", "active"]
            s.close()

        # Enrollment rejection -> admin reset -> re-request (#11).
        client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            e = s.scalars(select(Enrollment).where(Enrollment.action_id == "crm_search")).first()
            eid = e.id
            s.close()
        client_http.post(
            f"/admin/enrollment/{eid}/reject", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        client_http.post(
            f"/admin/enrollment/{eid}/reset", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        assert client_http.post(
            "/v2/actions/crm_search/enroll", headers=_hdr(client_key)
        ).status_code == 201  # re-request allowed after reset
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            client = s.scalars(select(Agent).where(Agent.name == "client")).first()
            s.close()
        _grant_enrollment(client_http, client.id, "crm_search")

        # Retry exhaustion -> 502 provider_failed.
        class FlakyArbiter:
            def check(self, *, side, action_id, payload, extra_instructions=""):
                return Verdict(approved=True, reason="ok")

        app.extensions["DMZ_ARBITER"] = FlakyArbiter()
        app.extensions["DMZ_TRANSPORT"] = ScriptedTransport([
            ProviderResult(error_class="transport", error_detail="boom"),
            ProviderResult(error_class="transport", error_detail="boom"),
            ProviderResult(error_class="transport", error_detail="boom"),
        ])
        resp = client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "A"}, headers=_hdr(client_key)
        )
        assert resp.status_code == 502

        # Arbiter outage on the request side -> 503, nothing dispatched.
        class OutageArbiter:
            def check(self, *, side, action_id, payload, extra_instructions=""):
                raise ArbiterTransportError("down")

        app.extensions["DMZ_ARBITER"] = OutageArbiter()
        t = ScriptedTransport([])
        app.extensions["DMZ_TRANSPORT"] = t
        resp = client_http.post(
            "/v2/actions/crm_search/invoke", json={"name": "A"}, headers=_hdr(client_key)
        )
        assert resp.status_code == 503 and t.framings == []
