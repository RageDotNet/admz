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
