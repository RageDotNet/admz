# Infra v1 — Technology Stack & Runtime Reference

> Reference document describing the infrastructure the current ("v1") LLM DMZ is built on, written from the actual code and `requirements.txt`. Intended as a baseline when planning changes for the next version.

## 1. Runtime & layout

- **Python 3.11**, run from a local `.venv`.
- Plain entry-point scripts at the repo root — **no packaging** (no `pyproject.toml` / setup). Making it an installable package is a known TODO.
- Core logic lives in the shared `dmz/` package (storage, schemas, agents, arbiter, tasks, celery, A2A protocol, admin/review routes, config), reused by both gateways.

Top-level layout:

```
<root>             Gateway entry points (REST gateway, A2A gateway, A2A requestee,
                   internal/external LLM agents, example tools, review CLI)
dmz/               Shared gateway core package
templates/admin/   Admin console Jinja2 templates
config/            agents.json, schemas.json
data/              SQLite DBs + JSON state
schemas/           JSON Schema files
tests/             Offline test suite
```

## 2. Web framework

**Flask** (not FastAPI). Two Flask applications:

| App | Port | Behavior |
|---|---|---|
| REST DMZ | 8080 | Async pipeline — validation + arbitration offloaded to Celery workers; requestor/requestee interact via REST poll/submit endpoints |
| A2A DMZ | 5000 | Synchronous validation in-process, forwards to the requestee over A2A; also registers the admin console (`/admin`) and review REST API |

Templating is stock **Jinja2** (bundled with Flask). Templates are cached unless `FLASK_DEBUG=1`, so template edits require a gateway restart in production.

## 3. Agent protocol

- **`python-a2a[server]`** — the Agent-to-Agent protocol library. Used by the A2A gateway, the internal requestee (port 5001, CRM handlers), and the example/nefarious test clients.

## 4. Admin console frontend

- **[Datastar](https://data-star.dev/)** — hypermedia reactivity: server-rendered HTML fragments, signals, and multi-patch responses; **no custom JavaScript**.
- **[0build](https://github.com/0builddotdev/0build)** CSS — zero-build utility classes (`z-*`); no CSS pipeline.
- **No npm/Node anywhere** — no bundler, no build step.

## 5. Storage

All persistence is **SQLite**, plus a few plain JSON files:

| Store | Technology | Notes |
|---|---|---|
| `data/dmz.db` — request/response records, review queue | **raw `sqlite3`** (storage module in `dmz/`) | Tables created in code; **no ORM, no migration library** (no Alembic) |
| `data/celery_broker.db`, `data/celery_results.db` | Celery via **SQLAlchemy URLs** | SQLAlchemy appears only in broker/backend connection strings, not for app models |
| `data/crm.json`, `data/email_seen.json` | plain JSON files | Example CRM data + email dedupe state |
| `emails/`, `emails_out/` | text files | Example email tool data |

> The raw-`sqlite3`-with-no-migrations choice is the piece most likely to need upgrading if new tables and state churn are added (e.g. a provider schema-submission lifecycle).

## 6. Async workers

- **Celery** (app + tasks in the `dmz/` package). The REST gateway enqueues request/response validation tasks.
- Broker and result backend default to SQLite files under `data/` (overridable via `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`). SQLite-backed Celery is fine for a single-machine dev setup but not for multi-worker/scaled deployments.

## 7. LLM stack

- **LiteLLM** for every model call — both the LLM agents (internal and external) and the security arbiter (in the `dmz/` package).
- Calls route through **OpenRouter**:
  - `OPENROUTER_API_KEY` (required, in `.env`)
  - `ARBITER_MODEL` — default `openrouter/openai/gpt-oss-120b:free`

## 8. Schema validation

- **jsonschema** — structural validation of request/response payloads (supports `anyOf` etc.).
- **dydantic** — generates **Pydantic** models from JSON Schema for a second validation pass (type coercion/format checks).
- **email-validator** — backs `format: email` in schemas.
- Schemas are JSON Schema draft 2020-12 files in `schemas/`, registered via `config/schemas.json` (see the schemas documentation).

## 9. Configuration

- **python-dotenv** — `.env` at repo root for secrets/env.
- **JSON config files** — `config/agents.json` (agent IDs, keys, roles incl. admin reviewers) and `config/schemas.json` (schema bindings).

Key environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | OpenRouter API key (agents + arbiter) |
| `ARBITER_MODEL` | `openrouter/openai/gpt-oss-120b:free` | Arbiter model |
| `A2A_DMZ_HOST` / `A2A_DMZ_PORT` | `127.0.0.1` / `5000` | A2A gateway bind |
| `A2A_DMZ_URL` | `http://127.0.0.1:5000` | Gateway public URL (agent card) |
| `A2A_REQUESTEE_HOST` / `PORT` / `URL` | `127.0.0.1` / `5001` | Internal requestee |
| `FLASK_SECRET_KEY` | dev default | Signs admin UI session cookies |
| `FLASK_DEBUG` | `0` | `1` enables auto-reload (incl. templates) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | SQLite files in `data/` | Celery transport |
| `LOG_LEVEL` | INFO | Logging verbosity (`llmdmz.*` loggers) |

## 10. Testing

- **pytest** (`pytest.ini` with `pythonpath = .`, tests in `tests/`).
- 86 tests, **fully offline** — LiteLLM arbiter calls and A2A requestee forwarding are mocked; no network access required.
- Covers storage, schemas, agents/auth, arbiter, Celery tasks, both gateways' APIs, admin UI routes, and the A2A protocol.

## 11. Explicitly absent (v1)

| Absent | Implication |
|---|---|
| **Docker** (no Dockerfile/compose) | Deployment is manual script launch on a host with a venv |
| **Migrations** (no Alembic/Flask-Migrate) | `dmz.db` schema changes mean hand-written SQL or DB recreation |
| **CI pipeline** | Tests run locally only |
| **Linters/formatters** | None configured |
| **Packaging** | Not pip-installable; run from the repo root |
| **npm/Node build** | Intentional — Datastar + 0build keep the frontend buildless |

### Upgrade candidates for the next version

- Introduce a migration tool (e.g. Alembic or lightweight in-code versioned migrations) before adding new tables for a schema-submission lifecycle.
- Packaging (`pyproject.toml`) — already on the TODO list.
- Consider a real broker (Redis) if the REST gateway's Celery usage survives the redesign.
