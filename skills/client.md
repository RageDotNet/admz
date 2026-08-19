# LLM DMZ — Client Skill

You are interacting with the **LLM DMZ**, a broker that lets you (an LLM agent)
discover and invoke capabilities ("actions") provided by trusted internal
providers. This document tells you everything you need to use it.

## Authentication

Every request must carry your bearer key:

```
Authorization: Bearer dmz_...
```

Missing or unknown keys return `401 unauthorized`. Role mismatches return
`403 forbidden`.

## Workflow

1. **Discover** — `GET /v2/actions` lists the action directory. Each item shows
   `id`, `description`, your `enrollment` state, and the active `version`.
   Optional query parameters: `?q=<substring>` (matches `id`/`description`),
   `?enrollment=available|requested|enrolled|unavailable`, `?page=`,
   `?per_page=` (max 500).
2. **Inspect** — `GET /v2/actions/{id}` returns the action detail: what the
   request payload must look like (`request_schema`, `client_instructions`)
   and what the response will contain (`response_schema`).
3. **Enroll** — `POST /v2/actions/{id}/enroll` requests enrollment. It returns
   `201` with state `requested`; an administrator grants it. Check the state
   with `GET /v2/actions/{id}/enroll`. Already requested/enrolled → `409`.
4. **Invoke** — `POST /v2/actions/{id}/invoke` with the request payload as the
   JSON body. Requires enrollment (`enrolled`), otherwise `403 not_enrolled`.
   On success you receive `{"result": {...}, "action": "...", "version": N}`.

## Rejection codes (self-correctable)

Every error response has the shape `{"error": {"code", "message", "detail"}}`.
When your invocation is rejected, read `detail` carefully and correct the
request in your next attempt:

- `request_schema_invalid` — your payload failed JSON Schema validation;
  `detail` lists the exact schema errors.
- `arbiter_rejected` — the DMZ's security arbiter flagged your payload;
  `detail` carries its verdict and stated reason, verbatim. Remove any
  instructions, hidden prompts, or out-of-scope content from data fields.
- `not_enrolled` — you must enroll and be granted first.
- `already_enrolled`, `not_found`, `forbidden`, `unauthorized`,
  `malformed_json`, `duplicate_action`, `version_pending` — lifecycle errors.

## Provider-side outcomes

- `502 provider_failed` — the provider could not produce a valid response
  after retries. You may retry the same request.
- `503 arbiter_unavailable` — the security check could not run. Retry.
- `500 internal_error` — operator fault; do not retry.

## Timeouts

Invocations are synchronous and may legitimately take **several minutes**
(up to ~9 minutes worst case). Do not time out early; wait for the response.
