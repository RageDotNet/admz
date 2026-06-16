"""Schema registry using dydantic and jsonschema."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from dydantic import create_model_from_schema
from pydantic import BaseModel, ValidationError

from dmz.config import SchemaBinding, load_schema_bindings


@dataclass(frozen=True)
class SchemaPair:
    binding: SchemaBinding
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    request_model: type[BaseModel]
    response_model: type[BaseModel]


class SchemaRegistry:
    def __init__(self, bindings: dict[str, SchemaBinding] | None = None) -> None:
        self._bindings = bindings or load_schema_bindings()
        self._pairs: dict[str, SchemaPair] = {}
        for schema_id, binding in self._bindings.items():
            self._pairs[schema_id] = self._load_pair(binding)

    def _load_schema_file(self, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _load_pair(self, binding: SchemaBinding) -> SchemaPair:
        request_schema = self._load_schema_file(binding.request_schema_path)
        response_schema = self._load_schema_file(binding.response_schema_path)
        return SchemaPair(
            binding=binding,
            request_schema=request_schema,
            response_schema=response_schema,
            request_model=create_model_from_schema(request_schema),
            response_model=create_model_from_schema(response_schema),
        )

    def get(self, schema_id: str) -> SchemaPair:
        pair = self._pairs.get(schema_id)
        if pair is None:
            raise KeyError(f"Unknown schema_id: {schema_id}")
        return pair

    def list_schemas(self) -> list[dict[str, str]]:
        return [
            {
                "id": pair.binding.id,
                "description": pair.binding.description,
                "requestor_id": pair.binding.requestor_id,
                "requestee_id": pair.binding.requestee_id,
            }
            for pair in self._pairs.values()
        ]

    def validate_request(self, schema_id: str, payload: dict[str, Any]) -> None:
        pair = self.get(schema_id)
        jsonschema.validate(payload, pair.request_schema)
        try:
            pair.request_model.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def validate_response(self, schema_id: str, payload: dict[str, Any]) -> None:
        pair = self.get(schema_id)
        jsonschema.validate(payload, pair.response_schema)
        try:
            pair.response_model.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
