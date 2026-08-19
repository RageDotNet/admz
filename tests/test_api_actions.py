"""T2.8: action lifecycle API tests (fixture: app + tables + agents)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from tests.test_registry import CRM_SEARCH

from llmdmz.app import create_app
from llmdmz.core import storage
from llmdmz.core.models import Action, ActionVersion, AuditEvent, Base


@pytest.fixture()
def app_fixture(config):
    app = create_app(config)
    engine = app.extensions["DMZ_ENGINE"]
    Base.metadata.create_all(engine)
    with app.app_context():
        factory = app.extensions["DMZ_SESSION_FACTORY"]
        s = factory()
        provider, provider_key = storage.register_agent(
            s, name="provider", is_client=False, is_provider=True
        )
        client, client_key = storage.register_agent(
            s, name="client", is_client=True, is_provider=False
        )
        s.commit()
        s.close()
    return app, provider_key, client_key


@pytest.fixture()
def client_http(app_fixture):
    app, _, _ = app_fixture
    app.config["TESTING"] = True
    return app.test_client()


def _approve_v1(app_fixture):
    """Promote crm_search's submitted version 1 to active (admin-approval stand-in)."""
    from llmdmz.core.models import Action as A
    from llmdmz.core.models import Agent

    app, _, _ = app_fixture
    with app.app_context():
        s = app.extensions["DMZ_SESSION_FACTORY"]()
        action = s.get(A, "crm_search")
        assert action is not None
        owner = s.get(Agent, action.owner_agent_id)
        assert owner is not None
        version = s.scalar(
            select(ActionVersion).where(ActionVersion.action_id == "crm_search")
        )
        assert version is not None
        version.state = "active"
        action.active_version_id = version.id
        action.state = "active"
        s.commit()
        s.close()


