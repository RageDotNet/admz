# Admin console UI — implementation todo

> **Read this first:** [`docs/admin-ui-qa.md`](admin-ui-qa.md) (findings from the 2026-08-24 walkthrough) and [`docs/webui-v2.md`](webui-v2.md) (product spec). Bootstrap 5 CSS + Datastar only — no custom JS bundle, no npm. Do not copy copy/layout from the old A2A console under `templates/admin/`.
>
> Revert point: git tag `pre-admin-ui` (`b9fa66b`, before this pass).
>
> Ordered; check items off top to bottom. Every task ≤ ~4 hours of junior-engineer time.
> After template/Python changes, restart `dmz-serve` and hard-refresh before QA. Use a throwaway agent for key-reveal / register flows — do not revoke or reissue keys on live agents (`crm`, `redmain`, etc.).
> **Validate** tasks are browser QA against `http://localhost:8000/admin` unless noted. Confirm behavior, not just a screenshot.

## Shell

- [x] U.1 Wire the stats bar: `data-init` (and keep post-mutation SSE patches) so `#stats-bar` loads `/admin/partials/stats` instead of staying on "Loading stats…"
- [x] U.2 **Validate:** after login, stats show agent count, action counts by state, pending enrollments, outcome totals, last-24h. Approve or reject something (throwaway) and confirm stats update without a full reload.
- [x] U.3 Fix tab/hash handling: stop `href="#"` from wiping the tab hash; tabs restore `$tab` from `#directory`/`#enrollments`/… on load; Log out is not inside `role="tablist"`; tabs expose `aria-selected`
- [x] U.4 **Validate:** click Directory → Agents → an agent name → URL still indicates Agents and the Agents tab looks selected. Reload on `/admin#audit` opens Audit trail. Browser back after a tab change is sane (does not land on a blank/`#` shell with the wrong tab highlighted).
- [x] U.5 Compact header: title, signed-in admin name, Log out (username not on the button). Add a light/dark toggle *or* drop the unused `prefers-color-scheme` init — pick one. Favicon. Document title can follow the active tab.
- [x] U.6 Shared filter toolbar: inputs/selects sit on one row (`w-auto` / max-width), visible `<label>`s (not placeholder-only). Wrap tables in `table-responsive`. Empty states should not look like a broken full-width grey bar.
- [x] U.7 **Validate:** desktop (~1440) filters are one row on Directory, Request log, and Audit. At ~390px width, Directory columns are reachable via horizontal scroll inside the table (Enrolled is not clipped with no way to see it). Filter fields have accessible names besides the placeholder.
- [x] U.8 Shared formatters: human timestamps (no microseconds; full time on `title`; relative OK for recent rows); human state/outcome labels (`Active`, `Provider failed`) with `state_tag` / `text-bg-*` badges everywhere — including SSE patches that currently emit `<span class="badge active">`. Pagination chrome is consistent (total / page / per-page); hide per-page noise when a single short page is enough, or keep it consistent.
- [x] U.9 Small cleanups: delete the 0build comment in `admin.py`; dedupe duplicated `btn btn-sm btn-outline-secondary` classes; replace `mono` with `font-monospace`.
- [x] U.10 Shared confirm for destructive actions (revoke key, new key, revoke enrollment, withdraw action). Datastar-friendly; no silent one-click.
- [x] U.11 Visible loading + error for Datastar fetches/POSTs (`data-indicator` actually shown; 400/404 not silent).
- [x] U.12 **Validate:** badges and timestamps look consistent on Directory, action detail, Request log, Audit. Trigger a 400 (empty agent register, or CSRF if easier) and confirm the admin sees an error, not a no-op.

## Login

- [x] U.13 Username/password `required`; empty submit does not hit the server as "Invalid username or password." Failed login keeps username, clears password, refocuses password. Error is `role="alert"`.
- [x] U.14 **Validate:** empty submit is blocked in-browser. Wrong password shows the alert, username still filled, password empty, focus on password. Successful login still lands on `/admin`.
- [x] U.15 Login polish: full-width Log in button, autofocus Username, consistent Log in / Log out verbs. Optional: product name + "Admin" without repeating the same string as both `<title>` and `h1`.
- [x] U.16 **Validate:** login card at desktop and ~390px; button is an easy hit target; no leftover "Sign in" copy.

## Directory

