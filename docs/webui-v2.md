# Admin Webui v2 — Product Requirements

> Product requirements for the admin console of the next version of the LLM DMZ. This document is self-contained: it specifies the console's pages, interactions, and technical requirements. Companion documents (referenced by name only): `system-prd-v2.md` (overall system), `infra-v2.md` (stack/deployment), `schemas-v2.md` (schema registry). The agent-facing REST API and skills are out of scope here.

## Overview & goals

The admin webui is the browser-based operational surface for the DMZ, mounted under `/admin` on the single Flask application. Human review in this system happens **upstream of traffic**: administrators approve actions, manage client access, and register agents — live requests are processed automatically. The console is where those human decisions happen, plus where administrators observe everything the system did.

### Goals

- Let an admin act on anything needing a decision (action versions, enrollment requests) in ≤ 2 clicks.
- Give a complete picture of any single **action** in one place: its definition/version history, which clients have access, and its invocation history.
- Give full visibility into agents, traffic, and state changes.
- Zero custom JavaScript — interactivity via Datastar; styling via Bootstrap 5 CSS; no npm/Node, no build step.

### Non-goals

- Agent-facing surfaces — directory browsing, enrollments, and action CRUD are REST API concerns; the console is admin-only.
- Real-time push — polling/refresh-on-interaction is sufficient.
- Per-admin permission tiers — all admins see and can do everything.
- Editing action definitions — admins approve or reject provider submissions; they do not author them.

## Users & authentication

| Aspect | Detail |
|---|---|
| Users | **Administrators** — multiple, defined in the system config file (username/password; some may also hold a bearer token for API access) |
| Webui auth | Username + password against config-defined accounts |
| Session | Flask signed-cookie session; login required before any console access |
| Unauthenticated behavior | Page requests redirect to login; fragment (Datastar) requests return `401` |
| API equivalence | **Every mutating `POST /admin/...` endpoint accepts the admin bearer token** — the full console decision surface (approvals, enrollment management, withdraw, agent/key management) is scriptable. Read routes (pages, fragments, log/audit views) are session-only |
| Auth precedence | If an `Authorization: Bearer` header is present it is validated first and exclusively; otherwise the admin session is checked. Neither present/valid → page routes redirect to login, fragment/mutating routes return `401` |

## Console structure

A single dashboard: a **stats bar** on top (agent count, action counts by state, pending enrollment requests, request totals by outcome) and **six tabs**. Tab switches and region updates are server-rendered fragments fetched via Datastar — no full page reloads.

| Tab | Purpose |
|---|---|
| **Dashboard/Directory** | All actions with all versions, lifecycle states, owning providers; entry point to per-action detail ("Directory tab & per-action detail") |
| **Enrollment requests** | Cross-action queue of pending client enrollment requests; approve/reject |
| **Agents** | Register agents, manage keys and capability flags, configure provider delivery (`dispatch-v2.md`) |
| **Request log** | All traffic with validation/arbitration outcomes, retries, and final results |
| **Audit trail** | Every state change: approvals, rejections, enrollments/revocations, agent registration/edits, key issuance/revocation |
| **Login** | (Not a tab — standalone page) |

## Directory tab & per-action detail

### Directory list

- All actions (active and withdrawn), with owner, current active version, state of any pending version, per-action enrollment count, and recent invocation count.
- Filterable by provider and state; sortable by name/recent activity; paginated (no hard row caps).
- Pending submitted versions are visually flagged; inline **Approve / Reject** actions are available directly from the list row.
- **Withdrawn** (soft-deleted) actions shown in a distinguishable style with their history retained. Withdraw is the provider-side operation (`DELETE /v2/actions/{id}`); the console reflects it and admins may also trigger it.

### Per-action detail (expanded inline or drill-in from a row)

The admin's "one place to understand one capability," with three sections:

1. **Definition & versions**
   - Current active version's full definition: description, request/response JSON Schemas, arbiter instructions, client/provider instructions.
   - **Version history**: every version with its state (`submitted`/`active`/`rejected`/`superseded`), submission and decision timestamps, deciding admin, and fields that changed relative to the prior version.
   - If a version is pending: full definition preview plus a diff against the currently active version, with **Approve / Reject** (optional notes). Approving atomically swaps the active version; the old one becomes `superseded`.
