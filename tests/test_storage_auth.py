"""T1.8 / T1.12: storage, keys, and auth unit tests (offline)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from llmdmz.core import storage
from llmdmz.core.audit import audit
from llmdmz.core.auth import resolve_bearer
from llmdmz.core.keys import (
    ADMIN_PREFIX,
    AGENT_PREFIX,
    generate_admin_token,
    generate_agent_key,
    hash_key,
)
from llmdmz.core.models import Base


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


def test_key_generation_prefixes_and_hashes():
    agent_key = generate_agent_key()
    admin_token = generate_admin_token()
    assert agent_key.startswith(AGENT_PREFIX)
    assert len(agent_key) == len(AGENT_PREFIX) + 43  # token_urlsafe(32) → 43 chars
    assert admin_token.startswith(ADMIN_PREFIX)
    assert hash_key(agent_key) != agent_key
    assert len(hash_key(agent_key)) == 64  # sha256 hex
    assert hash_key(agent_key) == hash_key(agent_key)


def test_register_agent_reveal_once(session):
    agent, key = storage.register_agent(session, name="acme", is_client=True, is_provider=False)
    assert key.startswith(AGENT_PREFIX)
    found = storage.find_agent_by_key(session, key)
    assert found is not None and found.id == agent.id
    # The row stores only the hash — the plaintext key is never persisted.
    assert found.api_key_hash == hash_key(key) != key
    # Re-issue: old key dies, new key works (reveal-once).
    new_key = storage.issue_key(session, found)
    assert storage.find_agent_by_key(session, key) is None
    assert storage.find_agent_by_key(session, new_key).id == agent.id


def test_unique_constraints(session):
    a1, _ = storage.register_agent(session, name="one", is_client=True, is_provider=False)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        storage.register_agent(session, name="one", is_client=True, is_provider=False)
    from llmdmz.core.models import Action, ActionVersion, Enrollment

    session.rollback()
    action = Action(id="act", owner_agent_id=a1.id, state="pending")
    session.add(action)
    session.flush()
    v1 = ActionVersion(action_id="act", version_number=1, state="submitted", payload={})
    session.add(v1)
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(ActionVersion(action_id="act", version_number=1, state="submitted", payload={}))
        session.flush()
    session.rollback()
    session.add(Enrollment(agent_id=a1.id, action_id="act", state="requested"))
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(Enrollment(agent_id=a1.id, action_id="act", state="requested"))
        session.flush()


def test_pagination_bounds(session):
    for i in range(7):
        storage.register_agent(session, name=f"agent{i}", is_client=True, is_provider=False)
    page, per_page = storage.clamp_page("2", "3")
    rows, total = storage.list_agents(session, page=page, per_page=per_page)
    assert total == 7 and len(rows) == 3
    # Clamping: garbage → defaults; per_page capped at 500; page floors at 1.
    assert storage.clamp_page("garbage", "999") == (1, 500)
    assert storage.clamp_page("0", "0") == (1, 1)
    # Past-the-end page is empty, not an error.
    rows, _ = storage.list_agents(session, page=99, per_page=10)
    assert rows == []


def test_stats_math_fixed_timestamps(session):
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)
    for hours_ago, outcome in [
        (1, "completed"), (2, "completed"), (30, "provider_failed"),
    ]:
        storage.log_request(
            session,
            action_id="a", agent_id="g", active_version_id=None,
            request_payload={}, outcome=outcome, created_at=now - timedelta(hours=hours_ago),
        )
    counts = storage.outcome_counts(session)
    assert counts == {"completed": 2, "provider_failed": 1}
    assert storage.requests_last_24h_at(session, now) == 2


def test_audit_writer_append_only_shape(session):
    row = audit(
        session, actor_type="admin", actor_id="admin:root", event="version.approved",
        target_type="action_version", target_id="v1", detail={"notes": "ok"},
    )
    assert row.event == "version.approved"
    events, total = storage.list_audit_events(session, target_type="action_version")
    assert total == 1 and events[0].id == row.id


def test_resolve_bearer(session, config):
    agent, key = storage.register_agent(session, name="acme", is_client=True, is_provider=False)
    ident = resolve_bearer(session, config, key)
    assert ident is not None and ident.kind == "agent" and ident.agent.id == agent.id
    # Admin token from config resolves as admin.
    ident = resolve_bearer(session, config, config.admins[0].token)
    assert ident is not None and ident.kind == "admin" and ident.admin.username == "admin"
    # Unknown / garbage / wrong-namespace tokens → None (→ 401 everywhere).
    assert resolve_bearer(session, config, "dmz_nope" + "x" * 40) is None
    assert resolve_bearer(session, config, "garbage") is None
    assert resolve_bearer(session, config, "dmzadm_wrong" + "x" * 40) is None
    # Disabled agent → None.
    agent.disabled = True
    assert resolve_bearer(session, config, key) is None
    agent.disabled = False
    # Prefix namespaces don't collide: an agent key never resolves as admin and
    # vice versa, even with identical suffixes.
    assert resolve_bearer(session, config, AGENT_PREFIX + "collide") is None
    assert resolve_bearer(session, config, ADMIN_PREFIX + "collide") is None
