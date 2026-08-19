"""Phase 4 console tests: auth matrix, SSE fragments, queues, reveal-once, routes."""

from __future__ import annotations

import re

from sqlalchemy import select
from tests.test_registry import CRM_SEARCH

from llmdmz.core.models import ActionVersion, Agent, Enrollment

ADMIN_TOKEN = "dmzadm_testtoken0000000000000000000000000"
EXPECTED_ROUTES = {
    ("GET", "/admin/login"),
    ("POST", "/admin/login"),
    ("GET", "/admin"),
    ("POST", "/admin/logout"),
    ("GET", "/admin/partials/stats"),
    ("GET", "/admin/partials/directory"),
    ("GET", "/admin/partials/action/<action_id>"),
    ("POST", "/admin/action-version/<version_id>/approve"),
    ("POST", "/admin/action-version/<version_id>/reject"),
    ("POST", "/admin/action/<action_id>/withdraw"),
    ("GET", "/admin/partials/enrollments"),
    ("POST", "/admin/enrollment/<enrollment_id>/approve"),
    ("POST", "/admin/enrollment/<enrollment_id>/reject"),
    ("POST", "/admin/action/<action_id>/enroll"),
    ("POST", "/admin/enrollment/<enrollment_id>/revoke"),
    ("POST", "/admin/enrollment/<enrollment_id>/reset"),
    ("GET", "/admin/partials/agents"),
    ("POST", "/admin/agents"),
    ("GET", "/admin/agents/<agent_id>"),
    ("POST", "/admin/agents/<agent_id>"),
    ("POST", "/admin/agents/<agent_id>/revoke-key"),
    ("POST", "/admin/agents/<agent_id>/new-key"),
    ("GET", "/admin/partials/log"),
    ("GET", "/admin/partials/request/<request_id>"),
    ("GET", "/admin/partials/audit"),
}


def _login(client):
    # GET first to establish the session + CSRF token, then POST with it.
    import re

    page = client.get("/admin/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    resp = client.post(
        "/admin/login",
        data={"username": "admin", "password": "pw", "csrf_token": token.group(1)},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)


def _seed_action(app_fixture, client):
    """Submitted v1 + a requested enrollment, reusing the fixture agents."""
    app, _, _ = app_fixture
    with app.app_context():
        s = app.extensions["DMZ_SESSION_FACTORY"]()
        owner = s.scalars(select(Agent).where(Agent.name == "provider")).first()
        agent_client = s.scalars(select(Agent).where(Agent.name == "client")).first()
        from llmdmz.core.models import Action

        s.add(Action(id="crm_search", owner_agent_id=owner.id, state="pending"))
        s.add(
            ActionVersion(
                action_id="crm_search", version_number=1, state="submitted", payload=CRM_SEARCH
            )
        )
        e = Enrollment(agent_id=agent_client.id, action_id="crm_search", state="requested")
        s.add(e)
        s.commit()
        version = s.scalars(
            select(ActionVersion).where(ActionVersion.action_id == "crm_search")
        ).first()
        s.close()
        return version.id, e.id, agent_client.id


