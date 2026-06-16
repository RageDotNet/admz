# LLM DMZ

A demilitarized zone (DMZ) between an **untrusted external agent** and a **trusted internal agent**. The two sides never talk directly. All communication passes through a schema-validated, LLM-arbitrated HTTP gateway with persistent queues and a human review path for anything suspicious.

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
                    │    reviewer (CLI) approve / reject       │
                    └─────────────────────────────────────────┘
```

## Concepts

| Role | Agent | Has access to |
|------|-------|---------------|
| **Requestor** | `ext_agent` | Outside world (email). Submits requests, polls responses. |
| **Requestee** | `int_agent` | Private data (CRM). Polls requests, posts responses. |
| **Reviewer** | `reviewer1` | Human oversight. Approves or rejects flagged items. |

Each interaction is defined by a **schema pair** (request + response JSON Schema). The requestor and requestee are bound to a schema by ID. Every request carries its own `request_id`.

Validation pipeline for every request and response:

1. **JSON Schema** validation (via `jsonschema` + `dydantic`)
2. **LLM arbiter** check (via LiteLLM / OpenRouter)
3. On failure → **human review queue** (approve to continue, reject to block)

---

## Project layout

```
llmdmz/
├── llmdmz.py              # Flask REST DMZ HTTP service
├── a2admz.py              # A2A protocol DMZ gateway/proxy (python-a2a)
├── a2a_requestee.py       # Trusted internal A2A requestee (CRM fulfillment)
├── a2a_client_example.py  # Example A2A requestor client
├── int_llm.py             # Trusted internal LLM agent (CRM tools)
├── ext_llm.py             # Untrusted external LLM agent (email tools)
├── crmtool.py             # Mock CRM (flat-file JSON)
├── emailtool.py           # Mock email inbox/outbox
├── review_cli.py          # Human reviewer CLI
├── llm_logging.py         # Shared logging helpers
├── dmz/                   # DMZ service internals
│   ├── agents.py          # Agent ID + key authentication
│   ├── arbiter.py         # LLM security checks
│   ├── celery_app.py      # Celery configuration
│   ├── config.py          # Load agents.json / schemas.json
│   ├── schemas.py         # Schema registry (dydantic + jsonschema)
│   ├── storage.py         # SQLite queue persistence
│   └── tasks.py           # Celery validation tasks
├── config/
│   ├── agents.json        # Agent IDs, keys, roles
│   └── schemas.json       # Schema bindings (multi-schema registry)
├── schemas/
│   ├── crm_search_request.json
│   └── crm_search_response.json
├── data/                  # Runtime data (created on first run)
│   ├── crm.json           # CRM contacts
│   ├── dmz.db             # Request/response/review queue
│   ├── celery_broker.db   # Celery message broker
│   └── celery_results.db  # Celery task results
├── emails/                # Mock inbox
├── emails_out/            # Mock sent mail
├── .env                   # API keys (not committed)
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
LLMDMZ_HOST=127.0.0.1
LLMDMZ_PORT=8080
LLMDMZ_URL=http://127.0.0.1:8080
ARBITER_MODEL=openrouter/openai/gpt-oss-120b:free
CELERY_BROKER_URL=sqla+sqlite:///data/celery_broker.db
CELERY_RESULT_BACKEND=db+sqlite:///data/celery_results.db

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

**`config/schemas.json`** — maps schema pairs to requestor/requestee:

```json
{
  "schemas": [
    {
      "id": "crm_search",
      "description": "Search CRM contacts by name or company",
      "request_schema": "schemas/crm_search_request.json",
      "response_schema": "schemas/crm_search_response.json",
      "requestor_id": "ext_agent",
      "requestee_id": "int_agent"
    }
  ]
}
```

Add more entries here to support additional operations without code changes.

---

## Running the system

You need **three processes** for the full DMZ flow:

### Terminal 1 — Celery worker (async validation)

```bash
celery -A dmz.celery_app.celery_app worker --loglevel=info
```

### Terminal 2 — DMZ HTTP server

```bash
python llmdmz.py
```

Server listens on `http://127.0.0.1:8080` by default.

### Terminal 3 — Agents (optional, for interactive use)

```bash
# Trusted internal agent (CRM)
python int_llm.py

# Untrusted external agent (email)
python ext_llm.py
```

Both agents use LiteLLM with OpenRouter. Default model: `openrouter/openai/gpt-oss-120b:free`.

---

## A2A gateway (`a2admz.py`)

