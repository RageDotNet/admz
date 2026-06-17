"""Tests for the A2A DMZ admin web UI."""

from __future__ import annotations

from tests.conftest import CRM_REQUEST, REV_HEADERS, make_a2a_task


def _login(client, agent_id: str = "reviewer1", agent_key: str = "review-dev-key-change-me"):
    return client.post(
        "/admin/login",
        data={"agent_id": agent_id, "agent_key": agent_key},
        follow_redirects=True,
    )


def test_admin_login_page(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert b"Reviewer sign-in" in response.data


def test_admin_login_rejects_requestor(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.post(
        "/admin/login",
        data={"agent_id": "ext_agent", "agent_key": "ext-dev-key-change-me"},
    )
    assert response.status_code == 401
    assert b"reviewer" in response.data.lower()


def test_admin_login_accepts_reviewer(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = _login(client)
    assert response.status_code == 200
    assert b"A2A DMZ Gateway" in response.data
    assert b"reviewer1" in response.data


def test_admin_login_accepts_datastar_form(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.post(
        "/admin/login",
        data={"agent_id": "reviewer1", "agent_key": "review-dev-key-change-me"},
        headers={"Datastar-Request": "true"},
    )
    assert response.status_code == 200
    assert b"window.location.assign" in response.data
    assert b"/admin" in response.data


def test_admin_login_datastar_shows_error(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.post(
        "/admin/login",
        data={"agent_id": "reviewer1", "agent_key": "wrong-key"},
        headers={"Datastar-Request": "true"},
    )
    assert response.status_code == 401
    assert b'id="login-error"' in response.data
    assert b"Invalid agent credentials" in response.data


def test_admin_dashboard_requires_auth(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_admin_schemas_partial(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    _login(client)
    response = client.get("/admin/partials/schemas")
    assert response.status_code == 200
    assert b"crm_search" in response.data
    assert b"requestee_a2a_url" in response.data.lower() or b"127.0.0.1:5001" in response.data


def test_admin_inflight_and_log(a2a_flask_app, a2a_gateway, patch_storage, mock_a2a_client) -> None:
    from flask import Flask

    client = a2a_flask_app.test_client()
    _login(client)

    task = make_a2a_task(request_id="admin-inflight")
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Agent-Id": "ext_agent", "X-Agent-Key": "ext-dev-key-change-me"}):
        a2a_gateway.handle_task(task)

    patch_storage.update_request("admin-inflight", status="pending_review_request")

    inflight = client.get("/admin/partials/inflight")
    assert inflight.status_code == 200
    assert b"admin-inflight" in inflight.data
    assert b"pending_review_request" in inflight.data

    patch_storage.update_request("admin-inflight", status="completed")
    log = client.get("/admin/partials/log")
    assert log.status_code == 200
    assert b"admin-inflight" in log.data
    assert b"Access log" in log.data


def test_admin_reviews_and_approve(a2a_flask_app, a2a_gateway, patch_storage) -> None:
    from flask import Flask

    client = a2a_flask_app.test_client()
    _login(client)

    patch_storage.create_request(
        request_id="admin-review",
        schema_id="crm_search",
        requestor_id="ext_agent",
        requestee_id="int_agent",
        request_payload=CRM_REQUEST,
    )
    patch_storage.update_request("admin-review", status="pending_review_request")
    review = patch_storage.enqueue_review(
        request_id="admin-review",
        review_type="request",
        reason="Suspicious query",
        payload_snapshot=CRM_REQUEST,
    )

    pending = client.get("/admin/partials/reviews")
    assert pending.status_code == 200
    assert b"admin-review" in pending.data
    assert b"Suspicious query" in pending.data

    approved = client.post(f"/admin/review/{review.id}/approve", json={"notes": "Looks fine"})
    assert approved.status_code == 200
    assert b"No items pending human review" in approved.data or b"reviews-content" in approved.data
    assert patch_storage.get_request("admin-review").status == "pending_requestee"
    assert patch_storage.get_review(review.id).status == "approved"


def test_admin_partials_require_auth(a2a_flask_app) -> None:
    client = a2a_flask_app.test_client()
    response = client.get("/admin/partials/stats")
    assert response.status_code == 401
