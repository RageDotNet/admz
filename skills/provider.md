# Agent DMZ — Provider Skill

You are an LLM agent acting as a **provider** on the **Agent DMZ**: you publish
capabilities ("actions") that client agents may discover and invoke. This
document describes how.

## Authentication

```
Authorization: Bearer dmz_...
```

Your key must carry the provider capability. Submitting, versioning, and
withdrawing actions require ownership of the action in question. A key that
fails its checksum returns `401 key_checksum_invalid` (likely a typo —
re-read it from disk or your keystore).

## Publishing an action

`POST /v2/actions` with a single JSON document â€” the **schema package**:

```json
{
  "id": "crm_search",
  "description": "What it does and when a client should use it.",
  "request_schema": { ... JSON Schema draft 2020-12, type: object ... },
  "response_schema": { ... JSON Schema draft 2020-12, type: object ... },
  "request_arbiter_instructions": "optional â€” extra guidance for the request arbiter",
  "response_arbiter_instructions": "optional â€” extra guidance for the response arbiter",
  "client_instructions": "optional â€” how client models should build requests",
  "provider_instructions": "optional â€” how your model should build responses"
}
```

Rules: `id` is lowercase letters/digits/underscores starting with a letter;
top-level schemas must be `type: object`; unknown fields are rejected.
Schemas are compiled (JSON Schema validation **and** a Pydantic model) at
submission time â€” compile failures return `422`. A duplicate `id` returns
`409 duplicate_action`. On success the first version is stored in state
`submitted` and the action sits in `pending` until an administrator approves
it.

## Versioning

`PUT /v2/actions/{id}` with the same shape submits a **new version** (there is
no separate version endpoint â€” PUT *is* versioning):

- The new version is `submitted` (response reports `version_pending`).
- The currently active version keeps serving until an admin approves the new
  one; approval swaps atomically and the old version becomes `superseded`.
- Only one version may be pending at a time; a second PUT returns
  `409 version_pending`.
- Version numbers are monotonic. Rejected versions are terminal â€” resubmit
  as a new version.
- `GET /v2/actions/{id}/versions` lists full history including superseded
  versions.

## Withdrawal

`DELETE /v2/actions/{id}` soft-withdraws the action: it immediately stops
being invokeable and clients see it as `unavailable`, but all history
(versions, logs, enrollments) is retained. Withdrawal is reversible â€” submit
a new version via PUT; once it is approved the action returns to `active`
and existing enrollments become valid again automatically.

## Delivery configuration

How the DMZ calls you at invoke time is configured in the admin console
(not via this API): a delivery config on your agent or action version with
`type` (`completions`, `exec`, or `post`), the target endpoint/command, and
optional per-provider `retries` and `timeout` overrides of the system
defaults (`retries: 2`, `timeout: 180` seconds).

**Framing contract** (dispatch-v2.md): the DMZ forwards your request payload
verbatim and expects a response payload conforming to your `response_schema`.
For `post`, your endpoint receives the framed request body and configured
headers; return the payload as JSON. For `completions`, the DMZ sends a chat
completions body (`model`, system/user messages) and extracts the payload
from the reply. For `exec`, the DMZ runs your command with the framed request
on stdin and parses stdout as JSON. On any retry, the DMZ injects an error
report into the framing so you can correct the previous attempt.

## Visibility

You see your own actions' states and version history via the endpoints above.
Invocation history is visible only to administrators, not providers.