- [x] U.17 Server-side state filter (not filter-after-paginate). `total` matches the visible set. Search placeholder/label is id (and description if that is what `q` searches) — not "id/state". Pagination preserves `q` and `state`.
- [x] U.18 **Validate:** Filter to `withdrawn` with no withdrawn actions → empty list and **0 total**. Filter to `active` → three actions and total 3. Search `crm_search` then paginate (or force `per_page` down in a test) without losing the query. Clear filters restores the full list.
- [x] U.19 Action open/close: no `href="#"` jump; selected row highlighted; detail scrolls into view; explicit close; unique DOM ids (row state vs detail state no longer share `action-{{ id }}-state`).
- [x] U.20 **Validate:** click `crm_search` → detail visible without the page jumping to the top; row stays highlighted; Close hides it; click `red_opinion` replaces detail; Filter rebuilds the list without leaving a ghost card that cannot be dismissed.
- [x] U.21 List cleanup: description as secondary text when present; owner fallback if the agent is missing; clearer Active/Pending column headers; pending versions visually flagged on the row.
- [x] U.22 **Validate:** pending-version row (use a throwaway submitted version if none) is obviously pending. Owner still shows if data is complete. Withdrawn rows (if any) look muted compared to active.

## Action detail

- [x] U.23 Invocation "Details" patches a **local** target on this card (`#action-request-detail` or equivalent), not `#request-detail` on the Request log tab.
- [x] U.24 **Validate:** from Directory, open `crm_search`, click Details on a completed row — payload/verdict appear **on this tab**. Switch to Request log: it must not show that request as a leftover under the log table unless you opened it there.
- [x] U.25 Headings use Bootstrap heading classes (`h5`/`h6`). Instruction fields stack label-above-value. Show `client_instructions` next to provider/arbiter instructions. Section the card (definition / versions / access / invocations). Owner links to the agent.
- [x] U.26 Version table: compact diffs (no `request_risk: changed request_risk`); diff vs **previous** version, not always vs current active; consistent empty "—"; Actions column has a header; JSON `<pre>`s are bounded.
- [x] U.27 Access: agent names link to Agents; show decided-by/notes; admin-enroll form wired to existing `POST /admin/action/<id>/enroll`. Danger zone at the bottom for Withdraw + confirms (U.10).
- [x] U.28 Invocations: Verdict column is outcome-relevant (or dropped in favor of detail). Cap of 20 plus a "view all in Request log" link that opens the log filtered to this action.
- [x] U.29 **Validate:** `client_instructions` visible when set. Diff on superseded v1 vs v2 is not a dump of every field vs v3. Click owner → Agents tab on that agent. "View all" lands on Request log filtered to `crm_search`. Withdraw sits in a labeled danger zone and asks for confirm (do not confirm on a live action).

## Enrollments

- [x] U.30 Move pending-version approvals off this tab (Directory + stats is enough). Guard `payload.description[:120]` against missing description. Same notes field on approve and reject; visible labels, not placeholder-only.
- [x] U.31 **Validate:** Enrollments tab is the enrollment queue only. Directory still has a path to approve a submitted version. A pending enrollment (throwaway) can be approved/rejected with notes; stats and queue update together.
- [x] U.32 Recently decided enrollments; filter/paginate by action, client, state; row links to action + client agent; Reset UI for rejected enrollments (`POST /admin/enrollment/<id>/reset`).
- [x] U.33 **Validate:** after rejecting a throwaway enrollment, it appears under recently decided with actor + time. Reset makes it requestable again. Links open the right action/agent.

## Agents

- [x] U.34 Delivery form: `data-show` actually hides protocol-specific fields (exec must not show Endpoint URL + five header rows). Header rows honor `headerRows`. Retries/Timeout placeholders are not clipped (`config default` fully visible, or drop the placeholder).
- [x] U.35 **Validate:** open `crm` (exec). Only Command + retries/timeout (and Delivery method) are visible. Switch the dropdown to HTTP POST → endpoint/headers appear, command hides. Completions → endpoint + model. Switch back to exec → POST fields gone. Header "+ header" / remove shows 1 row by default, up to 5.
- [x] U.36 Register validation: required name; at least one of client/provider; inline error on 400. Disable Register until valid. After register, pin the key reveal **above** the table until dismissed.
- [x] U.37 Key flows: New key always patches `#agent-detail-region` (works even if detail was never opened). Copy control on the one-time key. Revoke / New key are real buttons (danger vs outline; no `text-body-secondary` on danger). Confirms from U.10. Do not swallow the secret.
- [x] U.38 **Validate:** Register with empty name → inline error, no 400 no-op. Register throwaway client-only agent → key shown once at top with copy; Back/dismiss returns to the list; key cannot be retrieved again. New key on that throwaway **without** opening detail first still reveals the key. Revoke on that throwaway asks for confirm; list shows revoked. Do not touch `crm` / `redmain` keys.
- [x] U.39 Agent list/detail polish: name as title, UUID small monospace + copy; no `href="#"`; unique checkbox labels when register + detail coexist; Prev/Next pagination; capability/status/key as badges; delivery summary (protocol + endpoint/command) and registration date on the list; register checkboxes look enabled.
- [x] U.40 **Validate:** click `crm` — heading is readable, tab hash intact. List shows `exec` (or similar) without opening detail. Paginate if > per_page. Open agent A then agent B: delivery fields are B's, not A's leftover signals.

