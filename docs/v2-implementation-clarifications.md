# v2 Implementation Clarifications — Answered

> Open questions gathered from a full review of the v2 PRD set (`system-prd-v2.md`, `rest-api-v2.md`, `dispatch-v2.md`, `schemas-v2.md`, `webui-v2.md`, `infra-v2.md`), now **answered in-line** so a complete task breakdown can be written.
>
> Answers are of two kinds: **[PRD]** — already specified or now added to the PRDs (small normative edits were made alongside this document: `arbiter_unavailable` error code in `rest-api-v2.md`; enrollment `reset` route and authoritative route-table heading in `webui-v2.md`; removal of stale "future webui" references in `system-prd-v2.md`); and **[Decision]** — a default chosen here, which the project owner may override before coding starts but which is otherwise binding for task breakdown.
>
> Earlier inconsistencies (state-model vocabulary, completions request body, admin auth precedence, admin API scope) were resolved in the updated PRDs and are removed from this list.

Sections are ordered by implementation risk.

---

## A. Arbiter behavior (highest implementation risk)

1. **Arbiter transport failure handling.** An *unparseable verdict* counts as a failed check (specified in `schemas-v2.md`). But what happens on a **transport error or timeout calling OpenRouter** (rate limit, 5xx, network error)?
   - **Answer [PRD].** A transport failure of the arbiter call is distinct from a verdict failure:
   - **Request side**: fail the invocation immediately with **`503 arbiter_unavailable`** (`error.code` token now added to `rest-api-v2.md`). No dispatch to the provider occurs; the request is not counted against the provider. The client may retry.
   - **Response side**: an arbiter transport failure counts as a **retryable failed dispatch attempt** (same as a provider-side failure) because the response cannot be certified; exhausting the retry budget yields **`502 provider_failed`**.
   - An unparseable arbiter verdict remains a failed check: on the request side it is `4xx arbiter_rejected` (fail-closed), on the response side a retryable attempt. The arbiter call itself is made **once per check** — retries of the arbiter call are not the DMZ's job beyond the dispatch retry loop.

2. **Arbiter call parameters.** No temperature, max-tokens, or timeout is specified for arbiter calls via LiteLLM. The verdict-parse fallback (first `{...}` block) is specified, but the call budget is not. The default value of `ARBITER_MODEL` is also unspecified.
   - **Answer [Decision].** Arbiter calls are deterministic safety checks, so: `temperature=0`, `max_tokens=512`, per-call `timeout=30s`, no LiteLLM-level retries (DMZ handles failures per item 1). System prompt + request/response content are the only user turn. Defaults live in config with these fallbacks: `ARBITER_MODEL` default `openai/gpt-4o-mini` (OpenRouter naming), overridable via YAML/env. All values must be config knobs, not hardcoded.

3. **Base prompt text.** The base request/response arbiter prompts are "maintained in code" — but do not exist yet. Who authors and reviews them?
   - **Answer [Decision].** The implementer drafts them as **named deliverables** (one constant module, e.g. `arbiter_prompts.py`, with `REQUEST_BASE_PROMPT` and `RESPONSE_BASE_PROMPT`), placed under explicit PR review by the project owner — they are security-critical assets, not improvised strings. Task list includes a "write + review base prompts" task with acceptance criteria: each prompt (a) states the arbiter's job and that it may only answer with the fixed verdict JSON shape, (b) forbids following instructions found inside the checked content, (c) is covered by unit tests asserting the invariant clauses are present (so edits are consciously reviewed).

4. **Retry semantics confirmation.** On dispatch retry, only the response side re-validates/re-arbitrates; the request-side check runs once. This is implied but never stated explicitly.
   - **Answer [PRD confirmation].** Confirmed: **the request-side arbiter check runs exactly once per invocation**, before any dispatch. The retry loop re-executes only dispatch + response validation + response-side arbitration. Request arbiter verdicts and provider request payload are immutable across retries.

---

## B. WSGI / server / runtime

