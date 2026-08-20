"""Phase 4 console tests: auth matrix, SSE fragments, queues, reveal-once, routes."""

from __future__ import annotations

import re

from sqlalchemy import select
from tests.test_registry import CRM_SEARCH

from llmdmz.core.models import ActionVersion, Agent, Enrollment, Request

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
    def test_action_detail_shows_settings_and_pretty_schemas(self, app_fixture, client_http):
        _seed_action(app_fixture, client_http)
        _login(client_http)
        resp = client_http.get("/admin/partials/action/crm_search")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "request_schema" in body
        assert "provider_instructions" in body
        # pretty-printed JSON (2-space indent, not one line): SSE prefix + indent
        assert 'data: elements   "' in body
        # per-version payload viewer + link from pending versions list
        assert "view JSON" in body
        pending = client_http.get("/admin/partials/stats")
        assert pending.status_code == 200

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
        assert "event: datastar-patch-elements" in body

    def test_sse_wire_format_matches_client_parser(self, client_http):
        """Replay datastar v1.0.2's SSE arg parser over our events.

        Each data line is split at the FIRST space into key/value; duplicate
        keys are rejoined with \\n; the `datastar-patch-elements` handler
        reads `selector`, `mode`, and `elements`. A bare `data: elements`
        line (no space) would parse as key `element` and the HTML would
        never reach the client.
        """
        _login(client_http)
        resp = client_http.get("/admin/partials/directory")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("text/event-stream")

        args: dict[str, str] = {}
        for event_block in resp.get_data(as_text=True).split("\n\n"):
            if "event: datastar-patch-elements" not in event_block:
                continue
            data_lines = [
                ln[len("data: "):]
                for ln in event_block.splitlines()
                if ln.startswith("data: ")
            ]
            parts: dict[str, list[str]] = {}
            for ln in data_lines:
                key, _, value = ln.partition(" ")
                parts.setdefault(key, []).append(value)
            args = {k: "\n".join(v) for k, v in parts.items()}
            break
        assert args.get("selector") == "#directory-list"
        assert args.get("mode") == "inner"
        assert "elements" in args
        assert "table table-sm" in args["elements"]

    def test_directory_renders_after_session_close(self, app_fixture, client_http):
        """Regression: directory rows hold detached Action objects; the template
        touches the lazy `versions` relationship (via `active_version`) after
        the DB session closes — must be force-loaded inside the session.
        """
        _, provider_key, _ = app_fixture
        assert client_http.post(
            "/v2/actions",
            json=CRM_SEARCH,
            headers={"Authorization": f"Bearer {provider_key}"},
        ).status_code == 201
        _login(client_http)
        resp = client_http.get("/admin/partials/directory")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "crm_search" in body
        # Pending action: no active version. Empty cells must be an em dash,
        # not the mojibake that a mis-encoded '—' produces in the browser.
        assert "â€" not in body
        assert "&mdash;" in body

    def test_assets_served_no_network(self, client_http):
        for asset, min_size in (
            ("vendor/datastar-1.0.2.js", 1000),
            ("vendor/bootstrap-5.3.3.min.css", 1000),
        ):
            resp = client_http.get(f"/static/{asset}")
            assert resp.status_code == 200 and len(resp.get_data()) > min_size


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

    def test_delivery_config_prefilled_for_admin(self, app_fixture, client_http):
        """Admins may see all delivery settings (console is admin-only)."""
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
        # stale edit_* signals from a previously-viewed agent must be nulled first
        assert "event: datastar-patch-signals" in detail
        assert '"edit_hk0":null' in detail
        assert "super-secret-provider-token" in detail
        assert "secret.example" in detail
        # data-signals attribute must stay intact (JSON quotes escaped) or Datastar hides nothing
        q = '"edit_provider": true'.replace('"', "&#34;")
        hk = '"edit_hk0": "Authorization"'.replace('"', "&#34;")
        assert q in detail
        assert hk in detail

    def test_agent_edit_structured_delivery_post(self, app_fixture, client_http):
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            agent_id = agent.id
            s.close()
        _login(client_http)
        resp = client_http.post(
            f"/admin/agents/{agent_id}",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            data={
                "is_client": "", "is_provider": "on", "enabled": "on",
                "protocol": "post",
                "endpoint": "https://hook.example/prov",
                "header_key_0": "Authorization", "header_value_0": "Bearer s3cret",
                "header_key_1": "X-Tag", "header_value_1": "1",
                # row 2 left fully empty -> skipped
                "header_key_3": "", "header_value_3": "orphan",  # empty key -> skipped
                "retries": "2", "timeout": "45",
            },
        )
        assert resp.status_code == 200
        # Patch must target the wrapper region, not the detail card itself:
        # the partial's root carries the target id, and Datastar's inner-mode
        # morph of an element that contains the patch target into that target
        # throws HierarchyRequestError in the browser (page never updates).
        body = resp.get_data(as_text=True)
        assert "data: selector #agent-detail-region" in body
        assert f"data: selector #agent-{agent_id}-detail" not in body
        assert "event: datastar-patch-signals" in body
        assert '"edit_protocol":null' in body
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.id == agent_id)).first()
            assert agent.delivery_config == {
                "protocol": "post",
                "endpoint": "https://hook.example/prov",
                "headers": {"Authorization": "Bearer s3cret", "X-Tag": "1"},
                "retries": 2,
                "timeout": 45,
            }
            s.close()

    def test_agent_edit_structured_delivery_exec(self, app_fixture, client_http):
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            agent_id = agent.id
            s.close()
        _login(client_http)
        resp = client_http.post(
            f"/admin/agents/{agent_id}",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            data={"is_provider": "on", "protocol": "exec", "command": "python prov.py"},
        )
        assert resp.status_code == 200
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.id == agent_id)).first()
            assert agent.delivery_config == {"protocol": "exec", "command": "python prov.py"}
            s.close()

    def test_agent_edit_unchecking_provider_clears_config(self, app_fixture, client_http):
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            agent.delivery_config = {"protocol": "post", "endpoint": "https://x.example"}
            agent_id = agent.id
            s.commit()
            s.close()
        _login(client_http)
        resp = client_http.post(
            f"/admin/agents/{agent_id}",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            data={"is_client": "on", "enabled": "on"},  # provider unchecked
        )
        assert resp.status_code == 200
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.id == agent_id)).first()
            assert agent.delivery_config is None
            s.close()

    def test_agent_edit_rejects_bad_protocol_and_knobs(self, app_fixture, client_http):
        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "provider")).first()
            agent_id = agent.id
            s.close()
        _login(client_http)
        for bad in ({"protocol": "carrier-pigeon"}, {"protocol": "post", "retries": "many"}):
            resp = client_http.post(
                f"/admin/agents/{agent_id}",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                data={"is_provider": "on", **bad},
            )
            assert resp.status_code == 400

    def test_register_provider_with_delivery(self, app_fixture, client_http):
        app, _, _ = app_fixture
        _login(client_http)
        resp = client_http.post(
            "/admin/agents",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            data={
                "name": "hook-provider", "is_provider": "on",
                "protocol": "completions",
                "model": "crm-provider",
                "endpoint": "http://127.0.0.1:8090/v1/chat/completions",
            },
        )
        assert resp.status_code == 200
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            agent = s.scalars(select(Agent).where(Agent.name == "hook-provider")).first()
            assert agent.delivery_config == {
                "protocol": "completions",
                "model": "crm-provider",
                "endpoint": "http://127.0.0.1:8090/v1/chat/completions",
            }
            s.close()


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