The A2A gateway exposes the same DMZ validation pipeline over the **Agent-to-Agent (A2A)** protocol using [`python-a2a`](https://pypi.org/project/python-a2a/).

```
  ext_agent (A2A)          a2admz.py (A2A proxy)          a2a_requestee.py (A2A)
       │                         │                                │
       │  A2A task/send          │  schema + arbiter              │  fulfill request
       └────────────────────────►│───────────────────────────────►│
                                 │◄───────────────────────────────┘
                                 │  schema + arbiter on response
       ◄─────────────────────────┘
       A2A completed task
```

### Running the A2A stack

Terminal 1 — trusted requestee:

```bash
python a2a_requestee.py
```

Listens on `http://127.0.0.1:5001` by default.

Terminal 2 — A2A DMZ gateway:

```bash
python a2admz.py
```

Listens on `http://127.0.0.1:5000` by default. Also exposes the human review API at `/api/v1/review/*`.

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

### Example client

```bash
python a2a_client_example.py crm_search
```

Or from Python:

```python
from python_a2a import A2AClient, Task

envelope = {
    "llmdmz": {
        "schema_id": "crm_search",
        "request_id": "a2a-req-001",
        "payload": {"company": "Acme Corp"},
    }
}
task = Task(id="a2a-req-001", metadata=envelope)
client = A2AClient(
    "http://127.0.0.1:5000",
    headers={"X-Agent-Id": "ext_agent", "X-Agent-Key": "ext-dev-key-change-me"},
    google_a2a_compatible=True,
)
result = client._send_task(task)
```

### Gateway flow

1. Requestor submits A2A task to `a2admz.py`
2. Gateway validates request schema + LLM malicious-content check
3. On pass, forwards to requestee A2A URL (`requestee_a2a_url` in `config/schemas.json`)
4. Requestee receives response schema instructions and returns `response_payload`
5. Gateway validates response schema + LLM exfiltration check
6. On pass, returns completed A2A task to requestor

If validation fails at either stage, the task returns `input-required` with a review ID. Approve via `review_cli.py` (point `--base-url` at the gateway), then resubmit the same `request_id`.

### A2A environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `A2A_DMZ_HOST` | `127.0.0.1` | Gateway bind host |
| `A2A_DMZ_PORT` | `5000` | Gateway bind port |
| `A2A_DMZ_URL` | `http://127.0.0.1:5000` | Gateway public URL (agent card) |
| `A2A_REQUESTEE_HOST` | `127.0.0.1` | Requestee bind host |
| `A2A_REQUESTEE_PORT` | `5001` | Requestee bind port |
| `A2A_REQUESTEE_URL` | `http://127.0.0.1:5001` | Requestee public URL |

---

## DMZ HTTP API

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
| `pending_requestee` | Passed validation; waiting for requestee to pick up |
| `in_progress` | Requestee polled and claimed the request |
| `validating_response` | Response submitted; schema + arbiter check in progress |
| `completed` | Response approved; waiting for requestor to poll |
| `delivered` | Requestor polled the response |
| `pending_review_request` | Request failed validation/arbiter; needs human review |
| `pending_review_response` | Response failed validation/arbiter; needs human review |
| `rejected` | Human reviewer rejected, or terminal failure |

### Flow diagram

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

---

## Schema reference: `crm_search`

### Request (`schemas/crm_search_request.json`)

Query by **name**, **company**, or both. At least one is required.

```json
{ "name": "Jane Smith" }
{ "company": "Acme Corp" }
{ "name": "Jane", "company": "Acme Corp" }
```

### Response (`schemas/crm_search_response.json`)

Always includes a `records` array. Empty when nothing matched.

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

Contact `status` must be one of: `active`, `lead`, `churned`.

Schemas are loaded with **dydantic** (`create_model_from_schema`) and validated with **jsonschema** for constraints like `anyOf`.

---

## LLM agents

### Internal agent — `int_llm.py`

Trusted agent with access to private CRM data via `crmtool.py`.

```bash
# Interactive REPL
python int_llm.py

# One-shot
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

Inbox messages live in `emails/` (3 seeded on first run). Sent mail is written to `emails_out/` as `{timestamp}_{subject}.txt` (non-alphanumeric characters in the subject become underscores).

---

## Human review CLI

`review_cli.py` lets a reviewer inspect and resolve flagged items.

```bash
# List pending review items
python review_cli.py list

# Show a specific request's status
python review_cli.py show req-abc123

# Approve (sends request/response to the proper queue)
python review_cli.py approve <review_id> --notes "looks legitimate"

# Reject (marks request as rejected)
python review_cli.py reject <review_id> --notes "blocked"
```

Defaults to reviewer credentials from environment or `config/agents.json`. Override with flags:

```bash
python review_cli.py --agent-id reviewer1 --agent-key review-dev-key-change-me list
python review_cli.py --base-url http://127.0.0.1:8080 list
```

---

## LLM arbiter

The arbiter (`dmz/arbiter.py`) uses LiteLLM to call OpenRouter and returns a JSON verdict:

```json
{ "approved": true, "reason": "..." }
```

**Request check** looks for:
- Prompt injection / jailbreak attempts
- Hidden instructions bypassing schema constraints
- Unrelated sensitive operations
- Social engineering

**Response check** looks for:
- Private data beyond what the request asked for
- Bulk dumps of unrelated records
- Credentials or internal notes not justified by the request
- Encoded or steganographic leakage

Override the model with `ARBITER_MODEL` in `.env`.

---

## Logging

Both LLM agents and the DMZ service log to **stderr** using Python's `logging` module.

| Logger | Source |
|--------|--------|
| `llmdmz.int_llm` | Internal agent |
| `llmdmz.ext_llm` | External agent |
| `llmdmz.server` | Flask DMZ |
| `llmdmz.arbiter` | LLM security checks |
| `llmdmz.tasks` | Celery validation tasks |

Set verbosity:

```bash
LOG_LEVEL=DEBUG python int_llm.py "Who is at Acme?"
```

At `INFO`, logs include inference requests/responses, tool calls, and tool results. At `DEBUG`, full message payloads are included.

---

## Example: end-to-end CRM search via curl

Start Celery and the Flask server first, then:

```bash
# 1. Requestor submits a CRM search
curl -s -X POST http://127.0.0.1:8080/api/v1/requests \
  -H "X-Agent-Id: ext_agent" \
  -H "X-Agent-Key: ext-dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": "crm_search",
    "request_id": "req-demo-001",
    "payload": { "company": "Acme Corp" }
  }'