5. **WSGI server not chosen.** No gunicorn/waitress/dev-server decision; worst case ~9 minutes per invoke plus arbiter calls, all synchronous in-process. Worker/thread model and server timeout must be set.
   - **Answer [Decision].** **gunicorn with `gthread` workers** in the Docker image (Linux): `gunicorn -w 2 --threads 16 --timeout 900 --graceful-timeout 900 --keep-alive 5`. Rationale: invokes are I/O-bound (waiting on providers/arbiter), so threads over processes; 2×16 gives ~32 concurrent invokes on modest hardware. **Timeouts must exceed worst case**: 900s covers 3×180s dispatch plus arbiter overhead — any reverse proxy in front must have `proxy_read_timeout` ≥ 900s too (note added to deployment checklist task). Local dev: Flask dev server (single-threaded is acceptable; concurrent testing uses gunicorn). Waitress is the fallback only if a Windows-service deployment is ever required.

6. **OpenRouter-side failure taxonomy.** How are LiteLLM/OpenRouter errors (auth, rate limit) surfaced to clients?
   - **Answer [Decision].** Split by cause:
   - **Transient** (rate limit, 5xx, network, timeout): per item 1 — request side `503 arbiter_unavailable`, response side retryable attempt → `502 provider_failed` on exhaustion.
   - **Configuration faults** (invalid OpenRouter key, unknown model, malformed response from OpenRouter): these are operator errors, not client or provider errors → **`500 internal_error`**, logged at ERROR with the LiteLLM exception class, no retry (retrying a bad key never succeeds). Alerting on `internal_error` spikes is an ops concern, documented in the deployment checklist.

---

## C. Lifecycle edge cases

7. **Action stuck in `pending`.** If the first version is rejected, can the provider PUT a new version to a `pending` action whose only version was rejected?
   - **Answer [PRD confirmation].** **Yes.** `pending` means "no active version yet"; the action remains owned by the provider and accepts `PUT /v2/actions/{id}` submissions regardless of prior version rejections. `pending` is not a stuck state — it persists until some version is approved (→ `active`) or the action is withdrawn.

8. **Post-withdrawal behavior.** After `withdrawn`: can the owner PUT a new version? Is `withdrawn` terminal? Do enrollments survive?
   - **Answer [Decision].** `withdrawn` is **not terminal and is owner-reversible**: the owner (or an admin) may submit a new version via `PUT /v2/actions/{id}`; that version follows the normal review path, and on approval the action returns to `active` (and is re-listed in discovery). **Enrollments survive withdrawal** (rows are not deleted); while the action is withdrawn they are inert, and they become valid again automatically if the action returns to `active` — clients do not re-enroll. Revoked/rejected enrollments stay revoked/rejected.

9. **Concurrent PUT while a version is pending.** Overwrite, 409, or auto-reject?
   - **Answer [Decision].** **`409 version_pending`** (error code already in `rest-api-v2.md`). At most one `submitted` version exists per action at a time; a second PUT while one is pending is rejected with the pending version's id in `detail`. Rationale: overwrite loses review context silently, auto-reject makes the reviewer's queue racy; 409 is the simplest unambiguous rule. Admins resolve pending versions promptly; if the pending version is stale the admin rejects it, which unblocks new PUTs (per item 7).

10. **Enrolling in non-`active` actions.** Can a client POST `/enroll` against a `pending` or `withdrawn` action? What does invoking an enrolled-but-withdrawn action return?
    - **Answer [Decision].** **Enrollment: `404 not_found`** for any action without an `active` version (pending or withdrawn) — enrollment is only offered against listed, invokable actions; the directory's `unavailable` annotation is display-only. **Invocation of a withdrawn (or pending) action: `404 not_found`**, confirmed — withdrawn actions disappear from discovery and are non-invokable, and we do not leak existence state to callers. (The enrolled client also gets `404`; the enrollment row survives per item 8 and works again on reactivation.)