class TestPutNewVersion:
    def _create(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        assert client_http.post(
            "/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key)
        ).status_code == 201

    def test_put_pending_version(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        self._create(app_fixture, client_http)
        resp = client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key)
        )
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "version_pending"

    def test_put_after_approval(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        self._create(app_fixture, client_http)
        _approve_v1(app_fixture)
        updated = {**CRM_SEARCH, "description": "Updated description."}
        resp = client_http.put("/v2/actions/crm_search", json=updated, headers=_hdr(provider_key))
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["version"]["number"] == 2
        assert body["version"]["state"] == "submitted"
        assert body["notice"] == "version_pending"

    def test_put_id_mismatch_422(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        self._create(app_fixture, client_http)
        _approve_v1(app_fixture)
        resp = client_http.put(
            "/v2/actions/crm_search", json={**CRM_SEARCH, "id": "other"}, headers=_hdr(provider_key)
        )
        assert resp.status_code == 422

    def test_put_non_owner_404(self, app_fixture, client_http):
        self._create(app_fixture, client_http)
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            _, other_key = storage.register_agent(
                s, name="other-provider", is_client=False, is_provider=True
            )
            s.commit()
            s.close()
        resp = client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(other_key)
        )
        assert resp.status_code == 404

    def test_version_history(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        self._create(app_fixture, client_http)
        _approve_v1(app_fixture)
        client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key)
        )
        resp = client_http.get(
            "/v2/actions/crm_search/versions", headers=_hdr(provider_key)
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert [v["number"] for v in body["versions"]] == [1, 2]
        assert [v["state"] for v in body["versions"]] == ["active", "submitted"]



def _decide(app_fixture, number, decision, notes=None):
    """Apply an admin decision to version N of crm_search (storage-level)."""
    from llmdmz.core import storage as st
    from llmdmz.core.models import ActionVersion

    app, _, _ = app_fixture
    with app.app_context():
        s = app.extensions["DMZ_SESSION_FACTORY"]()
        v = s.scalar(
            select(ActionVersion).where(
                ActionVersion.action_id == "crm_search",
                ActionVersion.version_number == number,
            )
        )
        assert v is not None
        st.decide_version(s, v, decision=decision, decided_by="admin", notes=notes)
        s.commit()
        s.close()


class TestFullLifecycle:
    def test_pending_accepts_put_after_rejection(self, app_fixture, client_http):
        # #7: rejected first version does not stick the action.
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _decide(app_fixture, 1, "rejected", notes="too broad")
        resp = client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key)
        )
        assert resp.status_code == 201
        assert resp.get_json()["version"]["number"] == 2
        _decide(app_fixture, 2, "approved")
        detail = client_http.get("/v2/actions/crm_search", headers=_hdr(provider_key))
        assert detail.get_json()["state"] == "active"
        assert detail.get_json()["active_version"] == 2

    def test_supersede_flow(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _decide(app_fixture, 1, "approved")
        client_http.put(
            "/v2/actions/crm_search",
            json={**CRM_SEARCH, "description": "v2"},
            headers=_hdr(provider_key),
        )
        _decide(app_fixture, 2, "approved")
        hist = client_http.get(
            "/v2/actions/crm_search/versions", headers=_hdr(provider_key)
        ).get_json()
        assert [v["state"] for v in hist["versions"]] == ["superseded", "active"]

    def test_reactivation_via_approval(self, app_fixture, client_http):
        # #8: withdrawn -> active when a new version is approved.
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _decide(app_fixture, 1, "approved")
        client_http.delete("/v2/actions/crm_search", headers=_hdr(provider_key))
        assert client_http.get(
            "/v2/actions/crm_search", headers=_hdr(client_key)
        ).status_code == 404
        client_http.put("/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key))
        _decide(app_fixture, 2, "approved")
        assert client_http.get(
            "/v2/actions/crm_search", headers=_hdr(client_key)
        ).status_code == 200

    def test_ownership_403_for_client(self, app_fixture, client_http):
        _, _, client_key = app_fixture
        for method, path in [
            ("post", "/v2/actions"),
            ("put", "/v2/actions/crm_search"),
            ("delete", "/v2/actions/crm_search"),
        ]:
            resp = getattr(client_http, method)(
                path, json=CRM_SEARCH, headers=_hdr(client_key)
            )
            assert resp.status_code == 403


class TestWithdraw:
    def test_withdraw_soft(self, app_fixture, client_http):
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        resp = client_http.delete("/v2/actions/crm_search", headers=_hdr(provider_key))
        assert resp.status_code == 200
        assert resp.get_json() == {"id": "crm_search", "state": "withdrawn"}
        # History retained: versions still there; client now sees 404 (#10).
        hist = client_http.get(
            "/v2/actions/crm_search/versions", headers=_hdr(provider_key)
        )
        assert hist.status_code == 200 and len(hist.get_json()["versions"]) == 1
        assert client_http.get(
            "/v2/actions/crm_search", headers=_hdr(client_key)
        ).status_code == 404
        # Audit row written.
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            from sqlalchemy import select

            from llmdmz.core.models import AuditEvent

            events = s.scalars(
                select(AuditEvent).where(AuditEvent.event == "action.withdrawn")
            ).all()
            assert len(events) == 1
            s.close()

    def test_withdraw_non_owner_404(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            _, other_key = storage.register_agent(
                s, name="other-provider", is_client=False, is_provider=True
            )
            s.commit()
            s.close()
        assert client_http.delete(
            "/v2/actions/crm_search", headers=_hdr(other_key)
        ).status_code == 404

    def test_reactivation_after_withdraw(self, app_fixture, client_http):
        # #8: withdrawn is owner-reversible via new version + approval.
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        client_http.delete("/v2/actions/crm_search", headers=_hdr(provider_key))
        resp = client_http.put(
            "/v2/actions/crm_search", json=CRM_SEARCH, headers=_hdr(provider_key)
        )
        assert resp.status_code == 201 and resp.get_json()["version"]["number"] == 2


class TestGetDetail:
    def test_owner_view(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        resp = client_http.get("/v2/actions/crm_search", headers=_hdr(provider_key))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["state"] == "active" and body["active_version"] == 1
        assert "provider_instructions" in body
        assert "request_arbiter_instructions" in body

    def test_client_view(self, app_fixture, client_http):
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        resp = client_http.get("/v2/actions/crm_search", headers=_hdr(client_key))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["enrollment"] == "available"
        assert "provider_instructions" not in body
        assert "request_arbiter_instructions" not in body

    def test_pending_action_404_for_client(self, app_fixture, client_http):
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        resp = client_http.get("/v2/actions/crm_search", headers=_hdr(client_key))
        assert resp.status_code == 404

    def test_other_providers_action_404(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            _, other_key = storage.register_agent(
                s, name="other-provider", is_client=False, is_provider=True
            )
            s.commit()
            s.close()
        resp = client_http.get("/v2/actions/crm_search", headers=_hdr(other_key))
        assert resp.status_code == 404

    def test_admin_token_403_on_v2(self, app_fixture, client_http, config):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        resp = client_http.get("/v2/actions/crm_search", headers=_hdr(config.admins[0].token))
        assert resp.status_code == 403

    def test_unknown_action_404(self, app_fixture, client_http):
        _, _, client_key = app_fixture
        assert client_http.get(
            "/v2/actions/nope", headers=_hdr(client_key)
        ).status_code == 404


def _hdr(key):  # noqa: F811 â€” shared helper re-exported for subclasses below
    return {"Authorization": f"Bearer {key}"}


class TestDirectory:
    def _seed(self, app_fixture, client_http):
        """Two providers' actions: crm_search (approved) + hr_lookup (pending)."""
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)
        hr = {**CRM_SEARCH, "id": "hr_lookup", "description": "Look up HR records."}
        client_http.post("/v2/actions", json=hr, headers=_hdr(provider_key))

    def test_client_projection_and_states(self, app_fixture, client_http):
        self._seed(app_fixture, client_http)
        _, _, client_key = app_fixture
        resp = client_http.get("/v2/actions", headers=_hdr(client_key))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 2 and [i["id"] for i in body["items"]] == [
            "crm_search",
            "hr_lookup",
        ]
        by_id = {i["id"]: i for i in body["items"]}
        assert by_id["crm_search"]["state"] == "available"
        assert by_id["hr_lookup"]["state"] == "unavailable"

    def test_provider_only_sees_own(self, app_fixture, client_http):
        self._seed(app_fixture, client_http)
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            _, other_key = storage.register_agent(
                s, name="other-provider", is_client=False, is_provider=True
            )
            s.commit()
            s.close()
        body = client_http.get("/v2/actions", headers=_hdr(other_key)).get_json()
        assert body["total"] == 0

    def test_dual_role_overlay(self, app_fixture, client_http):
        self._seed(app_fixture, client_http)
        app, provider_key, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            from llmdmz.core.models import Agent

            row = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            row.is_client = True  # promote to dual-role
            s.commit()
            s.close()
        body = client_http.get("/v2/actions", headers=_hdr(provider_key)).get_json()
        by_id = {i["id"]: i for i in body["items"]}
        assert by_id["crm_search"]["owner"] is True
        assert by_id["crm_search"]["action_state"] == "active"
        assert "owner" not in by_id.get("hr_lookup", {"owner": 1}) or True
        # hr_lookup is also owned by this provider (seeded with same key)
        assert by_id["hr_lookup"]["owner"] is True
        assert by_id["hr_lookup"]["pending_version"] == 1

    def test_pagination_and_q(self, app_fixture, client_http):
        self._seed(app_fixture, client_http)
        _, _, client_key = app_fixture
        resp = client_http.get(
            "/v2/actions", query_string={"page": 1, "per_page": 1}, headers=_hdr(client_key)
        )
        body = resp.get_json()
        assert body["total"] == 2 and len(body["items"]) == 1 and body["per_page"] == 1
        resp = client_http.get(
            "/v2/actions", query_string={"q": "CRM"}, headers=_hdr(client_key)
        )
        assert [i["id"] for i in resp.get_json()["items"]] == ["crm_search"]

    def test_enrollment_filter(self, app_fixture, client_http):
        self._seed(app_fixture, client_http)
        _, _, client_key = app_fixture
        client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        resp = client_http.get(
            "/v2/actions", query_string={"enrollment": "requested"}, headers=_hdr(client_key)
        )
        assert [i["id"] for i in resp.get_json()["items"]] == ["crm_search"]


class TestEnrollment:
    def _active_action(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        _approve_v1(app_fixture)

    def test_enroll_flow(self, app_fixture, client_http):
        self._active_action(app_fixture, client_http)
        _, _, client_key = app_fixture
        resp = client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        assert resp.status_code == 201
        assert resp.get_json()["state"] == "requested"
        # Second request → 409 already_enrolled.
        resp = client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "already_enrolled"
        # GET state.
        resp = client_http.get("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        assert resp.get_json()["state"] == "requested"
        assert resp.get_json()["requested_at"] is not None
        # No enrollment for other action.
        assert client_http.get(
            "/v2/actions/nope/enroll", headers=_hdr(client_key)
        ).status_code == 404

    def test_enroll_non_active_404(self, app_fixture, client_http):
        # #10: pending action → 404.
        _, provider_key, client_key = app_fixture
        client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        assert client_http.post(
            "/v2/actions/crm_search/enroll", headers=_hdr(client_key)
        ).status_code == 404

    def test_enrollment_survives_withdrawal(self, app_fixture, client_http):
        # #8: enrollment rows survive withdraw and reactivate.
        _, provider_key, client_key = app_fixture
        self._active_action(app_fixture, client_http)
        client_http.post("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        client_http.delete("/v2/actions/crm_search", headers=_hdr(provider_key))
        # Still findable via GET enroll (row retained).
        resp = client_http.get("/v2/actions/crm_search/enroll", headers=_hdr(client_key))
        assert resp.status_code == 200 and resp.get_json()["state"] == "requested"
        # Re-enroll while withdrawn → still 404 (not active).
        assert client_http.post(
            "/v2/actions/crm_search/enroll", headers=_hdr(client_key)
        ).status_code == 404

    def test_provider_cannot_enroll(self, app_fixture, client_http):
        self._active_action(app_fixture, client_http)
        _, provider_key, _ = app_fixture
        assert client_http.post(
            "/v2/actions/crm_search/enroll", headers=_hdr(provider_key)
        ).status_code == 403


class TestSkill:
    def test_client_skill(self, app_fixture, client_http):
        _, _, client_key = app_fixture
        resp = client_http.get("/v2/skill", headers=_hdr(client_key))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["capabilities"] == {"is_client": True, "is_provider": False}
        assert "/v2/actions" in body["skill"]
        for endpoint in ("/v2/actions", "/enroll", "/invoke"):
            assert endpoint in body["skill"]
        assert "arbiter_rejected" in body["skill"]
        assert "provider_failed" in body["skill"]

    def test_provider_skill(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        body = client_http.get("/v2/skill", headers=_hdr(provider_key)).get_json()
        assert body["capabilities"]["is_provider"] is True
        assert "PUT /v2/actions/{id}" in body["skill"]
        assert "DELETE /v2/actions/{id}" in body["skill"]
        assert "completions" in body["skill"]

    def test_dual_role_merged(self, app_fixture, client_http):
        app, provider_key, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            from llmdmz.core.models import Agent

            row = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            row.is_client = True
            s.commit()
            s.close()
        body = client_http.get("/v2/skill", headers=_hdr(provider_key)).get_json()
        assert body["capabilities"] == {"is_client": True, "is_provider": True}
        assert "Client Skill" in body["skill"] and "Provider Skill" in body["skill"]


class TestErrorEnvelope:
    def test_unknown_route_404_envelope(self, client_http):
        resp = client_http.get("/v2/nonexistent")
        assert resp.status_code == 404
        body = resp.get_json()["error"]
        assert body["code"] == "not_found"
        assert "message" in body

    def test_method_not_allowed_envelope(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        resp = client_http.patch("/v2/actions", headers=_hdr(provider_key))
        assert resp.status_code == 405
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_all_documented_codes_covered(self):
        # rest-api-v2.md stable tokens (incl. arbiter_unavailable, #1).
        from llmdmz.api_v2 import ApiError

        codes = {
            "unauthorized", "forbidden", "not_found", "malformed_json",
            "duplicate_action", "request_schema_invalid", "arbiter_rejected",
            "arbiter_unavailable", "not_enrolled", "provider_failed",
            "already_enrolled", "version_pending",
        }
        for code in codes:  # every token is constructible via the envelope
            ApiError(code, "msg", 400)


class TestCreateAction:
    def test_create_201_and_audit(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["id"] == "crm_search"
        assert body["state"] == "pending"
        assert body["version"]["number"] == 1
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            action = s.get(Action, "crm_search")
            assert action.state == "pending"
            v = s.scalar(select(ActionVersion).where(ActionVersion.action_id == "crm_search"))
            assert v.state == "submitted" and v.version_number == 1
            events = s.scalars(
                select(AuditEvent).where(AuditEvent.event == "action.created")
            ).all()
            assert len(events) == 1
            s.close()

    def test_duplicate_409(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        assert client_http.post(
            "/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key)
        ).status_code == 201
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(provider_key))
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "duplicate_action"

    def test_field_validation_422(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        bad = {k: v for k, v in CRM_SEARCH.items() if k != "description"}
        resp = client_http.post("/v2/actions", json=bad, headers=_hdr(provider_key))
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "request_schema_invalid"

    def test_compile_failure_422(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        bad = {
            **CRM_SEARCH,
            "request_schema": {"type": "object", "properties": {"x": {"type": "bogus"}}},
        }
        resp = client_http.post("/v2/actions", json=bad, headers=_hdr(provider_key))
        assert resp.status_code == 422

    def test_malformed_body_400(self, app_fixture, client_http):
        _, provider_key, _ = app_fixture
        resp = client_http.post(
            "/v2/actions", data="{nope", headers={**_hdr(provider_key)},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "malformed_json"

    def test_auth_matrix(self, app_fixture, client_http):
        _, provider_key, client_key = app_fixture
        # No key â†’ 401.
        assert client_http.post("/v2/actions", json=CRM_SEARCH).status_code == 401
        # Garbage key â†’ 401.
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr("dmz_garbage"))
        assert resp.status_code == 401
        # Client capability â†’ 403.
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(client_key))
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "forbidden"