# 2. Check status (repeat until pending_requestee)
curl -s http://127.0.0.1:8080/api/v1/requests/req-demo-001 \
  -H "X-Agent-Id: ext_agent" \
  -H "X-Agent-Key: ext-dev-key-change-me"

# 3. Requestee polls for work
curl -s http://127.0.0.1:8080/api/v1/requests/poll \
  -H "X-Agent-Id: int_agent" \
  -H "X-Agent-Key: int-dev-key-change-me"

# 4. Requestee submits response
curl -s -X POST http://127.0.0.1:8080/api/v1/requests/req-demo-001/response \
  -H "X-Agent-Id: int_agent" \
  -H "X-Agent-Key: int-dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "records": [{
        "id": "c001",
        "name": "Jane Smith",
        "email": "jane.smith@acmecorp.com",
        "company": "Acme Corp",
        "phone": "+1-555-0101",
        "status": "active",
        "notes": "Enterprise renewal due Q3."
      }]
    }
  }'

# 5. Requestor polls for completed response
curl -s http://127.0.0.1:8080/api/v1/responses/poll \
  -H "X-Agent-Id: ext_agent" \
  -H "X-Agent-Key: ext-dev-key-change-me"
```

---

## Adding a new schema

1. Write request and response JSON Schema files under `schemas/`.
2. Add a binding to `config/schemas.json` with the correct `requestor_id` and `requestee_id`.
3. Restart the Flask server (Celery worker picks up task code changes on restart too).

No changes to `llmdmz.py` are required — the schema registry loads all bindings at startup.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `dydantic` | Build Pydantic models from JSON Schema |
| `litellm` | LLM calls (agents + arbiter) via OpenRouter |
| `python-dotenv` | Load `.env` |
| `flask` | DMZ HTTP server |
| `celery` | Async validation queue |
| `sqlalchemy` | Celery SQLite broker/backend |
| `email-validator` | Required by dydantic for `format: email` |
| `requests` | Review CLI HTTP client |
| `python-a2a[server]` | A2A protocol gateway and requestee |

---

## Security notes (development)

- Default agent keys in `config/agents.json` are placeholders. Change them before any real deployment.
- `.env` is gitignored and must contain your OpenRouter API key.
- The arbiter is a best-effort LLM check, not a guarantee. Human review is the backstop.
- Agents (`int_llm.py`, `ext_llm.py`) currently run standalone REPLs and do not yet auto-integrate with the DMZ HTTP API — they are the trusted/untrusted backends that a requestee/requestor process would wrap.