## Request log

- [x] U.41 Apply shared filter toolbar + hash-safe Details/pagination (U.3/U.6). Preserve `action_id` / `outcome` across pages. `in_flight` stays selected after submit (do not clear `outcome` after mapping to multiple states). Consistent pagination footer with Directory.
- [x] U.42 **Validate:** filter outcome `completed` → only completed rows, dropdown still says completed, total matches. Filter `in_flight` then reload the partial — dropdown still shows in_flight. Paginate with a filter applied (or lower per_page in a test) without losing it.
- [x] U.43 Action cell links to Directory detail; agent cell links to Agents. Dispatch truncated with full value on `title`; `exec —` / `post —` render as not-dispatched. Label "Details" (not "detail"); Details adjacent to Outcome or whole-row open. Selected row highlighted; detail scrolls into view; close control.
- [x] U.44 **Validate:** click action `crm_search` → Directory on that action. Click agent `crm` → Agents on that agent. Long completions URL is truncated in the table but full on hover. Open Details on a row, close it, open another — highlight follows.

## Request detail

- [x] U.45 Title is action + outcome + when; UUID is small monospace. Persist and render JSON Schema errors for `request_schema_invalid`. Hide empty sections (no `—` plus an empty attempts table). Show response-arbiter verdict when present. Bound `<pre>` max-height. For `provider_failed`, lead with error class/detail.
- [x] U.46 **Validate:** open the `request_schema_invalid` row (`crm_search` / `redmain` / empty `{}` from the QA walkthrough, or a new throwaway). Schema errors are visible. Empty arbiter/response/attempts sections are omitted. A `provider_failed` row leads with the transport/schema failure, not "payload looks fine." A completed row still shows request + response payloads in scrollable pres. Close works.
- [x] U.47 Copy buttons on payloads; collapse empty attempt `<details>`.
- [x] U.48 **Validate:** copy on a small JSON payload actually copies. Attempts without a response do not show an empty response disclosure.

## Audit trail

- [x] U.49 Actor shows agent **name** (id secondary). Target shows type + name, no 12-char UUID crop. Detail is a one-line human summary; omit empty/`null` notes. Rows link to action/agent where they still exist. Pagination preserves `actor_id` / `target_type` and does not use `href="#"`.
- [x] U.50 Filter by name (not only UUID / literal `admin`). Default view is lifecycle events (approvals, enrollments, agent/key changes); `request.invoked` is opt-in or a separate filter. Human event labels with machine name on `title`.
- [x] U.51 **Validate:** filter actor `admin` (by name) → only admin rows, names not raw UUIDs. Click a `crm` / `redmain` target → corresponding Agents/Directory view. Default list is not a wall of `request.invoked`. Paginate with the filter still applied. Empty notes do not render as `{"notes": ""}`.

## Cross-cutting QA

- [ ] U.52 **Validate (full pass):** login → every tab → open one detail on Directory, Agents, Request log, Audit → log out. Stats present the whole time. No "Loading stats…". No `/admin#` hash wipe. Desktop and ~390px. Throwaway agent leftover from U.38 can be left disabled.
- [ ] U.53 **Validate (spec checklist):** stats bar live; Directory filter totals correct; invocation detail from an action stays on that tab; version approve reachable without the Enrollments-tab queue; enrollment approve/reject + reset; admin-enroll from action detail; register key-once + copy; delivery fields hide by protocol; new-key reveal works from the list; request detail shows schema errors; audit is readable and linkable.

## Beyond the scope of this document

- Sticky table headers on very long logs (nice-to-have after U.6).
- Choosable page size (vs just consistent chrome in U.8).
- Owner/provider filter and sort on Directory; recent invocation **count** on each Directory row; inline Approve/Reject from the Directory row (U.22 flags pending; full inline actions can wait unless the ≤2-click path is still worse than opening detail).
- Time-range filters on Request log and Audit.
- Stage-decided column on the Request log (schema vs arbiter vs retries).
- `type="password"` + show toggle on delivery header values.
- Stopping `openWhenHidden` on the agents partial (performance only).
- Mutating live `crm` / `redmain` keys or withdrawing live actions.
- The old A2A admin under `templates/admin/`.
