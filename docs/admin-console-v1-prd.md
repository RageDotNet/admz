# PRD — Admin Console (v1)

> Product requirements document for the existing admin console, written from the current implementation (`dmz/admin_routes.py`, `templates/admin/`, and the review queue in `dmz/storage.py`). This is a descriptive PRD of **what v1 is**, intended as the baseline for planning the next version.

## 1. Summary

The admin console is a browser-based dashboard attached to the A2A DMZ gateway (`a2admz.py`) at `/admin`. It gives human reviewers visibility into everything crossing the DMZ and the ability to approve or reject requests that failed automated validation (schema validation or LLM arbitration).

### Problem statement

The DMZ gates all traffic between untrusted external clients and trusted internal providers. Automated checks catch most problems, but schema failures and arbiter rejections need a **human decision** before a message can proceed or be killed. Without a console, reviewers would have to use `review_cli.py` or raw REST calls — workable, but slow and with no visibility into overall traffic.

### Goals

- Let reviewers see and act on the review queue with minimal friction (one click to approve/reject, optional notes).
- Give full visibility into traffic: in-flight, historical, and pending review.
- Expose the registered schemas so reviewers understand what operations exist.
- Zero custom JavaScript — interactivity via Datastar; styling via 0build CSS.

### Non-goals (v1)

- Editing or registering schemas (the Schemas tab is read-only).
- REST gateway (`llmdmz.py`) hosting — the console is only registered on the A2A gateway today.
- Multi-tenant or role-differentiated admin features beyond the existing reviewer auth.
- Real-time push updates — In-flight polls every 3 seconds.

## 2. Users & access

| Aspect | Detail |
|---|---|
| Primary user | Human **reviewer** (operations/security role) |
| Authentication | Agent ID + key from `config/agents.json`, same credential store as gateway agents (default reviewer: `reviewer1` / `review-dev-key-change-me`) |
| Session | Flask signed-cookie session (`FLASK_SECRET_KEY`); login stores agent ID under the `admin_agent_id` session key |
| Unauthenticated behavior | Page requests redirect to `/admin/login`; partial (Datastar) requests return `401 Unauthorized` |
| Credential input | Login accepts Datastar signals, classic form posts, or JSON bodies (both `agentId`/`agentKey` and `agent_id`/`agent_key` key styles) |

## 3. Functional requirements

### 3.1 Tabs

The dashboard is a single page with four tabs; clicking a tab fetches its partial via Datastar without a full page reload.

| Tab | Partial route | Contents |
|---|---|---|
| **Review queue** | `/admin/partials/reviews` | Pending review items (up to 100) flagged by schema validation or the arbiter, with Approve/Reject buttons and expandable request detail |
| **In-flight** | `/admin/partials/inflight` | Requests currently validating, forwarded, or awaiting review; auto-refreshes every 3 seconds |
| **Access log** | `/admin/partials/log` | Completed and historical requests (up to 100, newest first), excluding in-flight |
| **Schemas** | `/admin/partials/schemas` | Registered schema bindings: ID, description, agent bindings, A2A URLs, and full JSON Schema definitions |

### 3.2 Stats bar

A compact bar above the tabs, rendered from `/admin/partials/stats`, showing:

- schema count
- in-flight request count
- pending review count
- total requests, with per-status breakdown

### 3.3 Request detail

- Each row/card has a **Details** toggle that expands inline detail below the selected row.
- Expanded detail shows the full request record: status, schema ID, request/response payloads, validation errors, arbiter verdicts — payloads pretty-printed as JSON.
- Detail is driven by a `detailRequestId` Datastar signal; the server renders the expanded row server-side so no client-side rendering logic is needed.
- `/admin/partials/request/<request_id>` renders detail for a single request; `/admin/partials/request-detail-clear/<request_id>` collapses it. Unknown request IDs return 404.

### 3.4 Review actions

- `POST /admin/review/<review_id>/approve` and `POST /admin/review/<review_id>/reject`
- Optional reviewer notes accepted from JSON body (`notes` or `reviewNotes`) or form field.
- Actions are attributed to the logged-in reviewer agent ID and logged (`Admin approved review_id=… reviewer=…`).
- The response is a **multi-patch HTML fragment** that atomically refreshes both the review queue and the stats bar, so counts update immediately after a decision.
- Approving a pending-review request lets it continue its lifecycle (e.g. `pending_review_request` → `pending_requestee`); rejecting terminates it (`rejected`).

