# Schemas & Arbiter Reference

This document describes the two halves of the DMZ's content-validation layer:

1. **Schema system** — the JSON Schema files in `schemas/`, the binding registry in `config/schemas.json`, and how they are loaded/validated by `dmz/schemas.py`.
2. **LLM Arbiter** — the request/response security checks in `dmz/arbiter.py`.

Every message crossing the DMZ passes through **both** layers: structural schema validation first, then LLM-based security arbitration. Anything that fails either layer is routed to the human review queue.

---

## 1. Schema System

### 1.1 File layout

```
schemas/                      # JSON Schema files (draft 2020-12)
├── crm_search_request.json
├── crm_search_response.json
├── crm_add_note_request.json
└── crm_add_note_response.json

config/schemas.json           # Schema registry / bindings
```

### 1.2 The registry: `config/schemas.json`

The registry maps a **schema ID** to everything needed to route and validate a message. Top level is a single key `schemas` holding a list of binding objects:

```json
{
  "schemas": [
    {
      "id": "crm_search",
      "description": "Search CRM contacts by name or company",
      "request_schema": "schemas/crm_search_request.json",
      "response_schema": "schemas/crm_search_response.json",
      "requestor_id": "ext_agent",
      "requestee_id": "int_agent",
      "requestee_a2a_url": "http://127.0.0.1:5001"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Unique schema ID used by callers (the `schema_id` on API requests and in arbiter prompts). |
| `description` | Human-readable summary of the operation. |
| `request_schema` | Relative path (from repo root) to the JSON Schema for the *request* payload. |
| `response_schema` | Relative path to the JSON Schema for the *response* payload. |
| `requestor_id` | Agent ID allowed to originate requests for this binding (from `config/agents.json`). |
| `requestee_id` | Agent ID of the trusted internal handler. |
| `requestee_a2a_url` | A2A URL of the internal agent that fulfills the request (used by the A2A gateway). |

### 1.3 Schema file format

Schema files are standard **JSON Schema draft 2020-12** documents. The repo uses this convention:

- **Naming:** `<operation>_request.json` and `<operation>_response.json` pairs.
- **Top-level keys:** `$schema`, `$id`, `title`, `description`, plus normal JSON Schema body (`type`, `properties`, `required`, `additionalProperties`, etc.).
- **Strictness:** request/response schemas use `"additionalProperties": false` so no undeclared fields can pass through the DMZ.
- **Sub-objects** are defined inline in `$defs` and referenced via `$ref` (e.g. the `contact` object reused by both CRM response schemas).

Example (`schemas/crm_search_request.json`) — note the `anyOf` requiring at least one search key:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://llmdmz.example/schemas/crm-search-request.json",
  "title": "CRM Search Request",
  "type": "object",
  "properties": {
    "name":     { "type": "string", "minLength": 1 },
    "company":  { "type": "string", "minLength": 1 }
  },
  "anyOf": [ { "required": ["name"] }, { "required": ["company"] } ],
  "additionalProperties": false
}
```

Current schema pairs:

| Schema ID | Request | Response | Notes |
|---|---|---|---|
| `crm_search` | `name` and/or `company` (`anyOf`) | `records`: array of `contact` | Empty array allowed when nothing matches |
| `crm_add_note` | `contact_id`, `note` (both required) | `record`: a single `contact` | Response is the updated record |

The shared `contact` definition (`$defs.contact`) requires `id`, `name`, `email`, `company`, `phone`, `status` (`enum: active | lead | churned`), and `notes`, with no additional properties.

### 1.4 How validation works (`dmz/schemas.py`)

`SchemaRegistry` loads all bindings at construction time and, for each one:

1. Reads the request and response schema JSON files.
2. Builds Pydantic models from each schema using `dydantic.create_model_from_schema`.
3. Stores everything in an immutable `SchemaPair` (binding + raw schemas + models).

`validate_request(schema_id, payload)` / `validate_response(schema_id, payload)` run **two-pass validation**:

1. **`jsonschema.validate`** against the raw JSON Schema (catches structural violations).
2. **Pydantic `model_validate`** against the generated model (catches type-coercion/format issues; errors are re-raised as `ValueError`).

Unknown `schema_id` values raise `KeyError`. The registry also exposes `list_schemas()` and `list_schemas_detail()` (used by the admin UI / API).

---

## 2. LLM Arbiter (`dmz/arbiter.py`)

After structural validation passes, the arbiter performs semantic security checks with an LLM.

### 2.1 Configuration

| Env var | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | **Required.** API key for OpenRouter (checked on every call). | — |
| `ARBITER_MODEL` | LiteLLM model string. | `openrouter/openai/gpt-oss-120b:free` |

Inference is done via `litellm.completion`; all calls are logged through `llm_logging.get_logger("arbiter")`.

### 2.2 Request check — `check_request(schema_id, payload)`

Screens the **incoming request** from the untrusted external agent for malicious intent:

- prompt injection / jailbreak attempts
- attempts to bypass schema constraints with hidden instructions
- requests for unrelated sensitive operations
- social engineering or coercion aimed at downstream systems

The prompt embeds the `schema_id` and the pretty-printed payload, and instructs the model to reply with **only** valid JSON.

### 2.3 Response check — `check_response(schema_id, request_payload, response_payload, response_schema=None, operation_description=None)`

Screens the **outgoing response** from the trusted internal agent for data exfiltration:

- private data beyond what the request asked for
- bulk dumps of unrelated customer records
- credentials, internal notes, or fields not justified by the request
- steganographic / encoded leakage

The prompt embeds the original request alongside the response. If supplied, the declared `response_schema` (and optional `operation_description`) are injected just before the "Reply with ONLY valid JSON" instruction — the prompt explicitly tells the arbiter to **approve schema-conformant responses** unless there is clear evidence of extra sensitive data. This reduces false positives on legitimate responses (e.g. a CRM search legitimately returning contact records).

### 2.4 Verdict parsing

The model's reply is parsed by `_parse_verdict`:

1. Strip whitespace and try `json.loads` directly.
2. On failure, regex-extract the first `{...}` block (dot-all) and parse that.
3. If neither works, `ValueError` is raised (treated as a failed check → review queue).

Both checks return a verdict dict:

```json
{ "approved": true, "reason": "Payload matches declared schema; no anomalies." }
```

`approved` is coerced to bool; a missing `reason` defaults to `"No reason provided"`.

### 2.5 Where it fits in the pipeline

```
external agent
   │ request
   ▼
schema validation ──fail──► review queue
   │ pass
   ▼
arbiter.check_request ──reject/error──► review queue
   │ approved
   ▼
internal agent (requestee queue / A2A)
   │ response
   ▼
schema validation ──fail──► review queue
   │ pass
   ▼
arbiter.check_response ──reject/error──► review queue
   │ approved
   ▼
response queue → external agent
```

> Note (see `TODO.md`): the arbiter prompts are currently hard-coded constants (`REQUEST_CHECK_PROMPT` / `RESPONSE_CHECK_PROMPT`) in `dmz/arbiter.py`; making them configurable is a planned improvement.
