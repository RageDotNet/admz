"""Load agent and schema configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).parent.parent / "config"
AGENTS_PATH = CONFIG_DIR / "agents.json"
SCHEMAS_PATH = CONFIG_DIR / "schemas.json"


@dataclass(frozen=True)
class Agent:
    id: str
    key: str
    role: str


@dataclass(frozen=True)
class SchemaBinding:
    id: str
    description: str
    request_schema_path: Path
    response_schema_path: Path
    requestor_id: str
    requestee_id: str
    requestee_a2a_url: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_agents(path: Path = AGENTS_PATH) -> dict[str, Agent]:
    data = _load_json(path)
    agents: dict[str, Agent] = {}
    for item in data["agents"]:
        agent = Agent(id=item["id"], key=item["key"], role=item["role"])
        agents[agent.id] = agent
    return agents


def load_schema_bindings(path: Path = SCHEMAS_PATH) -> dict[str, SchemaBinding]:
    root = path.parent.parent
    data = _load_json(path)
    bindings: dict[str, SchemaBinding] = {}
    for item in data["schemas"]:
        binding = SchemaBinding(
            id=item["id"],
            description=item["description"],
            request_schema_path=(root / item["request_schema"]).resolve(),
            response_schema_path=(root / item["response_schema"]).resolve(),
            requestor_id=item["requestor_id"],
            requestee_id=item["requestee_id"],
            requestee_a2a_url=item.get("requestee_a2a_url"),
        )
        bindings[binding.id] = binding
    return bindings