### 3.5 Login / logout

- `/admin/login` renders the login form (with an error partial on bad credentials); logout is a form POST that clears the session.

## 4. Route inventory

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/admin` | Dashboard shell (tab layout, stats bar) | session |
| GET/POST | `/admin/login` | Sign in | none |
| POST | `/admin/logout` | Sign out | session |
| GET | `/admin/partials/stats` | Stats bar fragment | session |
| GET | `/admin/partials/inflight` | In-flight requests fragment | session |
| GET | `/admin/partials/log` | Historical requests fragment | session |
| GET | `/admin/partials/reviews` | Review queue fragment | session |
| GET | `/admin/partials/schemas` | Registered schemas fragment | session |
| GET | `/admin/partials/request/<request_id>` | Single request detail fragment | session |
| GET | `/admin/partials/request-detail-clear/<request_id>` | Collapse-detail fragment | session |
| POST | `/admin/review/<review_id>/approve` | Approve a review item (optional notes) | session |
| POST | `/admin/review/<review_id>/reject` | Reject a review item (optional notes) | session |

Non-UI equivalents of the review actions exist for automation: `review_cli.py` and `POST /api/v1/review/{review_id}/approve|reject`.

## 5. UX principles

- **No custom JavaScript.** All interactivity (tab switching, detail expansion, auto-refresh, review actions) is server-rendered HTML fragments orchestrated by Datastar attributes.
- **Zero-build CSS.** Styling comes from 0build utility classes (`z-*`); no bundler or CSS pipeline.
- **Server-rendered everything.** The server owns all rendering logic, including expanded rows and post-action refreshes, keeping templates as the single source of UI truth.
- **Inline detail.** Details expand in place under the selected row rather than navigating to a separate page.

## 6. Technical design

- **Registration:** `register_admin_routes(app, agent_registry=…, schema_registry=…, storage=…)` is called by `a2admz.py` at startup; the module sets `app.secret_key` from `FLASK_SECRET_KEY` (dev default: `dev-admin-secret-change-me`).
- **Auth guard:** a `require_admin` decorator checks the Flask session; partials get 401, pages redirect to login.
- **Data:** all content comes from the shared `Storage` layer (`list_pending_reviews`, `list_inflight_requests`, `list_historical_requests`, `get_request`, `count_requests_by_status`) and `SchemaRegistry.list_schemas()` / `list_schemas_detail()` — the same stores the gateways use, so the console is always consistent with gateway state.
- **Templates:** `templates/admin/` (dashboard, login, macros, and `partials/` for each region). Templates are cached unless `FLASK_DEBUG=1`; template changes require a gateway restart in production.
- **Logging:** all actions logged under the `llmdmz.admin` logger.
- **Multi-patch responses:** approve/reject concatenate two rendered partials (reviews + stats) into one HTML response that Datastar splits and applies to both regions.

## 7. Metrics / success criteria

- Reviewer can resolve any pending review item in ≤ 2 clicks (Approve/Reject), with optional notes.
- Review queue and stats reflect a decision immediately (no manual refresh).
- In-flight view never requires manual refresh (3s polling).
- Console remains usable under hundreds of historical requests (partial queries capped at 100–500 rows).

## 8. Known limitations (candidates for the next version)

- **Schemas tab is read-only** — no way to submit, review, approve, or reject provider schema submissions (the v2 schema model requires this).
- **Attached only to the A2A gateway** — the REST gateway's review queue has no console.
- **Polling, not push** — 3s polling on In-flight; other tabs refresh only on interaction.
- **Reviewer-only roles** — any authenticated reviewer sees everything; no finer-grained permissions.
- **Hard row limits** — lists cap at 100 items with no pagination or filtering/search.
- **No audit UI** — reviewer decisions are logged and stored, but there's no view of past decisions/resolved reviews beyond the access log.
- **Template restart requirement** — template changes need a service restart unless `FLASK_DEBUG=1`.
