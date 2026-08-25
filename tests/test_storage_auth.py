"""T1.8 / T1.12: storage, keys, and auth unit tests (offline)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admz.core import storage
from admz.core.audit import audit
from admz.core.auth import resolve_bearer
from admz.core.keys import (
    ADMIN_PREFIX,
    AGENT_PREFIX,
    generate_admin_token,
    generate_agent_key,
    hash_key,
)
from admz.core.models import Base


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


def test_key_generation_prefixes_and_hashes():
    from admz.core.keys import (
        CHECKSUM_CHARS,
        CHECKSUMMED_BODY_CHARS,
        PAYLOAD_CHARS,
        key_checksum_status,
    )

    agent_key = generate_agent_key()
    admin_token = generate_admin_token()
    assert agent_key.startswith(AGENT_PREFIX)
    assert len(agent_key) == 20  # dmz_ + 16 (14 entropy + 2 checksum)
    assert len(agent_key) == len(AGENT_PREFIX) + CHECKSUMMED_BODY_CHARS
    assert len(agent_key) == len(AGENT_PREFIX) + PAYLOAD_CHARS + CHECKSUM_CHARS
    assert admin_token.startswith(ADMIN_PREFIX)
    assert key_checksum_status(agent_key) == "ok"
    assert key_checksum_status(admin_token) == "ok"
    assert hash_key(agent_key) != agent_key
    assert len(hash_key(agent_key)) == 64  # sha256 hex
    assert hash_key(agent_key) == hash_key(agent_key)


def test_key_checksum_rejects_typos_and_accepts_legacy():
    from admz.core.keys import (
        AGENT_PREFIX,
        PAYLOAD_CHARS,
        KeyChecksumError,
        assert_key_checksum,
        key_checksum_status,
    )

    key = generate_agent_key()
    body = key[len(AGENT_PREFIX) :]
    payload, check = body[:PAYLOAD_CHARS], body[PAYLOAD_CHARS:]
    i = 0
    while i + 1 < len(payload) and payload[i] == payload[i + 1]:
        i += 1
    transposed = payload[:i] + payload[i + 1] + payload[i] + payload[i + 2 :]
    bad = AGENT_PREFIX + transposed + check
    assert key_checksum_status(bad) == "invalid"
    with pytest.raises(KeyChecksumError):
        assert_key_checksum(bad)

    truncated = key[:-1]
    assert key_checksum_status(truncated) == "invalid"
    from admz.core.keys import LEGACY_UNCHECKED_BODY_CHARS

    legacy = AGENT_PREFIX + "A" * LEGACY_UNCHECKED_BODY_CHARS
    assert key_checksum_status(legacy) == "legacy"
    assert_key_checksum(legacy)  # does not raise
    assert key_checksum_status("garbage") == "other"
    # Config-file admin tokens are free-form length; don't checksum-reject them.
    from admz.core.keys import ADMIN_PREFIX

    assert key_checksum_status(ADMIN_PREFIX + "testtoken0000000000000000000000000") == "legacy"


def test_intermediate_43_plus_6_checksum_still_accepted():
    from admz.core.keys import (
        AGENT_PREFIX,
        KeyChecksumError,
        _checksum,
        assert_key_checksum,
        key_checksum_status,
    )

    payload = "C" * 43
    key = AGENT_PREFIX + payload + _checksum(payload, 6)
    assert key_checksum_status(key) == "ok"
    assert_key_checksum(key)
    assert key_checksum_status(AGENT_PREFIX + payload + "XXXXXX") == "invalid"
    with pytest.raises(KeyChecksumError):
        assert_key_checksum(AGENT_PREFIX + payload + "XXXXXX")


def test_configurable_payload_length():
    from admz.core.keys import (
        AGENT_PREFIX,
        CHECKSUM_CHARS,
        generate_agent_key,
        key_checksum_status,
    )

    for payload_chars in (14, 32, 64):
        key = generate_agent_key(payload_chars)
        body = key[len(AGENT_PREFIX) :]
        assert len(body) == payload_chars + CHECKSUM_CHARS
        assert key_checksum_status(key) == "ok"


def test_legacy_key_without_checksum_still_resolves(session, config):
    from admz.core.keys import AGENT_PREFIX, LEGACY_UNCHECKED_BODY_CHARS
    from admz.core.models import Agent

    legacy = AGENT_PREFIX + "B" * LEGACY_UNCHECKED_BODY_CHARS
    session.add(
        Agent(
            name="oldtimer",
            api_key_hash=hash_key(legacy),
            is_client=True,
            is_provider=False,
        )
    )
    session.flush()
    ident = resolve_bearer(session, config, legacy)
    assert ident is not None and ident.kind == "agent"
    assert ident.agent is not None and ident.agent.name == "oldtimer"


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
    from admz.core.models import Action, ActionVersion, Enrollment

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


def test_list_audit_events_actor_q_and_exclude(session):
    agent, _ = storage.register_agent(session, name="crm", is_client=True, is_provider=False)
    audit(
        session, actor_type="agent", actor_id=agent.id, event="request.invoked",
        target_type="action", target_id="crm_search",
    )
    audit(
        session, actor_type="admin", actor_id="admin", event="version.approved",
        target_type="action", target_id="crm_search", detail={"notes": ""},
    )
    session.flush()
    by_name, total = storage.list_audit_events(session, actor_q="crm")
    assert total == 1 and by_name[0].event == "request.invoked"
    by_admin, total = storage.list_audit_events(session, actor_q="admin")
    assert total == 1 and by_admin[0].actor_id == "admin"
    lifecycle, total = storage.list_audit_events(
        session, exclude_events=["request.invoked", "request.invoked"]
    )
    assert total == 1 and lifecycle[0].event == "version.approved"


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


def test_list_actions_state_filter_is_in_query_not_after_page(session):
    """Filtering after pagination made `total` disagree with the visible set."""
    from admz.core.models import Action

    owner, _ = storage.register_agent(
        session, name="provider", is_client=False, is_provider=True
    )
    session.add(Action(id="crm_add_note", owner_agent_id=owner.id, state="active"))
    session.add(Action(id="crm_search", owner_agent_id=owner.id, state="active"))
    session.add(Action(id="old_thing", owner_agent_id=owner.id, state="withdrawn"))
    session.commit()

    rows, total = storage.list_actions(session, page=1, per_page=1, state="active")
    assert total == 2
    assert len(rows) == 1
    assert rows[0].state == "active"

    rows, total = storage.list_actions(session, page=1, per_page=50, state="withdrawn")
    assert total == 1
    assert [a.id for a in rows] == ["old_thing"]

    rows, total = storage.list_actions(session, page=1, per_page=50, q="crm_search")
    assert total == 1
    assert rows[0].id == "crm_search"

    # `q` matches id, not the state column (state is a separate filter).
    rows, total = storage.list_actions(session, page=1, per_page=50, q="withdrawn")
    assert total == 0
