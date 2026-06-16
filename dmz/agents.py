"""Agent authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass

from dmz.config import Agent, load_agents


@dataclass(frozen=True)
class AuthContext:
    agent_id: str
    role: str


class AuthError(Exception):
    pass


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = load_agents()

    def authenticate(self, agent_id: str | None, agent_key: str | None) -> AuthContext:
        if not agent_id or not agent_key:
            raise AuthError("Missing agent credentials")
        agent = self._agents.get(agent_id)
        if agent is None or agent.key != agent_key:
            raise AuthError("Invalid agent credentials")
        return AuthContext(agent_id=agent.id, role=agent.role)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def require_role(self, context: AuthContext, *roles: str) -> None:
        if context.role not in roles:
            raise AuthError(f"Agent role '{context.role}' is not permitted for this action")