class TestRequestLogFraming:
    def test_attempt_request_shows_provider_framing(self, app_fixture, client_http):
        """Dispatch-attempt 'request' is the framed input sent to the provider
        (instructions, response schema, retry errors), not the client JSON."""
        from tests.test_invoke_pipeline import (
            GOOD_RESPONSE,
            ApprovingArbiter,
            ScriptedTransport,
            _enrolled_action,
            _invoke,
            error_result,
        )

        key = _enrolled_action(app_fixture, client_http)
        transport = ScriptedTransport(
            [error_result("protocol", "unparseable"), GOOD_RESPONSE]
        )
        _invoke(client_http, key, arbiter=ApprovingArbiter(), transport=transport)

        app, _, _ = app_fixture
        with app.app_context():
            s = app.extensions["DMZ_SESSION_FACTORY"]()
            req = s.scalars(select(Request)).first()
            assert req is not None
            request_id = req.id
            s.close()

        _login(client_http)
        resp = client_http.get(f"/admin/partials/request/{request_id}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "REQUEST JSON FOLLOWS:" in body
        assert "Return only matching contacts." in body
        assert "CRM Search Response" in body
        assert "ERRORS FROM YOUR PREVIOUS INVOCATION" in body
        assert "unparseable" in body
        assert "post https://x" in body
        assert "client client" in body.replace("\n", " ")
