# REST API v2 — Agent-Facing Interface

> Product requirements for the LLM DMZ's agent-facing REST API. This document is self-contained: an agent (or its model) should be able to use the DMZ entirely from this contract plus the live `/v2/skill` document. Companion documents: `system-prd-v2.md` (overall system), `schemas-v2.md` (submission format and validation detail), `infra-v2.md` (stack/deployment), `webui-v2.md` (admin console).

## Overview & goals

The DMZ exposes one REST interface for all agent traffic. Clients browse the action directory, enroll in actions, and invoke them synchronously — every call returns a final result (or a specific, self-correctable rejection) in one round trip. Providers create actions, submit new versions, and withdraw actions. Administrators act through the admin console, not this API.

Goals:

- **Bootstrappable** — an agent that has only a bearer key can learn everything else from `GET /v2/skill` and the endpoints it describes.
- **Resource-oriented** — `actions` is the single core collection; everything hangs off it.
- **Transparent failures** — when a request is rejected, the client is told exactly why (validation error or arbiter verdict, verbatim) so it can correct the request in its next attempt.
- **Synchronous** — no polling, no job IDs, no waiting on humans.

## Conventions

- **Base URL** — all endpoints are prefixed with `/v2/`.
- **Content** — JSON only; requests and responses are UTF-8 with `Content-Type: application/json`.
- **Authentication** — every request carries `Authorization: Bearer <key>`. The key identifies the agent and its capability flags (`is_client`, `is_provider`). Missing/unknown key → `401`; known key used for a role it doesn't hold → `403`.
- **Error envelope** — all error responses use one shape:

```json
{
  "error": {
    "code": "request_schema_invalid",
    "message": "Request payload failed validation against the action's request schema.",
    "detail": { ... }
  }
}
```

`code` is a stable machine-readable token; `message` is human-readable; `detail` carries structured context (e.g. JSON Schema errors, arbiter verdict) where available.

- **Status codes**

| Code | Meaning |
|---|---|
| `200` | Success (GET/PUT/DELETE) or invocation success |
| `201` | Resource created (action submitted, enrollment recorded) |
| `400` | Malformed request body / JSON parse error |
| `401` | Missing, unknown, or revoked bearer key |
| `403` | Authenticated agent lacks the required capability or ownership |
| `404` | Unknown action (also used for actions hidden from the caller) |
| `409` | Conflict — e.g. duplicate `id` on create, enrollment already requested |
| `422` | Semantically valid JSON that fails action-level validation (schema compilation, instructions) |
| `502` | Provider failure — dispatch retries exhausted without a valid response |

- **Error codes** (stable tokens used in `error.code`): `unauthorized`, `forbidden`, `not_found`, `malformed_json`, `duplicate_action`, `request_schema_invalid`, `arbiter_rejected`, `not_enrolled`, `provider_failed`, `already_enrolled`, `version_pending`.

## Endpoint reference

| Method & path | Role | Purpose |
|---|---|---|
| `GET /v2/skill` | any | Skill document for the agent's role(s) |
| `GET /v2/actions` | client / provider | Action directory (role-projected) |
| `POST /v2/actions` | provider | Create a new action (submit a schema package) |
| `GET /v2/actions/{id}` | client / owner | Action detail (projection depends on caller) |
| `PUT /v2/actions/{id}` | provider (owner) | Submit a new version of the action |
| `DELETE /v2/actions/{id}` | provider (owner) | Withdraw / deactivate the action |
| `GET /v2/actions/{id}/versions` | provider (owner) | Version history including superseded |
| `POST /v2/actions/{id}/invoke` | client | Invoke the action (synchronous) |
| `POST /v2/actions/{id}/enroll` | client | Request enrollment in the action |
| `GET /v2/actions/{id}/enroll` | client | Enrollment state for the calling client |

### GET /v2/skill

Returns the skill document appropriate to the authenticated agent: agents with `is_client` get the **client skill** (how to browse, enroll, invoke, and interpret rejections); agents with `is_provider` get the **provider skill** (how to create actions, submit versions, interpret states); agents with both flags get both documents in one response. The document is in a form an LLM agent can consume directly, and states the DMZ base URL and the caller's capabilities so an agent can bootstrap from this single call.

### GET /v2/actions

Lists all actions visible to the caller, each with its state relative to that caller.

- **Client projection** — every action in the directory, each annotated with the caller's enrollment state:
  - `available` — open, but no enrollment yet
  - `requested` — enrollment pending admin approval
  - `enrolled` — may be invoked now
  - `unavailable` — the action exists but is withdrawn, rejected, or otherwise not open (shown for directory completeness; invoking returns `not_found`)
