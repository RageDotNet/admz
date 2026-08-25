# Admin console UI QA

Walkthrough of `http://localhost:8000/admin` on 2026-08-24 against the live `dmz-serve` instance. Logged in as `admin`. No mutations were submitted (no approve/reject/revoke/withdraw/new-key/save) so this is observational plus a few safe filters and failed logins.

This is a punch list for a UI improvement pass. Items are grouped by severity, then by screen. Each item is a change to make, not a narrative.

## Severity

- **Blocker** — broken or misleading; the console cannot be trusted for that task.
- **Fix** — visible bug, wrong data, or silent failure.
- **Cleanup** — inconsistency, leftover, or polish that makes the UI look unfinished.
- **Improve** — product/UX gap (including gaps vs `webui-v2.md`).

## Suggested pass order

Do these first; they change how almost every later screen should be built:

1. Shell: stats bar fetch, header/nav, filter toolbar pattern, timestamps, badges, table-responsive.
2. Deep-link / `href="#"` hash handling so tabs and details stop fighting the URL.
3. Shared detail pattern (inline, closeable, correct patch target per tab).
4. Directory + action detail.
5. Agents + delivery form (show/hide, validation, key reveal).
6. Request log + request detail (including schema errors).
7. Enrollments + audit.

---

## Shell (every page)

### Blocker

- Stats bar never loads. Dashboard renders `partials/stats_placeholder.html` ("Loading stats…") and never `GET /admin/partials/stats`. The placeholder stays forever. Wire `data-init` (and refresh-after-mutation already exists on some POSTs).

### Fix

- Tab `<a href="#directory">` etc. plus row links with `href="#"` fight each other. Clicking an action/agent/request/pagination link sets the URL to `/admin#`, which drops the tab hash and can make the active tab look unselected even though `$tab` is unchanged. Use `href` that matches the tab, or `button`/`role=tab` with no hash, and keep `$tab` in sync with the hash on load so refresh/deep-link works.
- Log out sits inside `role="tablist"`. It is not a tab. Move it out of the tablist (header/navbar).
- Tabs are not real tabs: missing `aria-selected`, no keyboard left/right, `$tab` is not restored from `#hash` on first paint.

### Cleanup

- Page chrome is a bare `<h1>` + tab links. Add a compact header: title, signed-in admin, theme control, log out. Do not put the username on the Log out button (`Log out (admin)`).
- Dark mode is applied from `localStorage` / `prefers-color-scheme` with no toggle and no way to override. Either add a light/dark control or drop the unused init.
- No favicon.
- Document title stays "Agent DMZ" on every tab.
- Leftover comment in `admin.py` still talks about the 0build kit.
- Duplicate Bootstrap classes on Prev/Next: `btn btn-sm btn-outline-secondary btn btn-sm btn-outline-secondary`.
- Non-Bootstrap class `mono` (agent UUID). Use `font-monospace`.
- Filter toolbars (`form-control` + `form-select` with no width) each take 100% of the container, so search, dropdown, and Filter stack as three full-width rows. Constrain with `w-auto` / `style="max-width: …"` / `flex-grow-0` so they sit on one row.
- Filter inputs are placeholder-only (no `<label>`). Screen readers announce "filter by id/state", "action id", "actor id".
- No `table-responsive` wrapper. On a ~390px viewport the Directory table clips the last column ("Enrolled" → "En…") and grows a horizontal scrollbar.
- Nav links wrap poorly on mobile; Log out collides with the tab row.
- Empty states are a single muted table row. Fine for v1, but they look like a broken table (full-width grey bar, headers still showing unused columns).

### Improve

- Human timestamps: drop microseconds, show timezone or local time, use relative time for recent rows ("2h ago") with full time on hover/title.
- Human labels for states/outcomes (`Active`, `Provider failed`) instead of raw snake_case in badges and filters.
- Shared badge map is already there (`state_tag`); use it everywhere. Post-approve SSE patches use `<span class="badge active">` / `rejected` / `withdrawn` which are not Bootstrap 5 badge classes (`text-bg-*`).
- Confirm destructive actions (revoke key, withdraw action, revoke enrollment). Today they are one click with no undo copy.
- Loading/error for Datastar fetches. Directory has `data-indicator="loading"` but nothing visible uses it. Failed POSTs (400/404) are silent.
- Sticky table header on long logs.
- Per-page size shown as "50/page" even when there are 3 rows; either hide when one page, or make page size choosable.

---

## Login

### Fix

