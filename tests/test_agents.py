"""Tests for dmz.agents."""

from __future__ import annotations

import pytest

from dmz.agents import AgentRegistry, AuthError


@pytest.fixture
def registry() -> AgentRegistry:
    return AgentRegistry()


def test_authenticate_requestor(registry: AgentRegistry) -> None:
    ctx = registry.authenticate("ext_agent", "ext-dev-key-change-me")
    assert ctx.agent_id == "ext_agent"
    assert ctx.role == "requestor"


def test_authenticate_missing_credentials(registry: AgentRegistry) -> None:
    with pytest.raises(AuthError, match="Missing"):
        registry.authenticate(None, None)


def test_authenticate_invalid_key(registry: AgentRegistry) -> None:
    with pytest.raises(AuthError, match="Invalid"):
        registry.authenticate("ext_agent", "wrong-key")


def test_require_role_success(registry: AgentRegistry) -> None:
    ctx = registry.authenticate("int_agent", "int-dev-key-change-me")
    registry.require_role(ctx, "requestee")


def test_require_role_failure(registry: AgentRegistry) -> None:
    ctx = registry.authenticate("ext_agent", "ext-dev-key-change-me")
    with pytest.raises(AuthError, match="not permitted"):
        registry.require_role(ctx, "requestee")
