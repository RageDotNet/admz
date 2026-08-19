# LLM DMZ v2 â€” Implementation Todo List

> **Read this first:** To have sufficient context, you must read the v2 PRD set indexed in [`docs/index-v2.md`](docs/index-v2.md) â€” `system-prd-v2.md`, `rest-api-v2.md`, `dispatch-v2.md`, `schemas-v2.md`, `webui-v2.md`, and `infra-v2.md` â€” before starting any task below. Each PRD is standalone; task references to `#N` point to numbered answers in `docs/v2-implementation-clarifications.md`, which is also required reading.

> Ordered; check items off top to bottom. Every task â‰¤ ~4 hours of junior-engineer time.
> Global rules: offline tests only (stub fakes per clarification #31); every state change writes an `audit_events` row; route additions require a PRD edit (clarification #27); prompts/skills tasks require project-owner sign-off.
> Source docs: `docs/index-v2.md` (PRD set) and `docs/v2-implementation-clarifications.md` (binding answers, referenced as #N below).

## Phase 0 â€” Scaffolding & CI

- [x] T0.1 Create `pyproject.toml` with pinned deps + lockfile (Python 3.12, Flask `>=3.0,<4`, SQLAlchemy `>=2.0,<2.1`, LiteLLM, PyYAML, Alembic, gunicorn, dydantic; dev extras: pytest, ruff, mypy)
- [x] T0.2 Create v2 package skeleton (`src/` layout: app, core, agents) with console-script entry point and empty app factory
- [x] T0.3 Add ruff + mypy config wired into the pytest run; verify with a placeholder test
- [x] T0.4 **Validate:** `pip install -e .[dev]` succeeds in a fresh venv; ruff/mypy/pytest all run green
- [x] T0.5 Write `fabfile.py` commands (`dev.up`/`dev.down`, `test`, `lint`, `fmt`, `db.migrate`, `db.upgrade`, `build`, `deploy`) as thin wrappers
- [x] T0.6 **Validate:** each fab command executes without error (no-op with message OK until later phases)
- [x] T0.7 Create GitHub Actions workflow: lint â†’ typecheck â†’ pytest â†’ compose config check â†’ image build (no push on PRs)
- [x] T0.8 **Validate:** CI runs green on a trivial commit
- [x] T0.9 Build config loader: `DMZ_CONFIG` env â†’ `./config.yaml` fallback; precedence env > YAML > code defaults (#28)
- [x] T0.10 Add loud startup validation (crash on bad config) + admin account parsing (plaintext or `pbkdf2:sha256`, #23)
- [x] T0.11 **Validate:** unit tests cover precedence order, missing file, malformed YAML, bad admin entries
- [x] T0.12 Write `deploy/Dockerfile` (Python base, non-root, pip-install package) + `docker-compose.yml` with SQLite volume and `alembic upgrade head` entrypoint; entrypoint enforces `0600` on the DB file (#16)
- [x] T0.13 **Validate:** `docker compose up` starts; entrypoint order correct; DB file permissions verified

## Phase 1 â€” Storage & Identity

- [x] T1.1 Implement `agents` + `audit_events` SQLAlchemy models per ERD (#13)
- [x] T1.2 Implement `actions` + `action_versions` + `enrollments` models per ERD (delivery configs inside `action_versions.payload`)
- [x] T1.3 Implement `requests` + `dispatch_attempts` models per ERD with all indexes
- [x] T1.4 Create single baseline Alembic migration from the models (#32)
- [x] T1.5 **Validate:** migration upgrade/downgrade round-trips clean on SQLite; schema spot-checked against #13; optional Postgres pass for portability
- [x] T1.6 Build storage module: CRUD + list/get with pagination for agents, actions, versions, enrollments
- [x] T1.7 Build storage module: request/dispatch-attempt logging writes + stats queries (all-time by outcome, trailing 24h, #26)
- [x] T1.8 **Validate:** storage unit tests (pagination bounds, unique constraints, stats math with fixed timestamps)
- [x] T1.9 Build audit helper (append-only `audit_events` writer with actor/event/target/detail)
- [x] T1.10 Implement key generation: `dmz_`/`dmzadm_` prefixes, `token_urlsafe(32)`, SHA-256 hex storage (#15)
- [x] T1.11 Implement bearer auth middleware resolving any Bearer token to agent-or-admin identity (#17)
- [x] T1.12 **Validate:** unit tests â€” reveal-once semantics, hash lookup, unknown/garbage token â†’ 401, prefix namespaces don't collide

## Phase 2 â€” Schema Registry & Action Lifecycle

- [x] T2.1 Implement submission field validation (required fields, types, instruction-field rules from `schemas-v2.md`)
- [x] T2.2 Implement JSON Schema draft 2020-12 compilation of request/response schemas (422 on failure) + dydantic model generation
- [x] T2.3 **Validate:** unit tests using the `crm_search` example plus compile-failure (422) and malformed-body (400) cases
- [x] T2.4 Implement `POST /v2/actions` (create action + submitted version 1; `409 duplicate_action`; audit)
- [x] T2.5 Implement `GET /v2/actions/{id}` role-projected views (client vs owner)
- [x] T2.6 Implement `PUT /v2/actions/{id}` new version (monotonic numbering; `409 version_pending` while one submitted, #9; audit)
- [x] T2.7 Implement `DELETE` withdraw (soft, reversible, `withdrawn_by` recorded, #8/#12; audit) and `GET /v2/actions/{id}/versions`
- [ ] T2.8 **Validate:** API tests â€” full lifecycle (pending accepts PUT after rejection #7, withdrawn reversible, supersede flow, ownership 403s, hidden-action 404s)
- [x] T2.9 Implement error-envelope middleware (all `rest-api-v2.md` codes incl. `arbiter_unavailable`)
- [x] T2.10 Implement `GET /v2/actions` directory: `page`/`per_page` (clamp), `q` substring, `enrollment` filter, alphabetical order (#18)
- [x] T2.11 Implement client-projection base + provider overlay on owned rows for dual-role agents (#19, #20)
- [x] T2.12 **Validate:** API tests for filters/pagination/projections per #18â€“20
- [x] T2.13 Implement `POST`/`GET /v2/actions/{id}/enroll` (`409 already_enrolled`; `404` when no active version, #10; audit)
- [x] T2.14 **Validate:** enrollment tests incl. non-active 404 and enrollments-survive-withdrawal behavior
- [x] T2.15 Draft `skills/client.md` and `skills/provider.md` per clarification #21 acceptance criteria
- [x] T2.16 Implement `GET /v2/skill` serving texts (merged for dual-role agents)
- [x] T2.17 **Validate + owner gate:** tests assert non-empty + core endpoints mentioned; **project-owner review of skill prose required before merge**

## Phase 3 â€” Arbitration & Dispatch

- [x] T3.1 Define `ArbiterClient` + `ProviderTransport` interfaces (the DI seam for offline tests, #31)
- [x] T3.2 Implement verdict parser (JSON â†’ first-`{...}` fallback, bool coercion, default reason; unparseable = failed check)
- [x] T3.3 **Validate:** verdict-parser unit tests (clean JSON, fenced JSON, prose-wrapped JSON, garbage)
- [x] T3.4 Write `arbiter_prompts.py` (`REQUEST_BASE_PROMPT` / `RESPONSE_BASE_PROMPT`) meeting clarification #3 criteria
- [x] T3.5 **Validate + owner gate:** tests assert invariant clauses present (job statement, fixed verdict shape, injection refusal); **owner review of prompt text required before merge**
- [x] T3.6 Implement LiteLLM arbiter adapter (temp 0, max_tokens 512, 30s timeout, no LiteLLM retries, `ARBITER_MODEL` default `openai/gpt-4o-mini`, all knobs, #2)
- [x] T3.7 Implement `post` transport adapter (endpoint + verbatim headers, unstructured framing incl. retry-error injection)
- [x] T3.8 Implement `exec` transport adapter (subprocess, timeout, exit code/stderr capture)
- [x] T3.9 Implement `completions` transport adapter (chat-completions body with `model`, system/user framing)
- [x] T3.10 **Validate:** transport unit tests with fake HTTP/subprocess â€” framing exact-match, timeout, per-provider retry/timeout override of defaults (#28)
- [ ] T3.11 Implement invoke pipeline happy path: validate â†’ request arbiter â†’ dispatch â†’ response validate â†’ response arbiter â†’ 200 result
- [ ] T3.12 Implement failure mapping: 4xx rejections (verbatim detail), `503 arbiter_unavailable` (request side), `500 internal_error` (config faults, #1/#6)
- [ ] T3.13 Implement retry loop: response-side validation/arbitration per attempt, error injection, exhaustion â†’ `502 provider_failed`; request-side check runs exactly once (#4)
- [ ] T3.14 Implement `requests` + `dispatch_attempts` logging (framing, timestamps, `error_class`/`detail` per attempt, #13)
- [ ] T3.15 **Validate:** integration tests with injected fakes â€” every outcome path, retry-injection content, retry exhaustion, arbiter outage on both sides, immutable request verdict across retries
- [ ] T3.16 Write manually-run smoke script (real OpenRouter + live provider); document in README

## Phase 4 â€” Admin Console

- [ ] T4.1 Mount `/admin` blueprint; login/logout routes; session config (12h rolling, HttpOnly, SameSite=Lax, secure in Docker, #23)
- [ ] T4.2 Implement CSRF: per-session token, hidden field on all console forms, 400 on mismatch; bearer mutations exempt
- [ ] T4.3 Implement auth guard decorator (bearer first, else session; agent key â†’ 403/redirect per #17)
- [ ] T4.4 **Validate:** auth matrix tests (page redirect, fragment 401, agent-key 403, admin-token-on-/v2 403, unknown 401, CSRF reject)
- [ ] T4.5 Vendor Datastar script + 0build CSS into `static/vendor/` with pinned versions + `scripts/update_vendor.py` (#22)
- [ ] T4.6 Implement multi-patch SSE merge response helper + shared partial-per-region pattern (#25)
- [ ] T4.7 **Validate:** fragment route test returns `text/event-stream` with expected selectors; assets served with no network
- [ ] T4.8 Build dashboard shell: stats bar (agent count, action states, pending enrollments, all-time outcomes, 24h count, #26) + six Datastar tabs
- [ ] T4.9 **Validate:** stats numbers match storage-module stats; tab switching without full reload
- [ ] T4.10 Build directory tab: all actions/versions/states/owners, server-side pagination + filters
- [ ] T4.11 Build structural JSON diff utility (canonicalize + recursive walk; per-field changed/added/removed, #24)
- [ ] T4.12 **Validate:** diff utility unit tests on nested schema changes (no new dependency)
- [ ] T4.13 Build per-action detail view: definition, version history with diff vs active, enrolled clients, invocation history, admin withdraw (actor-labeled)
- [ ] T4.14 Build pending-version approval queue: approve/reject + optional notes (`decision_notes`), activation incl. withdrawnâ†’active path
- [ ] T4.15 Build enrollment queue: approve/reject + notes, revoke, admin-initiated enroll, `POST /admin/enrollment/<id>/reset` (#11)
- [ ] T4.16 **Validate:** queue tests â€” â‰¤2-click flows, notes persisted, multi-patch updates queue+stats together, audit rows with actor
- [ ] T4.17 Build agents tab: register (reveal-once key), re-issue/revoke keys, capability flags, delivery-config editing (never echoed back, #16)
- [ ] T4.18 **Validate:** reveal-once flow test; delivery config absent from all API/fragment/log output
- [ ] T4.19 Build request log tab: paginated/filtered list + per-request detail (payloads, verdicts, attempts)
- [ ] T4.20 Build audit trail tab: append-only, actor-labeled, filtered/paginated
- [ ] T4.21 **Validate:** route table matches `webui-v2.md` "authoritative surface" exactly (route-introspection test); log/audit pagination caps enforced

## Phase 5 â€” Hardening & Cutover Prep

- [ ] T5.1 E2E scenario 1: provider registers â†’ admin approves â†’ client enrolls â†’ admin grants â†’ invoke succeeds (all fakes)
- [ ] T5.2 E2E scenario 2: withdrawal â†’ 404 on invoke â†’ new version approved â†’ auto-reactivation, enrollment still valid (#8)
- [ ] T5.3 E2E scenario 3: version supersede, enrollment rejection â†’ admin reset â†’ re-request (#11), retry exhaustion, arbiter outage paths (#1)
- [ ] T5.4 **Validate:** full suite + lint + typecheck green in CI; `fab test` from a clean checkout
- [ ] T5.5 Write `deploy/README.md` checklist (gunicorn `-w 2 --threads 16 --timeout 900`, `proxy_read_timeout` â‰¥ 900s, OpenRouter key checks, `internal_error` alerting, SQLite sizing/growth note, vendor upgrade step)
- [ ] T5.6 Final compose validation: deterministic config check, entrypoint order (migrate â†’ serve), documented smoke-run steps

---

## Dependencies & assignment notes

- T0.* block everything; T1 blocks T2â€“T4; T2.1 â†’ T2.2 â†’ T2.4+; T3.1 before T3.6â€“T3.9; T3.11â€“T3.13 need T3.6â€“T3.9 and T1.7; T4.* need T1/T2 storage and lifecycle; T5.* last.
- **Owner-review gates:** T2.17 (skills) and T3.5 (arbiter prompts) â€” do not merge without project-owner sign-off.
- Suggested split for 4 juniors: J1 = Phase 0 (+infra ownership throughout); J2 = Phase 1 + T2.1â€“T2.8; J3 = T2.9â€“T2.17 + Phase 4; J4 = Phase 3 (strongest junior; pair with owner on prompts).