- Username and password are not `required`. Empty submit posts and comes back as "Invalid username or password." Distinguish empty vs wrong credentials.
- Failed login clears the username. Keep the username, clear only the password, and refocus the password field.
- Error alert uses `alert alert-danger py-2` as a `<p>`. Use a real alert (`role="alert"`) so it is announced.

### Cleanup

- Login button is left-aligned and short. Full-width (or at least `w-100` on the form) matches the card.
- No autofocus on Username.
- Card has no shadow / `mb-0` title hierarchy; heading is an `h1.h4` which is fine, but the page feels like a default Bootstrap example.
- "Log in" vs dashboard "Log out" vs older A2A templates "Sign in" — pick one verb pair.

### Improve

- Show a one-line product name + "Admin" rather than repeating "Agent DMZ — Admin Login" as both `<title>` and `h1`.

---

## Directory

### Fix

- State filter is applied in Python *after* pagination (`list_actions` then `[a for a in actions if a.state == state]`). Filtering to `withdrawn` showed "No actions." while the footer still said "3 total — page 1 (50/page)". Filter in the query; `total` must match the visible set.
- Search placeholder says "filter by id/state" but state is a separate `<select>`. Search is by id (and maybe description); say so.
- Pagination `Prev`/`Next` drop `q` and `state`. Preserve filters in the query string.
- Clicking an action uses `href="#"` so the page jumps to the top and the hash is wiped. Detail then appears *below* the table with no scroll-into-view and no selected-row highlight. Easy to miss that anything happened.
- No way to collapse/close action detail. Opening another action replaces `#action-detail`; filtering rebuilds the list and accidentally clears it. Add an explicit close.
- Duplicate DOM ids: directory row uses `id="action-{{ id }}-state"` and action detail uses the same id.

### Cleanup

- Action id is the only name shown. If a description exists, show it as secondary text so the table is scannable.
- Owner cell is blank if the owner agent is missing (`{{ row.owner.name if row.owner }}`). Show a fallback (id or "unknown").
- "Active ver." / "Pending ver." headers are cryptic. "Active" / "Pending" plus a version badge is enough.
- Pending versions are not visually flagged on the row (PRD: pending should stand out; inline approve/reject from the list is specified and missing).

### Improve (vs `webui-v2.md`)

- Filter by owner/provider; sort by name / recent activity.
- Recent invocation count on each row.
- Inline Approve/Reject for a pending version from the list row (≤2 clicks).
- Withdrawn rows should look withdrawn (muted row), not the same as active aside from the badge.

---

## Action detail

### Blocker

- "detail" on Recent invocations patches `#request-detail`, which only exists on the Request log tab. Clicking it from Directory does nothing on the current screen. The fragment lands on the hidden log tab, so later opening Request log shows a *stale* request that is not the first row. Patch a local `#action-request-detail` (or include the partial in this card).

### Fix

- `h2`/`h3`/`h4` in the card are unstyled browser headings (huge, tight). Use `h5`/`h6` or Bootstrap heading classes so the card does not overpower the page title.
- Definition list for instructions uses `col-sm-4` labels, so values sit far to the right with a large gap. Stack label-above-value, or use a narrower dt.
- `client_instructions` is a real payload field and is not shown. Show it next to `provider_instructions`.
- Version diffs print `request_risk: changed request_risk` (op + path repeating the field). Compact diffs; hide noise fields that are not in the "Active settings" summary, or show a real before/after.
- Diff is vs the *current active* version for every historical row (including superseded v1 vs v3). Prefer diff vs previous version, as the PRD says.
- Empty notes vs em dash is inconsistent (blank cell on v3 notes, "—" on diff).
- Last versions column has no header (approve/reject actions).
- "view JSON" `<details>` is easy to miss; JSON dumps are raw and unbounded in some `<pre>`s.
- Enrolled clients: no link to the agent, no decided-by/notes, no admin-enroll form (route `POST /admin/action/<id>/enroll` exists with no UI).
- Revoke and "Withdraw action (admin)" have no confirm. Withdraw sits at the very bottom after a long invocations table — easy to miss and easy to click by accident after scrolling. Put dangerous actions in a clearly labeled "Danger zone" with confirm.
- Recent invocations "Verdict" column always shows the *request* arbiter reason, including on `provider_failed` rows where that reason is "payload looks fine". Show the outcome-relevant reason (transport/schema/arbiter), or drop the column and keep it in detail.
- Invocations are capped at 20 with no "view all in Request log" link.

### Cleanup