- **Provider projection** — the caller's own actions only, each with its lifecycle state (`submitted`, `approved`, `rejected`, `withdrawn`) and the active version's number.

### POST /v2/actions

Provider submits a new action. The body is the schema package defined in `schemas-v2.md` (`id`, `description`, `request_schema`, `response_schema`, optional instruction fields). Automated checks run synchronously: duplicate `id` returns `409 duplicate_action`; schemas that fail to compile return `422` with detail. On success: `201` with the action in state `submitted`, awaiting admin approval. The action is not callable until an admin approves it (approval happens in the admin console, not this API).

### GET /v2/actions/{id}

Action detail. **Client view**: `id`, `description`, active version number, `client_instructions`, `request_schema` (what to send), `response_schema` (what comes back), and the caller's enrollment state. **Owner (provider) view**: additionally the full instruction fields, lifecycle state, and version summary. Actions the caller cannot see (withdrawn, never approved, not owned) return `404`.

### PUT /v2/actions/{id}

Owner submits a **new version**. The body is the same schema-package shape with updated contents; the `id` must match. There is no separate version-creation endpoint — versioning *is* PUT. Semantics:

- The new version is stored in state `submitted` (pending admin approval); the response reports `version_pending`.
- The currently active version **keeps serving** invoke calls until an admin approves the new version, at which point the swap is atomic: the old version becomes `superseded`, the new one `active`.
- Validation is identical to create (compile failures return `422`, malformed bodies `400`).

### DELETE /v2/actions/{id}

Owner **withdraws** the action. Withdraw is soft: the action immediately stops being invokeable and shows as `unavailable` in client directories, but all history — versions, request logs, enrollments — is retained for audit. Existing enrollments do not block the withdraw. Returns `200` with the action's new `withdrawn` state.

### GET /v2/actions/{id}/versions

Owner-only. Lists every version with number, lifecycle state (`submitted`, `active`, `superseded`, `rejected`), submission time, and the version's schema package. Superseded versions remain inspectable for audit.

### POST /v2/actions/{id}/invoke

Client invokes the action. Requires `enrolled` state (see enrollment below); otherwise `403 not_enrolled`. The body is the request payload, validated against the action's **active** version's `request_schema`. Processing is synchronous and single-round-trip; the three possible outcomes:

- **`200` success** — the validated provider response:

```json
{ "result": { ... }, "action": "crm_search", "version": 3 }
```

- **`4xx` rejection** — the request failed validation or arbitration. **The reason is returned transparently and verbatim** so the client's model can correct the request in its next attempt:
  - `request_schema_invalid` — `detail` carries the JSON Schema errors.
  - `arbiter_rejected` — `detail` carries the arbiter's verdict (`{ "approved": false, "reason": "..." }`) including its stated reason.
- **`502 provider_failed`** — dispatch was retried up to the configured limit (default 2) without producing a valid response. The client is told the provider failed, not why the provider's output was invalid; retrying the same request may succeed if the failure was transient.

Rejections are final for that request; there is no pending state and no human in the loop.

### POST /v2/actions/{id}/enroll

Client requests enrollment in the action. Creates an enrollment in state `requested`, awaiting admin approval (granted in the admin console). Responses: `201` with the enrollment state; `409 already_enrolled` if an enrollment already exists for this client and action (whether `requested` or `enrolled`); `404` if the action is not visible/enrollable. Enrollment applies to the action, not a version — approved enrollments carry forward across version swaps.

### GET /v2/actions/{id}/enroll

Returns the calling client's enrollment state for the action: `requested`, `enrolled`, or `404 not_found` when no enrollment exists (the action itself may still be `available`). Included fields: state, requested-at time, and (once enrolled) granted-at time.

## Provider visibility of invocations

Providers do **not** get an agent-facing endpoint listing invocations of their actions in this version. Invocation history (payloads, outcomes, retries) is recorded in the request log and visible to administrators in the console. Providers see the directory-level facts of their own actions (state, versions) via the endpoints above.

## Beyond the scope of this document

- **Provider dispatch protocols** (`completions`, `exec`, `post`) — how the DMZ calls provider endpoints, timeouts, and retry mechanics are specified in `dispatch-v2.md`.
- **Admin console routes** — approval, enrollment management, request log, and audit UI belong to `webui-v2.md`; this document defines only the agent-facing contract.
- **A2A / MCP front doors, streaming, webhooks, rate limiting** — REST request/response only in this version.
- **Skill document contents** — the `/v2/skill` endpoint's contract is defined here; the prose of the skill documents themselves is authored with the implementation.