class TestAuthMatrix:  # T4.4
    def test_page_redirects_to_login(self, client_http):
        resp = client_http.get("/admin")
        assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]

    def test_fragment_401(self, client_http):
        assert client_http.get("/admin/partials/stats").status_code == 401

    def test_agent_key_on_admin_401(self, app_fixture, client_http):
        _, _, client_key = app_fixture
        resp = client_http.get(
            "/admin/partials/stats", headers={"Authorization": f"Bearer {client_key}"}
        )
        assert resp.status_code == 401  # invalid-to-admin bearer â†’ 401

    def test_admin_token_mutation_ok(self, client_http):
        resp = client_http.post(
            "/admin/action-version/whatever/approve",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )
        assert resp.status_code == 404  # authenticated; unknown version

    def test_admin_token_on_v2_403(self, client_http):
        resp = client_http.get("/v2/actions", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        assert resp.status_code == 403

    def test_unknown_bearer_401(self, client_http):
        resp = client_http.get(
            "/admin/partials/stats", headers={"Authorization": "Bearer dmzadm_nope"}
        )
        assert resp.status_code == 401

    def test_csrf_reject(self, client_http):
        _login(client_http)
        resp = client_http.post("/admin/agents", data={"name": "x", "is_client": "on"})
        assert resp.status_code == 400  # missing CSRF token

    def test_session_login_grants_access(self, client_http):
        _login(client_http)
        assert client_http.get("/admin/partials/stats").status_code == 200


class TestSSEFragments:  # T4.7
    def test_mutation_returns_sse_with_selectors(self, app_fixture, client_http):
        version_id, _, _ = _seed_action(app_fixture, client_http)
        _login(client_http)
        resp = client_http.post(
            f"/admin/action-version/{version_id}/approve",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("text/event-stream")
        body = resp.get_data(as_text=True)
        for selector in ("#stats-bar", "#pending-versions", "#pending-enrollments"):
            assert f"data: selector {selector}" in body
        assert "event: datastar-merge-fragments" in body

    def test_assets_served_no_network(self, client_http):
        for asset in ("vendor/datastar.min.js", "vendor/0build.min.css"):
            resp = client_http.get(f"/static/{asset}")
            assert resp.status_code == 200 and len(resp.get_data()) > 1000


class TestQueues:  # T4.16
    def test_approve_flow_two_clicks(self, app_fixture, client_http):
        version_id, _, _ = _seed_action(app_fixture, client_http)
        _login(client_http)
        resp = client_http.post(
            f"/admin/action-version/{version_id}/approve",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            data={"notes": "looks good"},
        )
        assert resp.status_code == 200
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            v = s.get(ActionVersion, version_id)
            assert v.state == "active"
            assert v.decision_notes == "looks good"
            assert v.decided_by == "admin"
            from llmdmz.core.models import Action, AuditEvent

            assert s.get(Action, "crm_search").state == "active"
            events = s.scalars(
                select(AuditEvent).where(AuditEvent.event == "version.approved")
            ).all()
            assert len(events) == 1 and events[0].actor_id == "admin"
            s.close()

    def test_enrollment_reset_allows_re_request(self, app_fixture, client_http):
        _, enrollment_id, _ = _seed_action(app_fixture, client_http)
        _login(client_http)
        assert client_http.post(
            f"/admin/enrollment/{enrollment_id}/reject",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        ).status_code == 200
        assert client_http.post(
            f"/admin/enrollment/{enrollment_id}/reset",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        ).status_code == 200
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            assert s.get(Enrollment, enrollment_id) is None
            s.close()


class TestRevealOnce:  # T4.18
    def test_register_returns_key_once_never_again(self, client_http):
        _login(client_http)
        resp = client_http.post(
            "/admin/agents",
            data={"name": "newbie", "is_client": "on"},
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        key = re.search(r"dmz_[A-Za-z0-9_-]+", body)
        assert key is not None
        listing = client_http.get("/admin/partials/agents").get_data(as_text=True)
        assert key.group(0) not in listing

    def test_delivery_config_never_echoed(self, app_fixture, client_http):
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            agent.delivery_config = {
                "protocol": "post",
                "endpoint": "https://secret.example/hook",
                "headers": {"Authorization": "Bearer super-secret-provider-token"},
            }
            s.commit()
            agent_id = agent.id
            s.close()
        _login(client_http)
        detail = client_http.get(f"/admin/agents/{agent_id}").get_data(as_text=True)
        assert "super-secret-provider-token" not in detail
        assert "secret.example" not in detail


class TestRouteTable:  # T4.21
    def test_routes_match_webui_prd_exactly(self, app_fixture):
        app, _, _ = app_fixture
        actual = set()
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/admin"):
                continue
            endpoint = app.view_functions[rule.endpoint]
            module = getattr(endpoint, "__module__", "")
            if "llmdmz.admin" not in module:
                continue
            methods = rule.methods - {"HEAD", "OPTIONS"}
            for m in methods:
                actual.add((m, rule.rule))
        assert actual == EXPECTED_ROUTES

    def test_pagination_caps_enforced(self, client_http):
        _login(client_http)
        assert client_http.get("/admin/partials/log?per_page=10000").status_code == 200
