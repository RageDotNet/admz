"""T2.8: action lifecycle API tests (fixture: app + tables + agents)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from llmdmz.app import create_app
from llmdmz.core import storage
from llmdmz.core.models import Action, ActionVersion, AuditEvent, Base

from tests.test_registry import CRM_SEARCH


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


def _hdr(key):
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
        # No key → 401.
        assert client_http.post("/v2/actions", json=CRM_SEARCH).status_code == 401
        # Garbage key → 401.
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr("dmz_garbage"))
        assert resp.status_code == 401
        # Client capability → 403.
        resp = client_http.post("/v2/actions", json=CRM_SEARCH, headers=_hdr(client_key))
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "forbidden"
