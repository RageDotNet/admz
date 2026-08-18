# System PRD v2 — The LLM DMZ

> Product requirements for the next version of the LLM DMZ. This document is self-contained and describes the overall system: what it does, who uses it, and the behaviors it must implement. Companion documents (referenced for deeper detail, not required reading): `infra-v2.md` (technology stack, deployment), `schemas-v2.md` (schema registry and validation detail), and a future `webui-v2.md` (admin console UI detail).

## 1. Overview & goals

The DMZ is a **directory-driven broker** that sits between untrusted LLM agents. Providers register *actions* (validated API capabilities); clients discover those actions, request access, and invoke them. Every request and response passing through the DMZ is validated against a JSON Schema and judged by an LLM security arbiter before reaching the other side.

Goals for this version:

- **Synchronous processing** — every request is handled in one round trip; the client gets a final answer (result, or a specific rejection) immediately. There is no manual review or quarantine state for individual requests.
- **Self-service directory** — providers manage their own actions via a REST API; clients browse the directory and request access; administrators approve actions, action updates, and access requests.
- **Governance by approval, not interception** — human review moves upstream: actions and access are approved before any traffic flows, so live traffic needs no human gate.
- **Portability** — SQLite is the default database, but the system is structured so switching to MariaDB, PostgreSQL, etc. is a configuration change, not a code change.

### MVP scope

One synchronous REST application: agent identity, action directory with versioning and approval, access control, validated request/response brokering with arbitration and retries, request logging, and an admin webui.

### Non-goals (this version)

- **A2A and MCP endpoints** — REST only for now; additional front-door protocols may be revisited later.
- **Long-running work conventions** — providers that need async processing should implement their own queue/tracking-ID/polling pattern or push results to a client's own action. This is a provider implementation detail and may later be documented as a best practice, but it is not part of what the DMZ builds.
- **Webui detail** — the admin console's page-level design lives in the future `webui-v2.md`; this PRD defines only what the console must let administrators *do*.

## 2. Terms

| Term | Definition |
|---|---|
| **Action** | An API endpoint that a provider serves and other agents can call: a named capability with a request schema, a response schema, and arbiter/model-facing instructions |
| **Agent** | Any registered participant — a client, a provider, or both. Every agent has a bearer key |
| **Client** | An agent that calls actions |
| **Provider** | An agent that registers and responds on actions |
| **Admin** | A human administrator (multiple allowed; defined in the config file) |
| **Directory** | The catalog of all registered actions, filterable per client by access state |
| **Access request** | A client's request for permission to invoke a specific action |
| **Action version** | A specific revision of an action's definition; only one version of an action is active at a time |

## 3. System components

- **Single Flask application** (REST only). All processing is synchronous within the request cycle — there is no worker/queue pipeline. This keeps the mental model simple: one request in, one response out.
- **Relational storage** (SQLite by default) accessed through an ORM. Requirements:
  - All database access goes through the ORM and the storage module's interface — no raw, dialect-specific SQL in application code.
  - The connection is a configurable DSN (e.g. `DMZ_DATABASE_URL`), defaulting to a SQLite file, so MariaDB/PostgreSQL/etc. are drop-in via configuration.
  - Schema changes go through migrations; nothing is created ad hoc at runtime.
- **Admin webui** — server-rendered console mounted under `/admin` in the same application (detail spec in the future `webui-v2.md`).
- **LLM stack** — all model calls (arbiter, any internal agents) go through a unified LLM gateway routed via OpenRouter.

## 4. Configuration

- **YAML config file(s)** hold *system* configuration:
  - Server settings (host, port, public URL, debug)
  - Database DSN
  - LLM settings (API key reference, arbiter model)
  - Retry policy (provider response retry count; default 2)
  - **Admin accounts** — multiple admins, each with a username/password and/or a bearer token
- Configuration is validated at startup; malformed config fails fast.
- **Agents are *not* in the config file.** Agent registrations (clients, providers) live in the database and are created/managed through the admin webui, which issues each agent its bearer key.
- Secrets may come from environment variables injected at deploy time; the config file references or supplements them.

## 5. Agent & identity management

- Agents are registered by an **administrator** through the webui. On registration the system generates a **bearer key**; the admin delivers it to the agent owner out of band.
- An agent has a role: **client**, **provider**, or **both**. Roles are stored as **independent capability flags** (e.g. `is_client`, `is_provider`) — "both" is not a stored value but simply the state where both flags are true. Every endpoint checks only the capability it requires (invoking actions requires client capability; registering actions requires provider capability) — there is no `role == "both"`-style conditional anywhere. This keeps roles non-brittle: new capabilities become new flags, and an admin can revoke one capability (e.g. provider duty) independently of the other.
- **Providers have exactly one endpoint configuration** (endpoint-per-provider, not endpoint-per-action). All of a provider's actions are served through that endpoint. The endpoint specifies:
  - **Protocol** — how the DMZ invokes the provider. Supported protocols:
    - **`completions`** — an LLM completions endpoint; config includes the URL to hit and an array of header/value pairs to send.
    - **`exec`** — a local program; the DMZ opens a pipe to the configured program, writes the request input to stdin, and reads the response from stdout until the program exits.
    - **`post`** — a plain HTTP endpoint; config includes a URL and headers; the DMZ posts the input and reads the output.
  - **Protocol config** — the protocol-specific settings above (URL, headers, program).
