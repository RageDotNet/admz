"""Schema registry: submission field validation + JSON Schema compilation (T2.1/T2.2).

Implements `schemas-v2.md`: required fields (id, description, request_schema,
response_schema), optional instruction fields, and instruction-field rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from dydantic import create_model_from_schema as generate_model

REQUIRED_FIELDS = ("id", "description", "request_schema", "response_schema")
OPTIONAL_INSTRUCTION_FIELDS = (
    "request_arbiter_instructions",
    "response_arbiter_instructions",
    "client_instructions",
    "provider_instructions",
)
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS + OPTIONAL_INSTRUCTION_FIELDS)

# IDs become URL path segments and directory keys â€” keep them conservative.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,254}$")

MAX_DESCRIPTION_LEN = 5000
MAX_INSTRUCTION_LEN = 5000


@dataclass
class ValidationIssue:
    field: str
    message: str


@dataclass
class SubmissionValidation:
    """Result of validating a schema-package submission body."""

    ok: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized: dict[str, Any] | None = None

    def fail(self, fld: str, message: str) -> None:
        self.ok = False
        self.issues.append(ValidationIssue(field=fld, message=message))

    def as_detail(self) -> dict[str, Any]:
        return {"issues": [{"field": i.field, "message": i.message} for i in self.issues]}


def validate_submission(body: Any) -> SubmissionValidation:
    """Field-level validation of a POST/PUT schema-package body (schemas-v2.md).

    Returns a normalized payload dict (only the allowed fields, instruction
    fields defaulted to empty strings) on success.
    """
    result = SubmissionValidation()
    if not isinstance(body, dict):
        result.fail("$body", "Submission body must be a JSON object.")
        return result

    for fld in REQUIRED_FIELDS:
        if fld not in body:
            result.fail(fld, "Required field is missing.")

    action_id = body.get("id")
    if isinstance(action_id, str) and not ID_PATTERN.match(action_id):
        result.fail(
            "id",
            "Action id must be lowercase letters/digits/underscores, starting with a letter.",
        )

    description = body.get("description")
    if description is not None and (not isinstance(description, str) or not description.strip()):
        result.fail("description", "Description must be a non-empty string.")
    elif isinstance(description, str) and len(description) > MAX_DESCRIPTION_LEN:
        result.fail("description", f"Description exceeds {MAX_DESCRIPTION_LEN} characters.")

    for schema_field in ("request_schema", "response_schema"):
        schema = body.get(schema_field)
        if schema is None:
            continue  # missing flagged above
        if not isinstance(schema, dict):
            result.fail(schema_field, "Must be a JSON Schema object.")
        elif schema.get("type") != "object":
            result.fail(schema_field, "Top-level schema must have \"type\": \"object\".")

    # Instruction fields: optional strings (max length keeps prompts reviewable).
    for fld in OPTIONAL_INSTRUCTION_FIELDS:
        value = body.get(fld)
        if value is None:
            continue
        if not isinstance(value, str):
            result.fail(fld, "Instruction fields must be strings.")
        elif len(value) > MAX_INSTRUCTION_LEN:
            result.fail(fld, f"Instruction field exceeds {MAX_INSTRUCTION_LEN} characters.")

    unknown = set(body) - ALLOWED_FIELDS
    if unknown:
        result.fail("$body", f"Unknown fields are not allowed: {sorted(unknown)}.")

    if not result.ok:
        return result

    result.normalized = {
        "id": action_id,
        "description": description,
        "request_schema": body["request_schema"],
        "response_schema": body["response_schema"],
        **{fld: body.get(fld, "") for fld in OPTIONAL_INSTRUCTION_FIELDS},
    }
    return result



def compile_schemas(submission: dict[str, Any]) -> list[ValidationIssue]:
    """Compile request/response schemas with jsonschema + dydantic (422 on failure).

    Returns a list of issues; empty means the schemas are usable at runtime
    (validate structurally with jsonschema and generate a pydantic model via
    dydantic, per schemas-v2.md "Runtime Validation" step 1).
    """
    issues: list[ValidationIssue] = []
    for schema_field in ("request_schema", "response_schema"):
        schema = submission[schema_field]
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            issues.append(
                ValidationIssue(field=schema_field, message=f"Invalid JSON Schema: {exc.message}")
            )
            continue
        try:
            generate_model(schema)
        except Exception as exc:  # noqa: BLE001 â€” dydantic surfaces varied pydantic errors
            issues.append(
                ValidationIssue(
                    field=schema_field, message=f"Schema failed to compile to a model: {exc}"
                )
            )
    return issues


def validate_payload(schema: dict[str, Any], payload: Any) -> list[str]:
    """Runtime structural validation of an invoke payload; returns error strings."""
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in sorted(validator.iter_errors(payload), key=lambda e: e.path)]