- Card is a wall of tables. Section the three PRD blocks (definition/versions, access, invocations) with `nav-pills` or `<h3 class="h6 text-uppercase">`.
- Owner shown as `owner: crm` in muted small text; make it a link to the agent.
- Raw ISO-ish datetimes with microseconds on every row.

---

## Enrollments

### Fix

- "Pending version approvals" lives on this tab. Versions are not enrollments; they belong on Directory (with a badge/count in the stats bar). This tab should be the enrollment queue.
- Empty pending-version description uses `payload.description[:120]` with no guard if description is missing.
- Approve/Reject notes fields are unlabeled "notes" placeholders; reject on the enrollment queue has no notes field while approve does (versions have notes on both).
- After a decision, list refresh depends on SSE multi-patch. There is no in-tab feedback if the patch misses (and stats still never update because the stats target stays a placeholder).

### Improve (vs `webui-v2.md`)

- Recently decided enrollments (approved/rejected, who, when).
- Filter/paginate by action, client, state.
- Row links to action detail and to the client agent.
- Reset of a rejected enrollment (`POST /admin/enrollment/<id>/reset`) has no UI.

---

## Agents

### Blocker

- Delivery-method `data-show` is not hiding protocol-specific fields. Agent `crm` is `exec` (`python crm_provider.py run`) but the form still shows Endpoint URL, five empty header rows, and "+ header" above the Command field. Saving that form as-is could write leftover POST fields into `delivery_config` (or at least confuse the admin).
- All five header rows render even when `headerRows` should be 1. The "+ header" / remove controls are not doing the job.
- Retries / Timeout inputs are `max-width: 8rem` with placeholder "config default", which clips to "config" / "config d".

### Fix

- Register with empty name or with neither client nor provider: server `abort(400)`, UI does nothing. Client-side required name + "pick at least one capability", plus an inline error region for 400s.
- "New key" from a list row patches `#agent-{id}-detail`, which only exists after the agent was opened. Issuing a key without the detail card open can swallow the one-time secret. Always reveal in `#agent-detail-region` (same as register).
- "New key" button is unstyled (`class="small text-body-secondary"`) next to a red "Revoke key". Make both real buttons; Revoke = danger, New key = outline-secondary. Do not mute danger-button text with `text-body-secondary`.
- No confirm on Revoke key / New key.
- Key reveal has no copy control (PRD: copy affordance + shown-once warning). "Back to agents" is a GET that reloads the whole list.
- Agent heading dumps the full UUID at the same size as the name: `crm 784987f7-…`. Name as title, id as small monospace with copy.
- Clicking the agent name uses `href="#"` (same hash/tab problem as Directory).
- Duplicate accessible names: two "client" checkboxes (register form + detail) on the same page.
- Agents list has "4 total — page 1" and no Prev/Next at all.

### Cleanup

- Capabilities column is the string `client provider` with no separator or badges.
- Status is plaintext `enabled`/`disabled`; Key is plaintext `set`/`revoked`. Use badges.
- Register form checkboxes are cramped; labels are `small text-body-secondary` so they look disabled.
- Delivery summary in the list is missing (PRD: protocol + endpoint/command). Detail only says `configured (exec)`.
- Registration date is missing from the list.
- Header values are `type="text"` (Bearer tokens visible). Acceptable for an admin console; still consider `type="password"` with a show toggle for header values that look like secrets.
- `openWhenHidden: true` on the agents partial means the tab fetches even when you never open it. Fine for freshness; wasteful. Not a bug.

### Improve

- Disable Register until name + at least one capability.
- After register, keep the key reveal pinned at the top until dismissed; do not let it sit under the table.
- Editing another agent must not leak prior `edit_*` Datastar signals (code already sends `remove_signals`; verify in the UI after the delivery-fields show/hide fix).

---

## Request log

### Fix

- Same full-width stacked filters as Directory.
- Same `href="#"` on "detail" and pagination; detail appears below a long table with no scroll-into-view and no selected row.
- Action and agent cells are plain text. Link action → Directory detail, agent → Agents detail.
- Dispatch column is a dump (`completions https://very-long-url…`, `exec —`, `post —`). Truncate with title/tooltip; treat "protocol with no target" as "—" or "not dispatched".
- `in_flight` is a pseudo-filter that maps to several outcomes and then clears `outcome`, so the dropdown will not stay on `in_flight` after submit.
- Pagination does not preserve `action_id` / `outcome`.
- Footer omits `(50/page)` unlike Directory — pick one pagination chrome.

### Cleanup