2. **Enrollment management** (enrollments for this action)
   - Enrolled clients (who/when approved).
   - Pending enrollment requests for this action, with inline **Approve / Reject**.
   - **Revoke** on any existing enrollment (immediate effect; the client's state returns to `available`).
   - **Admin-initiated enrollment**: proactively enroll a client that has not requested it (bootstrap for trusted clients).
3. **Invocation log** (requests pre-filtered to this action)
   - Recent invocations with outcomes (success / request-rejected / provider-failure), expandable to full payloads, validation/arbitration results, and retry counts (same detail rendering as the Request log tab).

**Consistency rule**: this detail view and the Enrollment-requests tab read the same underlying enrollment store — they are two views (per-action and cross-action queue), never separate state.

## Enrollment requests tab

- Queue of **pending** enrollment requests across all actions: client, action, provider, requested-at time, with Approve/Reject (optional notes).
- Also lists **recently decided** requests (approved/rejected with deciding admin and time) for context.
- Each row links to the action's detail view ("Per-action detail") and the client's agent record ("Agents tab").
- Row limits replaced by pagination + filter (by action, client, state).

## Agents tab

- **List** of registered agents: name, capability flags (`is_client`, `is_provider` — displayed as two independent toggles, not a role dropdown), key status (active/revoked), delivery configuration summary (protocol + endpoint/command), registration date.
- **Register agent**: name + capability flags; on save the system generates a **bearer key shown exactly once** with a copy affordance and a warning that it cannot be retrieved again.
- **Edit agent**: toggle capability flags independently (revoking one capability leaves the other intact), edit the delivery configuration (`dispatch-v2.md`): protocol (`completions`/`exec`/`post`), endpoint URL + headers or command, timeout, retry count, enable/disable the agent.
- **Revoke key**: immediately cuts off the agent; a new key can be issued later.
- Delivery-config forms validate per protocol (e.g. `exec` requires a command; `completions`/`post` require a URL) and accept timeout/retry values.

## Request log tab

- All requests, newest first: timestamp, client, action (linking to its detail view), provider, outcome (success / request-rejected / provider-failure), and which stage decided (request schema, request arbiter, response schema, response arbiter, retries exhausted).
- **Filter** by client, action, provider, outcome, and time range; **paginated** with counts.
- **Detail expansion** inline per row: full request and response payloads, schema validation errors (exact JSON Schema failures), arbiter verdicts and reasoning, per-attempt retry results, and final delivery status.
- No manual actions here — the log is observational; the only human gates are upstream approvals (Directory / Enrollment requests tabs).

## Audit trail tab

- Chronological record of every **state change** in the system:
  - Action lifecycle: version submitted / active / rejected / superseded; action withdrawn — with deciding admin and notes
  - Enrollment: request submitted / approved / rejected; enrollment revoked; admin-initiated enrollment
  - Agents: registered, capability flags changed, endpoint config changed, key issued / revoked, disabled
- Filterable by admin actor, object type, and time range; paginated.
- Rows link to the affected object (action detail, agent record) where it still exists.
- Entries are append-only from the console's perspective — the console never edits audit history.

## Routes (authoritative surface)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/admin/login` | Login page | — |
| POST | `/admin/login` | Authenticate (form or JSON) | — |
| GET | `/admin` | Dashboard shell (stats + tab container) | session |
| GET | `/admin/partials/stats` | Stats bar fragment | session |
| GET | `/admin/partials/directory` | Directory list fragment (filters/pagination via query params) | session |
| GET | `/admin/partials/action/<action_id>` | Per-action detail fragment (versions / access / invocations sub-sections) | session |
| POST | `/admin/action-version/<version_id>/approve` | Approve a submitted version | session / admin token |
| POST | `/admin/action-version/<version_id>/reject` | Reject a submitted version | session / admin token |
| POST | `/admin/action/<action_id>/withdraw` | Withdraw (soft-delete) an action | session / admin token |
| GET | `/admin/partials/enrollments` | Enrollment request queue fragment | session |
| POST | `/admin/enrollment/<request_id>/approve` | Approve an enrollment request | session / admin token |
| POST | `/admin/enrollment/<request_id>/reject` | Reject an enrollment request | session / admin token |
| POST | `/admin/action/<action_id>/enroll` | Admin-initiated enrollment (client + action) | session / admin token |
| POST | `/admin/enrollment/<enrollment_id>/revoke` | Revoke an existing enrollment | session / admin token |
| POST | `/admin/enrollment/<enrollment_id>/reset` | Reset a rejected enrollment, allowing the client to re-request | session / admin token |
| GET | `/admin/partials/agents` | Agent list fragment | session |
| POST | `/admin/agents` | Register agent (returns key once) | session |
| GET/POST | `/admin/agents/<agent_id>` | View / edit agent (flags, endpoint, enable/disable) | session |
| POST | `/admin/agents/<agent_id>/revoke-key` | Revoke bearer key | session |
| POST | `/admin/agents/<agent_id>/new-key` | Issue a replacement key (shown once) | session |
| GET | `/admin/partials/log` | Request log fragment (filters/pagination) | session |
| GET | `/admin/partials/request/<request_id>` | Request detail fragment | session |
| GET | `/admin/partials/audit` | Audit trail fragment (filters/pagination) | session |

Action endpoints that mutate state return **multi-patch responses** (e.g. affected list + stats bar in one Datastar response) so the UI updates without a separate fetch.

## UX principles

- **No custom JavaScript.** Tab switching, detail expansion, filters, pagination, and action submissions are server-rendered HTML fragments orchestrated by Datastar attributes.
- **Zero-build CSS.** Styling via Bootstrap 5 utility/component classes from the vendored stylesheet; no bundler, no CSS pipeline.
- **Server-rendered everything.** The server owns all rendering, including expanded rows and post-action refreshes; templates are the single source of UI truth.
- **Inline detail.** Details expand in place under the selected row rather than navigating away.
- **Immediate feedback.** Every decision updates the affected list and stats in the same response; nothing requires a manual refresh after acting.
- **Reveal-once secrets.** Bearer keys appear exactly once at issuance, with an explicit warning; they are never re-displayed.

## Technical design

- **Mounting**: the console is registered on the single Flask application under `/admin` at startup; it shares the app's storage, agent, and registry layers, so the console is always consistent with API state.
- **Auth guard**: a decorator checks admin auth — `Authorization: Bearer <admin-token>` first (required for token-based mutation), otherwise the admin session; page routes redirect to login, fragment routes return `401`. Mutating endpoints accept either, so the full decision surface is automatable.
- **Data**: all content comes from the shared storage layer (agents, actions/versions, enrollments, request log, audit events) via the same queries the API uses — the console never keeps its own copy of state.
- **Key handling**: bearer keys are generated server-side and stored only as hashes; the plaintext is returned exactly once (registration or re-issue).
- **Templates**: Jinja2 templates ship as package data (dashboard shell, login, tab partials, macros for shared row/detail rendering).
- **Logging**: all console actions are logged and also recorded as audit events ("Audit trail" tab).
- **Pagination/filtering**: list endpoints accept query parameters (page, filters) and enforce sane page sizes server-side — no unbounded queries.

## Success criteria

- Any pending action version or enrollment request can be resolved in ≤ 2 clicks, with optional notes.
- After any decision, the affected list and stats reflect it without a manual refresh.
- An admin can answer, from one screen, for any action: what it is, who can call it, and how it has been used.
- A newly registered agent's key is delivered via a reveal-once flow and never retrievable afterwards.
- All lists remain usable at thousands of rows (pagination + filters server-side).
- The console shows exactly the same state an API consumer sees (single shared data layer).

## Beyond the scope of this document

- **Agent-facing API design details** — the full agent-facing endpoint contract is defined in `rest-api-v2.md`; this document covers the admin console only.
- **Skill documents** — client and provider skill content.
- **Infrastructure** — stack, packaging, deployment, config file paths (`infra-v2.md`).
- **Schema registry internals** — validation rules and instruction-field semantics (`schemas-v2.md`).
- **Per-admin permissions or SSO** — all admins are equal in this version.
- **Push-based realtime updates** — polling and refresh-on-interaction only.



