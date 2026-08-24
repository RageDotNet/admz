# LLM DMZ

A demilitarized zone (DMZ) between an **untrusted external agent** and a **trusted internal agent**. The two sides never talk directly. All communication passes through a schema-validated, LLM-arbitrated gateway with persistent queues and a human review path for anything suspicious.

**Why we built this:** keep agents with external reach (internet, customers) separate from agents with internal confidential systems — and still let them call each other both ways through a neutral boundary. The DMZ breaks the [lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) path with schemas, an LLM arbiter, and human-approved enrollment. See [Why We Built This](docs/why-we-built-this.md) for the problem statement, benefits, human vs agent usage, and how this relates to sandboxes (NemoClaw), session policy engines (Omnigent), and MCP proxies (Open Edison). The v2 product direction is a directory-driven sync broker; see [docs/index-v2.md](docs/index-v2.md).

The project provides **two gateway entry points** that share the same core (`dmz/` package, SQLite storage, schema registry, LLM arbiter, and review queue):

| Gateway | Entry point | Protocol | Validation | Default port |
|---------|-------------|----------|------------|--------------|
| **REST DMZ** | `llmdmz.py` | HTTP REST + Celery | Async (background worker) | 8080 |
| **A2A DMZ** | `a2admz.py` | Agent-to-Agent ([`python-a2a`](https://pypi.org/project/python-a2a/)) | Synchronous (in-process) | 5000 |

Both gateways read the same `config/agents.json`, `config/schemas.json`, and `data/dmz.db`.

---

## Architecture

### REST gateway (`llmdmz.py`)

```
                    ┌─────────────────────────────────────────┐
                    │              llmdmz.py (Flask)           │
                    │                                         │
  ext_agent         │  submit request ──► validate schema     │         int_agent
  (untrusted)       │         │          LLM arbiter (attack?)  │         (trusted)
       │            │         ▼                               │              │
       │            │   requestee queue ◄──── poll ───────────┼──────────────┤
       │            │         │                               │              │
       │            │         └──────► submit response        │◄─────────────┘
       │            │                    validate schema       │
       │            │                    LLM arbiter (exfil?)   │
       │            │                         │                 │
       │            │   response queue ◄──── poll               │
       │            │                                         │
       │            │   review queue ◄── schema/arbiter fail  │
       └────────────┤         ▲                               │
                    │  reviewer (CLI / API) approve/reject   │
                    └─────────────────────────────────────────┘
                              ▲
                              │ Celery worker (async validation)
```

### A2A gateway (`a2admz.py`)

```
  ext_agent (A2A)          a2admz.py (A2A proxy)          a2a_requestee.py (A2A)
       │                         │                                │
       │  A2A task/send          │  schema + arbiter (sync)       │  fulfill schema
       └────────────────────────►│───────────────────────────────►│
                                 │◄───────────────────────────────┘
                                 │  schema + arbiter on response
       ◄─────────────────────────┘
       A2A completed task

  reviewer ──► /admin (web UI)  or  /api/v1/review/*  or  review_cli.py
```

The A2A requestee (`a2a_requestee.py`) is the trusted internal agent that fulfills schema operations (CRM search, add note, etc.) when the gateway forwards work over A2A.

---

## Concepts

| Role | Agent | Has access to |
|------|-------|---------------|
| **Requestor** | `ext_agent` | Outside world (email). Submits requests, polls responses. |
| **Requestee** | `int_agent` | Private data (CRM). Fulfills requests (A2A) or polls/submits via REST. |
| **Reviewer** | `reviewer1` | Human oversight. Approves or rejects flagged items via admin UI, REST API, or CLI. |

Each interaction is defined by a **schema pair** (request + response JSON Schema). The requestor and requestee are bound to a schema by ID. Every request carries its own `request_id`.

Validation pipeline for every request and response:

1. **JSON Schema** validation (via `jsonschema` + `dydantic`)
2. **LLM arbiter** check (via LiteLLM / OpenRouter)
3. On failure → **human review queue** (approve to continue, reject to block)

---

## Registered schemas

Configured in `config/schemas.json`. Both are bound to `ext_agent` → `int_agent`.

| Schema ID | Description | A2A requestee handler |
|-----------|-------------|----------------------|
| `crm_search` | Search CRM contacts by name and/or company | `fulfill_crm_search()` |
| `crm_add_note` | Append a note to an existing CRM contact | `fulfill_crm_add_note()` |

See [Schema reference](#schema-reference) below for payload shapes.

---

## Project layout

```
llmdmz/
├── llmdmz.py                    # Flask REST DMZ HTTP service
├── a2admz.py                    # A2A protocol DMZ gateway/proxy
├── a2a_requestee.py             # Trusted internal A2A requestee (CRM fulfillment)
├── a2a_client_example.py        # Example A2A requestor client
├── a2a_client_nefarious_example.py  # Test client for human review queue
├── int_llm.py                   # Trusted internal LLM agent (CRM tools)
├── ext_llm.py                   # Untrusted external LLM agent (email tools)
├── crmtool.py                   # Mock CRM (flat-file JSON)
├── emailtool.py                 # Mock email inbox/outbox
├── review_cli.py                # Human reviewer CLI
├── llm_logging.py               # Shared logging helpers
├── pytest.ini                   # Pytest configuration
├── dmz/                         # Shared DMZ internals
│   ├── agents.py                # Agent ID + key authentication
│   ├── admin_routes.py          # A2A admin web UI routes
│   ├── a2a_protocol.py          # A2A envelope helpers
│   ├── arbiter.py               # LLM security checks
│   ├── celery_app.py            # Celery configuration
│   ├── config.py                # Load agents.json / schemas.json
│   ├── review_routes.py         # Shared review REST API routes
│   ├── schemas.py               # Schema registry (dydantic + jsonschema)
│   ├── storage.py               # SQLite queue persistence
│   └── tasks.py                 # Celery validation tasks (REST gateway)
├── templates/admin/             # A2A admin web UI (0build + Datastar)
├── config/
│   ├── agents.json              # Agent IDs, keys, roles
│   └── schemas.json             # Schema bindings (multi-schema registry)
├── schemas/
│   ├── crm_search_request.json
│   ├── crm_search_response.json
│   ├── crm_add_note_request.json
│   └── crm_add_note_response.json
├── tests/                       # Offline test suite (86 tests)
├── data/                        # Runtime data (created on first run, gitignored)
│   ├── crm.json                 # CRM contacts
│   ├── dmz.db                   # Request/response/review queue
│   ├── celery_broker.db         # Celery message broker (REST only)
│   └── celery_results.db        # Celery task results (REST only)
├── emails/                      # Mock inbox (gitignored)
├── emails_out/                  # Mock sent mail (gitignored)
├── .env                         # API keys (not committed)
└── requirements.txt
```

---

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-v1-...

# Optional overrides
LOG_LEVEL=INFO

# REST DMZ (llmdmz.py)
LLMDMZ_HOST=127.0.0.1
LLMDMZ_PORT=8080
LLMDMZ_URL=http://127.0.0.1:8080

# A2A DMZ (a2admz.py)
A2A_DMZ_HOST=127.0.0.1
A2A_DMZ_PORT=5000
A2A_DMZ_URL=http://127.0.0.1:5000
A2A_REQUESTOR_ID=ext_agent
A2A_REQUESTOR_KEY=ext-dev-key-change-me

# A2A requestee (a2a_requestee.py)
A2A_REQUESTEE_HOST=127.0.0.1
A2A_REQUESTEE_PORT=5001
A2A_REQUESTEE_URL=http://127.0.0.1:5001

# LLM arbiter
ARBITER_MODEL=openrouter/openai/gpt-oss-120b:free

# Celery (REST gateway only)
CELERY_BROKER_URL=sqla+sqlite:///data/celery_broker.db
CELERY_RESULT_BACKEND=db+sqlite:///data/celery_results.db

# Admin UI session signing (a2admz.py)
FLASK_SECRET_KEY=change-me-in-production

# Review CLI defaults (optional)
REVIEWER_AGENT_ID=reviewer1
REVIEWER_AGENT_KEY=review-dev-key-change-me
```

### 3. Configure agents and schemas

**`config/agents.json`** — each agent has an `id`, `key`, and `role` (`requestor`, `requestee`, or `reviewer`):

```json
{
  "agents": [
    { "id": "ext_agent",  "key": "ext-dev-key-change-me",    "role": "requestor" },
    { "id": "int_agent",  "key": "int-dev-key-change-me",    "role": "requestee" },
    { "id": "reviewer1",  "key": "review-dev-key-change-me", "role": "reviewer" }
  ]
}
```

**`config/schemas.json`** — maps schema pairs to requestor/requestee. For A2A, include `requestee_a2a_url`:

```json
{
  "schemas": [
    {
      "id": "crm_search",
      "description": "Search CRM contacts by name or company",
      "request_schema": "schemas/crm_search_request.json",
      "response_schema": "schemas/crm_search_response.json",
      "requestor_id": "ext_agent",
      "requestee_id": "int_agent",
      "requestee_a2a_url": "http://127.0.0.1:5001"
    },
    {
      "id": "crm_add_note",
      "description": "Append a note to a CRM contact record",
      "request_schema": "schemas/crm_add_note_request.json",
      "response_schema": "schemas/crm_add_note_response.json",
      "requestor_id": "ext_agent",
      "requestee_id": "int_agent",
      "requestee_a2a_url": "http://127.0.0.1:5001"
    }
  ]
}
```

---

## Running the REST gateway

Three processes for the full REST DMZ flow:

### Terminal 1 — Celery worker (async validation)

```bash
celery -A dmz.celery_app.celery_app worker --loglevel=info
```

### Terminal 2 — REST DMZ server

```bash
python llmdmz.py
```

Listens on `http://127.0.0.1:8080` by default. Exposes the review API at `/api/v1/review/*`.

### Terminal 3 — LLM agents (optional, for interactive use)

```bash
python int_llm.py    # Trusted internal agent (CRM)
python ext_llm.py    # Untrusted external agent (email)
```

Both agents use LiteLLM with OpenRouter. Default model: `openrouter/openai/gpt-oss-120b:free`.

---

## Running the A2A gateway

Two processes for the A2A stack:

### Terminal 1 — trusted requestee

```bash
python a2a_requestee.py
```

Listens on `http://127.0.0.1:5001` by default. Implements CRM schema handlers (`crm_search`, `crm_add_note`).

### Terminal 2 — A2A DMZ gateway

```bash
python a2admz.py
```

Listens on `http://127.0.0.1:5000` by default. Also exposes:

- Human review REST API at `/api/v1/review/*`
- Admin web UI at `/admin`
- A2A endpoint at `/a2a/tasks/send`

**Development note:** `a2admz.py` runs with `FLASK_DEBUG=0` by default, so Jinja2 templates are cached. After editing files under `templates/`, restart the gateway process (a browser hard-refresh alone is not enough).

---

## A2A gateway details

### Admin web UI (`/admin`)

Browser-based dashboard built with [0build](https://github.com/0builddotdev/0build) and [Datastar](https://data-star.dev/) for live updates without custom JavaScript.

Open `http://127.0.0.1:5000/admin` and sign in with a **reviewer** agent from `config/agents.json` (default: `reviewer1` / `review-dev-key-change-me`).

| Tab | Purpose |
|-----|---------|
| **Review queue** | Approve or reject requests flagged by schema validation or the LLM arbiter |
| **In-flight** | Requests currently being validated, forwarded, or awaiting review (auto-refreshes every 3s) |
| **Access log** | Completed and historical requests |
| **Schemas** | Registered operations, agent bindings, A2A URLs, and JSON Schema definitions |

Features:

- Compact stats bar (schemas, in-flight, pending review, total requests)
- Tab clicks refresh content via Datastar (no full page reload required)
- Inline request details below the selected row/card; toggle Details to expand/collapse
- Reviewer session auth via Flask cookie (`FLASK_SECRET_KEY`)

### A2A request envelope

Requestors send an A2A task with a `llmdmz` envelope in `metadata` or message data:

```json
{
  "llmdmz": {
    "schema_id": "crm_search",
    "request_id": "a2a-req-001",
    "payload": { "company": "Acme Corp" }
  }
}
```

Authenticate with headers:

```
X-Agent-Id:  ext_agent
X-Agent-Key: ext-dev-key-change-me
```

### Example A2A clients

**Normal requests:**

```bash
python a2a_client_example.py crm_search
python a2a_client_example.py crm_add_note
```

**Exercise human review** (submits payloads designed to fail validation or arbiter checks):

```bash
python a2a_client_nefarious_example.py schema      # invalid payload → schema review
python a2a_client_nefarious_example.py injection   # prompt injection → arbiter review
python a2a_client_nefarious_example.py exfil       # over-broad request → arbiter review
```

Then inspect the **Review queue** tab in the admin UI or use `review_cli.py`.

**From Python:**

```python
from python_a2a import A2AClient, Task

envelope = {
    "llmdmz": {
        "schema_id": "crm_add_note",
        "request_id": "a2a-req-002",
        "payload": {"contact_id": "c001", "note": "Follow-up scheduled."},
    }
}
task = Task(id="a2a-req-002", metadata=envelope)
client = A2AClient(
    "http://127.0.0.1:5000",
    headers={"X-Agent-Id": "ext_agent", "X-Agent-Key": "ext-dev-key-change-me"},
    google_a2a_compatible=True,
)
result = client._send_task(task)
```

### A2A gateway flow

1. Requestor submits A2A task to `a2admz.py`
2. Gateway validates request schema + LLM malicious-content check (synchronous)
3. On pass, forwards to requestee A2A URL (`requestee_a2a_url` in `config/schemas.json`)
4. Requestee fulfills the schema operation and returns `response_payload`
5. Gateway validates response schema + LLM exfiltration check
6. On pass, returns completed A2A task to requestor

If validation fails at either stage, the task returns `input-required` with a review ID. Approve via the admin UI, `review_cli.py` (point `--base-url` at the gateway), or the review REST API, then resubmit the same `request_id`.

### A2A environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `A2A_DMZ_HOST` | `127.0.0.1` | Gateway bind host |
| `A2A_DMZ_PORT` | `5000` | Gateway bind port |
| `A2A_DMZ_URL` | `http://127.0.0.1:5000` | Gateway public URL (agent card) |
| `A2A_REQUESTOR_ID` | `ext_agent` | Default client example agent ID |
| `A2A_REQUESTOR_KEY` | (from config) | Default client example agent key |
| `FLASK_SECRET_KEY` | dev default | Signs admin UI session cookies |
| `A2A_REQUESTEE_HOST` | `127.0.0.1` | Requestee bind host |
| `A2A_REQUESTEE_PORT` | `5001` | Requestee bind port |
| `A2A_REQUESTEE_URL` | `http://127.0.0.1:5001` | Requestee public URL |
| `FLASK_DEBUG` | `0` | Set to `1` to enable Flask debug mode (auto-reloads templates) |

---

## REST DMZ HTTP API

All authenticated endpoints require headers:

```
X-Agent-Id:  <agent id>
X-Agent-Key: <agent secret key>
```

### Health

```
GET /health
```

No auth required. Returns `{"status": "ok"}`.

### List schemas

```
GET /api/v1/schemas
```

Returns all registered schema bindings.

### Submit a request (requestor)

```
POST /api/v1/requests
```

```json
{
  "schema_id": "crm_search",
  "request_id": "req-abc123",
  "payload": { "company": "Acme Corp" }
}
```

Returns `202 Accepted`. Validation runs asynchronously via Celery.

### Poll for work (requestee)

```
GET /api/v1/requests/poll?limit=10
```

Returns pending requests and marks them `in_progress`.

### Submit a response (requestee)

```
POST /api/v1/requests/{request_id}/response
```

```json
{
  "payload": {
    "records": [
      {
        "id": "c001",
        "name": "Jane Smith",
        "email": "jane.smith@acmecorp.com",
        "company": "Acme Corp",
        "phone": "+1-555-0101",
        "status": "active",
        "notes": "Enterprise renewal due Q3."
      }
    ]
  }
}
```

Returns `202 Accepted`. Response validation runs asynchronously.

### Poll for responses (requestor)

```
GET /api/v1/responses/poll?limit=10
```

Returns completed responses and marks them `delivered`.

### Check request status

```
GET /api/v1/requests/{request_id}
```

Accessible by the requestor, requestee, or a reviewer.

### Human review (reviewer)

Available on both `llmdmz.py` (port 8080) and `a2admz.py` (port 5000):

```
GET  /api/v1/review/pending?limit=50
POST /api/v1/review/{review_id}/approve   {"notes": "optional reason"}
POST /api/v1/review/{review_id}/reject    {"notes": "optional reason"}
```

---

## Request lifecycle

| Status | Meaning |
|--------|---------|
| `validating` | Request just submitted; schema + arbiter check in progress |
| `pending_requestee` | Passed validation; waiting for requestee to pick up / be forwarded |
| `in_progress` | Requestee polled and claimed the request (REST) |
| `validating_response` | Response submitted; schema + arbiter check in progress |
| `completed` | Response approved; waiting for requestor to poll |
| `delivered` | Requestor polled the response (REST) |
| `pending_review_request` | Request failed validation/arbiter; needs human review |
| `pending_review_response` | Response failed validation/arbiter; needs human review |
| `rejected` | Human reviewer rejected, or terminal failure |

### Flow diagram (REST)

```
requestor POST /requests
        │
        ▼
   validating ──► schema fail ──► pending_review_request ──► approve ──► pending_requestee
        │                              │                         reject ──► rejected
        ▼                              │
   LLM arbiter ──► reject ──────────────┘
        │
        ▼ approve
   pending_requestee
        │
        ▼ requestee poll
   in_progress
        │
        ▼ requestee POST /response
   validating_response
        │
        ▼
   (same pattern for response)
        │
        ▼ approve
   completed ──► requestor poll ──► delivered
```

The A2A gateway follows the same status model but validates synchronously and forwards to the A2A requestee instead of using poll/submit endpoints.

---

## Schema reference

### `crm_search`

**Request** (`schemas/crm_search_request.json`) — query by **name**, **company**, or both. At least one is required.

```json
{ "name": "Jane Smith" }
{ "company": "Acme Corp" }
{ "name": "Jane", "company": "Acme Corp" }
```

**Response** (`schemas/crm_search_response.json`) — always includes a `records` array (empty when nothing matched):

```json
{
  "records": [
    {
      "id": "c001",
      "name": "Jane Smith",
      "email": "jane.smith@acmecorp.com",
      "company": "Acme Corp",
      "phone": "+1-555-0101",
      "status": "active",
      "notes": "Enterprise renewal due Q3. Primary decision maker."
    }
  ]
}
```

### `crm_add_note`

**Request** (`schemas/crm_add_note_request.json`):

```json
{
  "contact_id": "c001",
  "note": "Follow-up call scheduled for next week."
}
```

**Response** (`schemas/crm_add_note_response.json`) — the updated contact record:

```json
{
  "record": {
    "id": "c001",
    "name": "Jane Smith",
    "email": "jane.smith@acmecorp.com",
    "company": "Acme Corp",
    "phone": "+1-555-0101",
    "status": "active",
    "notes": "Enterprise renewal due Q3. Primary decision maker.\nFollow-up call scheduled for next week."
  }
}
```

### Contact record fields

Contact `status` must be one of: `active`, `lead`, `churned`.

Schemas are loaded with **dydantic** (`create_model_from_schema`) and validated with **jsonschema** for constraints like `anyOf`.

---

## LLM agents

### Internal agent — `int_llm.py`

Trusted agent with access to private CRM data via `crmtool.py`.

```bash
python int_llm.py
python int_llm.py "Who works at Acme Corp?"
```

**CRM tools available to the model:**

| Tool | Description |
|------|-------------|
| `list_contacts` | List all CRM contacts |
| `get_contact` | Get contact by ID (`c001`, etc.) |
| `search_contacts` | Text search across name, email, company, status, notes |
| `add_contact_note` | Append a note to a contact |

CRM data is stored in `data/crm.json` (seeded with 4 mock contacts on first run).

### External agent — `ext_llm.py`

Untrusted agent with access to mock email via `emailtool.py`.

```bash
python ext_llm.py
python ext_llm.py "Check for new email and summarize it."
```

**Email tools available to the model:**

| Tool | Description |
|------|-------------|
| `get_new_emails` | Return unread inbox messages (marks them seen) |
| `list_inbox` | List all inbox messages |
| `get_email` | Read one message by filename |
| `send_email` | Write a mock sent message to `emails_out/` |

Inbox messages live in `emails/` (3 seeded on first run). Sent mail is written to `emails_out/` as `{timestamp}_{subject}.txt`.

---

## Human review

Flagged requests/responses can be reviewed three ways:

### Admin web UI (A2A gateway only)

`http://127.0.0.1:5000/admin` — sign in as `reviewer1`. See [Admin web UI](#admin-web-ui-admin) above.

### Review CLI

`review_cli.py` works against either gateway:

```bash
# REST gateway (default base URL)
python review_cli.py list
python review_cli.py show req-abc123
python review_cli.py approve <review_id> --notes "looks legitimate"
python review_cli.py reject <review_id> --notes "blocked"

# A2A gateway
python review_cli.py --base-url http://127.0.0.1:5000 list
```

Override credentials with `--agent-id` and `--agent-key`.

### Review REST API

`GET /api/v1/review/pending`, `POST /api/v1/review/{id}/approve`, `POST /api/v1/review/{id}/reject` — see [REST DMZ HTTP API](#rest-dmz-http-api).

---

## LLM arbiter

The arbiter (`dmz/arbiter.py`) uses LiteLLM to call OpenRouter and returns a JSON verdict:

```json
{ "approved": true, "reason": "..." }
```

**Request check** looks for prompt injection, hidden instructions, unrelated sensitive operations, and social engineering.

**Response check** looks for data exfiltration, bulk dumps, unjustified credentials/notes, and encoded leakage.

Override the model with `ARBITER_MODEL` in `.env`.

---

## Logging

Services log to **stderr** using Python's `logging` module under the `llmdmz.*` namespace.

| Logger | Source |
|--------|--------|
| `llmdmz.int_llm` | Internal LLM agent |
| `llmdmz.ext_llm` | External LLM agent |
| `llmdmz.server` | REST Flask DMZ |
| `llmdmz.a2admz` | A2A DMZ gateway |
| `llmdmz.a2a_requestee` | A2A requestee |
| `llmdmz.admin` | Admin web UI |
| `llmdmz.arbiter` | LLM security checks |
| `llmdmz.tasks` | Celery validation tasks |

```bash
LOG_LEVEL=DEBUG python a2admz.py
```

---

## Examples

### REST: end-to-end CRM search via curl

Start Celery and `llmdmz.py` first:

```bash
curl -s -X POST http://127.0.0.1:8080/api/v1/requests \
  -H "X-Agent-Id: ext_agent" \
  -H "X-Agent-Key: ext-dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": "crm_search",
    "request_id": "req-demo-001",
    "payload": { "company": "Acme Corp" }
  }'
```

Poll status, requestee work, submit response, and requestor poll — see flow in prior sections or use the test suite as reference.

### A2A: CRM search and add note

Start `a2a_requestee.py` and `a2admz.py`, then:

```bash
python a2a_client_example.py crm_search
python a2a_client_example.py crm_add_note
```

---

## Adding a new schema

### 1. Write JSON Schema files

Create request and response schemas under `schemas/`.

### 2. Register in config

Add a binding to `config/schemas.json` with the correct `requestor_id`, `requestee_id`, and (for A2A) `requestee_a2a_url`.

### 3. Implement requestee fulfillment

| Gateway | What to implement |
|---------|-------------------|
| **A2A** | Add a handler in `a2a_requestee.py` `HANDLERS` dict |
| **REST** | Requestee (`int_agent`) must poll `/api/v1/requests/poll`, fulfill the operation, and POST the response — typically by wrapping `int_llm.py` or custom code |

### 4. Restart services

- **REST:** restart `llmdmz.py` and the Celery worker
- **A2A:** restart `a2admz.py` and `a2a_requestee.py`
- **Admin UI templates:** restart `a2admz.py` (templates cached when `FLASK_DEBUG=0`)

No changes to gateway core code are required beyond the requestee handler — the schema registry loads all bindings at startup.

---

## Testing

The test suite runs fully offline (86 tests). LLM arbiter calls and A2A requestee forwarding are mocked — no network access required.

```bash
pip install -r requirements.txt
pytest
```

Coverage includes:

| Area | Tests |
|------|-------|
| **Storage** | Queue, polling, list/inflight queries, review approve/reject |
| **Schemas** | Valid/invalid payloads for `crm_search` and `crm_add_note` |
| **Agents** | Authentication and role checks |
| **Arbiter** | Mocked LiteLLM verdict parsing |
| **Celery tasks** | Synchronous `process_request` / `process_response` pipeline |
| **`llmdmz.py`** | Full REST API flow, auth errors, review queue |
| **`a2admz.py`** | A2A gateway success/failure paths, HTTP `/a2a/tasks/send`, review API |
| **`a2a_requestee.py`** | CRM schema handlers |
| **Admin UI** | Login, partials, review actions, auth guards |
| **A2A protocol** | Envelope extraction and task building |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `dydantic` | Build Pydantic models from JSON Schema |
| `litellm` | LLM calls (agents + arbiter) via OpenRouter |
| `python-dotenv` | Load `.env` |
| `flask` | DMZ HTTP servers |
| `celery` | Async validation queue (REST gateway) |
| `sqlalchemy` | Celery SQLite broker/backend |
| `email-validator` | Required by dydantic for `format: email` |
| `requests` | Review CLI HTTP client |
| `python-a2a[server]` | A2A protocol gateway and requestee |
| `pytest` | Test suite |

Admin UI front-end assets (0build, Datastar) are loaded from CDN — no npm build step.

---

## Security notes (development)

- Default agent keys in `config/agents.json` are placeholders. Change them before any real deployment.
- Set `FLASK_SECRET_KEY` in production for admin UI session signing.
- `.env` is gitignored and must contain your OpenRouter API key.
- The arbiter is a best-effort LLM check, not a guarantee. Human review is the backstop.
- `int_llm.py` and `ext_llm.py` are standalone REPL demos; they do not auto-integrate with either gateway. In production, requestors/requestees would be processes that call the REST or A2A APIs.
- `llmdmz.py` and `a2admz.py` are independent entry points sharing storage and config — run one or both depending on your integration needs.