- Keys can be revoked/disabled by an admin, immediately cutting off the agent.
- Admins authenticate with username/password (webui) or bearer token (API).

## 6. Action directory

### 6.1 Action lifecycle & versioning

- Providers manage their actions via a **REST CRUD API** (authenticated with their bearer key).
- An action version's lifecycle: **`submitted` → `active`** (approved by an admin) **or `rejected`**.
- **Versioning rule**: when a provider edits an action, a *new version* is created in `submitted` state; the previously approved version remains active and callable until the new version is approved. Approval swaps the active version atomically.
- **Deletion is immediate** but soft: deleting an action deactivates it — it disappears from discovery and becomes non-invokable — while its history and logs are retained.
- Each action version carries (per the schema registry design in `schemas-v2.md`): a JSON request schema, a JSON response schema (draft 2020-12), per-schema **arbiter instructions**, and **client instructions** (what calling agents see, e.g. how to format inputs) and **provider instructions** (what the provider should know about serving the action). Schema documents themselves remain JSON — they are wire-format contracts.

### 6.2 Client directory views

A client can query the directory and see actions grouped by its relationship to them:

- **Available** — active actions it has not yet requested access to
- **Pending** — actions it has requested access to that are not yet approved
- **Rejected** — actions where its access request was rejected
- **Approved** — actions it is approved to invoke

### 6.3 Access requests

- A client requests access to an action via the REST API.
- Administrators see and manage access requests in the webui: approve or reject each one.
- Only approved clients may invoke an action; other callers receive an authorization error.

### 6.4 Admin directory view

Admins see the full directory: all actions, all versions, lifecycle states, owning providers, and per-action access grants.

## 7. Request flow (synchronous)

One request, one response — no intermediate states a client must poll:

1. **Authenticate** — the caller presents its bearer key; the agent and its role are resolved.
2. **Authorize** — the client must hold approved access to the requested action.
3. **Request validation** — the request payload is validated against the action's active request schema, then judged by the LLM arbiter using that action's arbiter instructions. Any failure → **immediate rejection** to the client with a specific error.
4. **Dispatch** — the DMZ invokes the provider's endpoint using the provider's configured protocol (`completions`, `exec`, or `post`) with the validated input.
5. **Response validation with retries** — the provider's response is validated against the action's response schema and judged by the arbiter. On failure, dispatch + validation is **retried up to the configured limit (default 2 retries)**. If all attempts fail, the client receives a "provider failed to provide a valid response" error.
6. **Deliver** — the validated response is returned to the client immediately.
7. **Log** — the request (payloads, validation/arbitration outcomes, retries, final result) is persisted for admin review. Logging is observational; nothing waits on a human.

## 8. `/skill` endpoints

The DMZ exposes a `/skill` endpoint with **two skill documents**:

- **Client skill** — machine/model-facing instructions for client agents: how to authenticate, browse the directory, interpret access states, request access, and invoke actions (including the meaning of immediate rejections and provider-failure responses).
- **Provider skill** — instructions for provider agents: how to authenticate, register and version actions, submit schemas and instructions, interpret approval states, and what the DMZ guarantees when invoking their endpoint.

Skills are returned in a form an LLM agent can consume directly (the point being that an agent can bootstrap its use of the DMZ from the skill alone).

## 9. Admin capabilities

Administrators, via the webui (and API where noted):

- Register agents, issue/revoke bearer keys, assign roles, configure provider endpoints
- Approve or reject **new action versions** (activating them on approval)
- Manage **client access requests** (approve/reject)
- Browse the full **action directory** with version history
- Browse **request logs** — all traffic with validation/arbitration outcomes
- Manage their own credentials as defined in the config file

## 10. Non-functional requirements

- **Offline test suite** — the full test suite runs with no network access (LLM and provider calls mocked).
- **Startup validation** — config parsing and validation happen at boot; bad config crashes loudly rather than misbehaving at runtime.
- **Portability** — no SQLite-specific constructs in application code; the ORM and DSN-config keep MariaDB/PostgreSQL switchable.
- **Auditability** — every request, decision, and state change (approvals, access grants, agent registration) is persisted with enough context for after-the-fact review.
- **Immediate feedback** — no code path leaves a client waiting on human action; the only human gates are upstream (action/access approval).

## 11. Beyond the scope of this document

- **A2A and MCP front doors** — REST is the only interface in this version; additional protocols may be added later.
- **Long-running work conventions** — tracking IDs, polling endpoints, and result push-back are provider implementation choices; a future best-practices document may describe patterns.
- **Webui design detail** — page structure, interactions, and console UX belong to the future `webui-v2.md`.
- **Infrastructure detail** — packaging, Docker/deployment, migrations, config file paths, and dev workflows are specified in `infra-v2.md`.
- **Schema registry internals** — submission validation rules, instruction-field semantics, and registry behavior are specified in `schemas-v2.md`.