11. **Enrollment `rejected` recovery.** Which admin action re-enables re-requesting?
    - **Answer [PRD — route added].** A dedicated console action: **`POST /admin/enrollment/<enrollment_id>/reset`** (added to `webui-v2.md`'s route table). It deletes the `rejected` enrollment record (audited), returning the client to "may request" status. Rejection is otherwise sticky; clients cannot delete or supersede their own rejected records. Reset works on both `rejected` and `revoked` records.

12. **Admin-initiated withdraw vs provider withdraw.** Same soft semantics? Audit distinction?
    - **Answer [PRD confirmation].** **Yes — identical soft semantics** (same state transition, same data retention). Distinguished in the audit trail by **actor**: `audit_events.actor` records the acting agent (provider) vs admin identity, and the webui's action-detail timeline shows both with the actor labeled. One state, two triggers.

---

## D. Data model & storage

13. **No field-level ERD.** Column-level detail, indexes, decision-notes storage, audit-event shape needed before migration tasks.
    - **Answer [Decision].** The authoritative ERD is the **initial Alembic migration** (per item 32); the normative sketch it must implement:
    - **`agents`**: `id` (UUID PK), `name` (unique), `api_key_hash` (unique), `is_client`, `is_provider`, `created_at`.
    - **`actions`**: `id` (string PK = submitted action id), `owner_agent_id` (FK agents, indexed), `state` (`pending|active|withdrawn`), `active_version_id` (nullable FK action_versions), `created_at`, `withdrawn_at`, `withdrawn_by` (nullable; agent id or admin marker).
    - **`action_versions`**: `id` (UUID PK), `action_id` (FK, indexed), `version_number` (int, unique with `action_id`), `state` (`submitted|active|rejected|superseded`), `payload` (JSON: description, both schemas, both arbiter instruction blocks, delivery config), `submitted_at`, `decided_at`, `decided_by`, `decision_notes` (nullable text — this is where admin "optional notes" live).
    - **`enrollments`**: `id` (UUID PK), `agent_id` + `action_id` (unique together), `state` (`requested|enrolled|rejected|revoked`), `requested_at`, `decided_at`, `decided_by`, `decision_notes`, `revoked_at`. Indexes: `(agent_id)`, `(action_id)`.
    - **`requests`**: `id` (UUID PK), `action_id`, `agent_id`, `active_version_id` (snapshot), `request_payload` (JSON), `request_verdict` (JSON), `response_payload` (JSON, nullable), `outcome` (stable token: `completed|arbiter_rejected|provider_failed|arbiter_unavailable|internal_error|…`), `created_at`, `finished_at`. Indexes: `(action_id, created_at)`, `(agent_id, created_at)`, `(created_at)` for stats.
    - **`dispatch_attempts`**: `id` (UUID PK), `request_id` (FK, indexed), `attempt_number`, `framing`, `error_class` (nullable), `error_detail` (text; redacted per-provider error feedback), `started_at`, `finished_at`.
    - **`audit_events`**: `id` (UUID PK), `occurred_at`, `actor_type` (`agent|admin|system`), `actor_id`, `event` (stable token, e.g. `version.approved`, `enrollment.revoked`, `action.withdrawn`), `target_type`, `target_id`, `detail` (JSON; includes decision notes). Indexes: `(target_type, target_id)`, `(occurred_at)`.
    - Delivery configs live inside `action_versions.payload` (versioned with the action), not a separate table.

14. **Request log retention.** Any purge/archival policy?
    - **Answer [Decision].** **Unbounded in v2** — full payloads and attempts are retained (they are the audit surface). No purge job in v2; the schema makes a later retention policy a simple background job. "Unbounded growth" is documented as a known operational property in the deployment checklist (SQLite file sizing note).

15. **Bearer key format & hash algorithm.** Which algorithm, length, prefix?
    - **Answer [Decision].** Keys are generated as 32 random bytes via `secrets.token_urlsafe` (43 chars), prefixed: agent keys **`dmz_`**, admin tokens **`dmzadm_`**. Stored as **SHA-256 hex** of the full string; authentication is hash-lookup against the unique indexed column. Reveal-once at creation; never recoverable. Prefixes are cosmetic metadata (see item 17) — auth always goes through the hash.

16. **"Protected at rest" for delivery configs.** What does this concretely mean with SQLite?
    - **Answer [Decision].** In v2 the concrete control is: **OS file permissions on the database file** (`0600`, owner-only, enforced by the entrypoint script; on SQLite this is the practical boundary) plus the invariant that delivery configs are **never serialized back out through any API, fragment, or log** (write-only from the DMZ's perspective; used only by the dispatcher). Application-layer encryption of the JSON column is explicitly **deferred** — noted in the PRD as a deployment-environment concern (full-disk encryption / restricted volume in real deployments).

17. **Admin token vs agent key collision.** Both arrive as `Authorization: Bearer ...`.
    - **Answer [Decision].** Separate, prefix-distinguished namespaces (`dmz_` vs `dmzadm_`, item 15) plus role columns; validation resolves the bearer token to an identity (admin or agent) before route authorization. An **agent key hitting `/admin/*`** returns **`403 forbidden`** (authenticated, not admin) for mutating/fragment routes and redirects to login for page routes. An **admin token hitting `/v2/*`** returns `403 forbidden` (admin tokens are console-only). Unknown/garbage bearer → `401 unauthorized` everywhere.

---

## E. API details

18. **`GET /v2/actions` pagination/filtering.** Query params, caps, defaults for the agent-facing directory.
    - **Answer [Decision].** `?page=1&per_page=100` (max `per_page=500`; invalid values clamp, not error), `?q=<substring>` matched case-insensitively against `id` and `description`, `?enrollment=` filter (`available|requested|enrolled|unavailable`). Response carries `items`, `page`, `per_page`, `total`. Ordering: alphabetical by `id`. Filters compose.

19. **Dual-role agent projection.** What does `GET /v2/actions` return for a both-flag agent?
    - **Answer [Decision].** **One merged list**: every action shown in the client projection (with the caller's enrollment annotation), and the caller's own actions additionally carry the provider fields (`pending_version`, `state`, version history) — i.e. the client projection is the base, provider detail is an overlay on owned rows. No separate provider listing endpoint.

20. **Provider-as-client visibility.** Does a dual-flag agent see other providers' actions in the directory?
    - **Answer [PRD confirmation].** **Confirmed yes** — any agent with `is_client` sees the full client projection (all actions with an active version, with enrollment annotations), including other providers' actions. `is_provider` adds nothing to directory visibility except the overlay on owned rows (item 19).




## C. Lifecycle edge cases

7. **Action stuck in `pending`.** If the *first* version is rejected, the action state stays `pending` (per the state table). Can the provider PUT a new version to a `pending` action whose only version was rejected? (Presumably yes — confirm.)
8. **Post-withdrawal behavior.** After `withdrawn`:
   - Can the owner PUT a new version (reactivating the action)?
   - Is `withdrawn` terminal?
   - Do existing enrollments survive in the DB, and are they valid again if the action ever returns to `active`?
9. **Concurrent PUT while a version is pending.** A second PUT before the first version is decided: overwrite the pending version, `409`, or auto-reject the older one? Unspecified.
10. **Enrolling in non-`active` actions.** `unavailable` actions are shown "for directory completeness" — can a client POST `/enroll` against a `pending` or `withdrawn` action, or is that a `404`? And what does invoking an enrolled-but-now-withdrawn action return — `not_found` or `403`? (Implied `not_found`; confirm.)
11. **Enrollment `rejected` recovery.** "Client may not re-request without admin action" — which admin action re-enables re-requesting (delete the rejected record? a "reset" control?). No route for it exists in the webui route table.
12. **Admin-initiated withdraw vs provider withdraw.** Same soft semantics? How is it distinguished in the audit trail? (Implied yes; confirm.)

## D. Data model & storage

13. **No field-level ERD.** Entities are implied (agents, actions, action_versions, enrollments, requests, dispatch attempts, audit_events) but column-level detail — indexes, timestamps, decision-notes fields (the webui mentions "optional notes" on decisions — where are they stored?), and the audit-event shape — must be designed before migration tasks can be written.
14. **Request log retention.** Full payloads are retained for audit — is there any purge/archival policy, or unbounded growth?
15. **Bearer key format & hash algorithm.** Keys are "stored only as hashes" — which algorithm, what key length/prefix convention? Needed for the generation + reveal-once flow and tests.
16. **"Protected at rest" for delivery configs.** With SQLite as the default database, what does this concretely mean (application-layer encryption? OS file permissions? deferred to deployment)? An undefined control cannot be implemented.
17. **Admin token vs agent key collision.** Admin bearer tokens and agent keys both arrive as `Authorization: Bearer ...` — separate namespaces/prefixes? What does an agent key hitting `/admin/*` return?

## E. API details

18. **`GET /v2/actions` pagination/filtering.** Specified for the admin console only. The agent-facing directory needs query params, caps, and defaults.
19. **Dual-role agent projection.** `GET /v2/skill` merges both skills for both-flag agents, but what does `GET /v2/actions` return for an agent with both flags — a merged client+provider list?
20. **Provider-as-client visibility.** A provider-only agent sees only its own actions; a provider that is also a client presumably sees the full client projection including other providers' actions — confirm.
21. **Skill document prose.** "Authored with the implementation." Who writes and reviews the client and provider skill texts?
    - **Answer [Decision].** Same treatment as the arbiter prompts (item 3): the implementer drafts both skill texts as **named deliverables** (e.g. `skills/client.md`, `skills/provider.md`, versioned in the repo and served verbatim from `/v2/skill`), reviewed via PR by the project owner. Acceptance criteria: client skill covers directory listing, enrollment, invocation, error tokens, and long-invoke timeouts; provider skill covers submission shape, versioning, withdraw, delivery-config fields, and the framing contract in `dispatch-v2.md`. Tests assert the served skill text is non-empty and mentions the core endpoints.

---

## F. Admin console

22. **Datastar & 0build acquisition method.** Vendored, CDN, or package?
    - **Answer [Decision].** **Vendored static files committed to the repo** under `static/vendor/`: the Datastar single-file browser script (pinned release) and a prebuilt 0build CSS bundle. No CDN links, no runtime package fetch — satisfies the offline test suite and the no-network Docker build. A `scripts/update_vendor.py` (or documented manual step) notes the pinned versions for future upgrades.

23. **Admin password storage & session policy.** Plaintext or hashed? Session lifetime, logout, CSRF?
    - **Answer [Decision].** The YAML may hold either a plaintext password (operator's choice for simple deployments) **or** a Werkzeug-style hash (`pbkdf2:sha256:...`); the loader hashes/compares accordingly — hash strongly preferred and documented. **Sessions**: Flask signed-cookie sessions, `SESSION_COOKIE_HTTPONLY`, `SAMESITE=Lax`, secure-flag on in the Docker deployment; lifetime **12 hours** (rolling refresh on activity). **Logout**: `POST /admin/logout` (added to the route table). **CSRF**: per-session token, required as a hidden field on every console form POST; missing/mismatched token → `400`. Bearer-token mutations (`Authorization:` header) are exempt (header presence is the CSRF defense).

24. **Version diff fidelity.** Textual or structural JSON diff?
    - **Answer [Decision].** **Structural (JSON-aware) diff.** Each submitted version is diffed field-by-field against the active version's payload (description, request schema, response schema, both instruction blocks, delivery config) using a deep-diff walk rendered as per-field changed/added/removed entries; schemas are compared as parsed JSON trees, never as raw text. Implement as a small utility (sorted-key canonicalization + recursive walk) rather than pulling a diff dependency, with unit tests on nested schema changes.

25. **Multi-patch response shape.** Concrete reference pattern needed.
    - **Answer [Decision].** All console mutations respond with **Datastar SSE merge responses** (`Content-Type: text/event-stream`) emitting multiple events so one action can update several regions, e.g. approving a version:

```
event: datastar-merge-fragments
data: selector #pending-queue-count
data: mode replace
data: fragments
data: <span id="pending-queue-count">2</span>

event: datastar-merge-fragments
data: selector #version-<id>-state
data: mode replace
data: fragments
data: <span class="badge active">active</span>
```

    - Reference pattern: one named target element per updated region, `mode: replace`, and a shared Jinja partial per region so initial render and patches cannot diverge. Tests assert fragment routes return `text/event-stream` with at least the expected selectors.

26. **Stats windows.** All-time or rolling? What is "recent"?
    - **Answer [Decision].** **"Request totals by outcome" = all-time counts** (cheap on SQLite, stable). **"Recent invocation count" = trailing 24-hour window**, computed with the `created_at` index; the console labels it "last 24h" so it is never ambiguous.

27. **Route table authority.** Webui route table was marked illustrative; one mutating route showed session-only while system PRD says all mutating endpoints accept the admin token.
    - **Answer [PRD — fixed].** The webui route table is now headed **"Routes (authoritative surface)"** (edited in `webui-v2.md`). Rule confirmed: **every mutating `POST /admin/...` accepts either the admin session or the admin bearer token**; read pages are session-only; fragments are session-or-token (read fragments remain session-only for page-embedded ones — any fragment intended for API scripting is individually listed with `session / admin token`). The table is the final route list; additions during implementation require a PRD edit, not a code-only change.


## G. Infra & process

28. **Exact config filename(s) & precedence.** YAML path/search order, env-vs-YAML precedence, system-default vs per-provider retries.
    - **Answer [Decision].** Single config file, path from env **`DMZ_CONFIG`**, falling back to **`./config.yaml`** (no other search paths — predictable in Docker, where the path is fixed anyway). Precedence, highest wins: **env vars → YAML → code defaults**. Per-provider `retries` and `timeout` in a delivery config **override** the system defaults (`retries: 2`, `timeout: 180`); an unset per-provider field falls back to the system value. Same rule for arbiter settings.

29. **Dependency pin set.** No initial versions committed; who decides?
    - **Answer [Decision].** The implementer decides at scaffold time and commits both `pyproject.toml` constraints and a lockfile in the **first scaffolding PR** (so CI pins from day one). Constraints: Python 3.12, Flask `>=3.0,<4`, SQLAlchemy `>=2.0,<2.1`, plus current-stable LiteLLM, PyYAML, Alembic, gunicorn, dydantic; dev extras: pytest, ruff, mypy. Upgrades are explicit PRs that touch the lockfile only.

30. **CI platform & repo state.** Which CI system? Greenfield or existing scaffolding?
    - **Answer [Decision].** **GitHub Actions** (`.github/workflows/ci.yml`): lint (ruff) → typecheck (mypy) → tests (pytest, offline per item 31) → `docker compose config` validation → image build (no push on PRs). The repo is **brownfield** — v1 code exists; v2 is built alongside in the same repo behind the `/v2/` blueprint, with v1 untouched until cutover.

31. **Offline mock strategy.** In-process fake, HTTP mocking, or stub module?
    - **Answer [Decision].** **Stub-module layer with dependency injection**: the dispatcher takes an `ArbiterClient` and a `ProviderTransport` interface; tests inject a fake that returns scripted verdicts/candidates/transport errors by scenario. No network, no HTTP-level mocking libraries, no monkeypatching LiteLLM internals — the seam is the interface. One thin adapter each wraps real LiteLLM/HTTP in production; adapters are excluded from coverage targets but covered by a manually run smoke script.

32. **Alembic baseline approach.** One initial migration or incremental?
    - **Answer [Decision].** **One initial baseline migration** creating the full schema from item 13 (the ERD's authoritative form), committed with the data-model task. Subsequent schema changes are normal incremental migrations. No per-feature migration fan-out during initial build — the schema is designed up front.

33. **Documentation nit.** `system-prd-v2.md` still refers to `webui-v2.md` as "future" (twice).
    - **Answer [PRD — fixed].** All four "future `webui-v2.md`" references (header + three body mentions) were edited to plain references in `system-prd-v2.md`.


---

## Blockers — resolved

Every previously listed blocker is answered above:

- **#1–2** (arbiter failure handling, call parameters) → items 1, 2, 6
- **#5** (WSGI server and timeouts) → item 5
- **#9–11** (lifecycle edge cases) → items 9, 10, 11 (plus 7, 8, 12)
- **#13** (field-level data model) → item 13
- **#23** (admin password / session / CSRF) → item 23
- **#28–30** (config precedence, dependency pins, CI) → items 28, 29, 30

The task breakdown can now be written against these answers. Items tagged **[Decision]** are binding defaults; the project owner may amend any of them by editing this document before the corresponding task starts.