- "detail" → "Details".
- Outcome badges are readable; still snake_case.
- Table is dense and the Details link sits far right of the badge, so scanning a row is hard. Consider making the whole row clickable or putting Details next to Outcome.

### Improve (vs `webui-v2.md`)

- Filters: client, provider, time range (not just action id + outcome).
- Show which stage decided (request schema / request arbiter / response schema / response arbiter / retries exhausted), not only the terminal outcome.

---

## Request detail

### Fix

- Title is `Request <uuid>`. Lead with action + outcome + when; put the id in small monospace.
- `request_schema_invalid` detail showed payload `{}`, arbiter `—`, response `—`, and an empty "Dispatch attempts (0)" table. **JSON Schema errors are not shown.** Persist and render them (PRD: exact schema failures). Hide empty sections instead of `—` plus an empty table.
- No response-arbiter verdict block (only request verdict).
- Payload `<pre>`s have no max-height/overflow on the main request/response (attempt framing does). Long payloads will blow the page.
- No close control; opening another request replaces the card but the previous row stays unhighlighted.

### Improve

- Copy buttons on payloads.
- Collapse empty attempt payload `<details>`.
- For `provider_failed`, lead with error class/detail, not the successful-looking request arbiter quote.

---

## Audit trail

### Fix

- Actor is `agent:<uuid>` or `admin:admin`. Show agent **name** (keep id in title or as secondary).
- Target is truncated to 12 chars (`agent/bc0eadba-ba1`, `enrollment/7907d539-a8e`). That is not unique enough to scan. Show name + type; do not crop UUIDs mid-string, or don't show them at all if you have a name.
- Detail is raw JSON (`{"notes": ""}`, `{"notes": null}`, `{"code": null, "status": 200}`). Render a one-line human summary; omit empty notes.
- Rows do not link to the action/agent (PRD).
- Filter "actor id" requires a UUID (or the literal `admin`). Filter by name too, or provide a picker.
- Pagination drops `actor_id` / `target_type` (after filtering to `admin`, paging would lose the filter — and Prev/Next use `href="#"`).
- `request.invoked` dominates the trail. The PRD describes a *state-change* log. Either split "traffic" out, or default the filter to lifecycle events (approvals, enrollments, agent/key changes) with an opt-in for invocations.

### Improve (vs `webui-v2.md`)

- Filter by time range.
- Event names as human text (`Approved enrollment`) with the machine name in `title`.

---

## Gaps vs `webui-v2.md` (checklist)

Present in the UI today, but incomplete or wrong:

| Spec | Status |
| --- | --- |
| Stats bar | Placeholder only; never fetched |
| Directory list + pagination | Yes; state filter totals are wrong; no owner filter/sort |
| Per-action detail | Yes; invocation detail is patched to the wrong tab |
| Version approve/reject | UI exists on Enrollments + in action detail; not on the Directory row |
| Enrollment queue approve/reject | Yes; no recently-decided, no filters |
| Admin-initiated enroll | Route only |
| Enrollment reset | Route only |
| Agents register + key once | Yes; no copy; empty submit is silent 400 |
| Agent edit + delivery config | Yes; protocol fields do not hide |
| Revoke / new key | Yes; new-key target is wrong if detail is closed; no confirm |
| Request log + detail | Yes; schema errors missing; filters incomplete |
| Audit trail | Yes; UUIDs, raw JSON, invocation noise |
| Deep links / no full reload | Partial; hashes and `$tab` disagree |
| Immediate stats refresh after decisions | Impossible until stats actually render |

---

## Accessibility notes

- Filter and notes fields are placeholder-only.
- Duplicate checkbox labels (client/provider) when register + detail are both on screen.
- Tablist contains a submit button (Log out).
- Many controls are `<a href="#">` that do not navigate; use buttons.
- Login error is not `role="alert"`.
- Color-only outcome meaning is OK because the badge also has text; keep it that way.
- Mobile: table overflow without `table-responsive`, small touch targets on tabs and Filter.

---

## Out of scope for this pass (called out so they are not forgotten)

- Do not mutate live keys/enrollments/actions while fixing UI; use a throwaway agent for key-reveal QA.
- Confirm `payload.description[:120]` against a version with a missing description (likely a 500).
- Confirm delivery-form save on an `exec` provider does not persist leftover `endpoint`/`headers` from the visible POST fields.
- Theme toggle vs "always light for the admin console" is a product choice; pick one.
- The old A2A console under `templates/admin/` is a different app. Do not mix its copy ("A2A DMZ", reviewer agent id) into this console.
