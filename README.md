# Agent DMZ

**Agent DMZ** (`admz`) is a directory-driven broker between **untrusted client agents** and **trusted provider agents**. The two sides never talk directly. Clients discover actions, request enrollment, and invoke; providers publish versioned actions; an LLM arbiter plus JSON Schema check every request and response; humans approve enrollments and action versions in the admin console.

See [Why We Built This](docs/why-we-built-this.md) for the problem statement. Normative v2 behavior is in the [PRD index](docs/index-v2.md).

## Quickstart (Docker Compose)

From the **repo root**. You need Docker and an [OpenRouter](https://openrouter.ai/) API key (invokes run an LLM arbiter).

1. Put the key in a gitignored **repo-root** `.env` (not `deploy/.env` — Compose’s project directory is `deploy/`, so it loads `../.env`):

```
OPENROUTER_API_KEY=sk-or-...
```

2. Edit [`config.yaml`](config.yaml) if you want (admins, `arbiter_model`). Keep the `openrouter/...` model prefix so LiteLLM talks to OpenRouter. Default login is `admin` / `changeme`.

3. Build and run:

```
docker compose -f deploy/docker-compose.yml up --build
```

- Admin console: `http://127.0.0.1:8000/admin`
- Agent API: `/v2/...` (see [`docs/rest-api-v2.md`](docs/rest-api-v2.md))
- SQLite lives on the Compose volume (`/var/lib/dmz/dmz.db` in the container), not `data/dmz.db` on the host
- Sample client/provider: [`examples/README.md`](examples/README.md). If the CRM provider runs on the host and the DMZ is in Docker, use `http://host.docker.internal:8090/v1/chat/completions` as the completions endpoint.

Optional: `DMZ_APP_PORT` in the environment maps the published port (default `8000`). Behind a reverse proxy, set `public_base_url` in `config.yaml` so the agent onboarding prompt uses the public origin. Operational knobs (gunicorn timeouts, secrets) are in [`deploy/README.md`](deploy/README.md).

## First walkthrough

Sign in at `/admin` (`admin` / `changeme`). This is the human loop; the agent talks only to `/v2`.

1. **Agents** — Register an agent. Check **Client** and **Provider** if one agent will both publish and invoke (simplest first run). Copy the key when it is shown; it is not shown again. **Copy prompt** and paste that block into your agent so it fetches the skill(s) and uses the bearer key.
2. **Provider delivery** — Open the agent, set delivery before any invoke. Typical with Docker: **completions**, endpoint `http://host.docker.internal:8090/v1/chat/completions` (or your real OpenAI-compatible URL), optional model name. Save. The process that answers that URL must already be running (your agent, or `python examples/crm_provider.py serve` on the host). `exec` only works if the command runs *inside* the same environment as the DMZ (not a host script while the DMZ is only in Docker).
3. **Publish an action** — Tell the agent to create an action (`POST /v2/actions` — the provider skill describes the schema package). In **Directory** (or the pending queue), **approve** the submitted version so it becomes active.
4. **Enroll and invoke** — Tell the agent to enroll in that action (`POST /v2/actions/{id}/enroll`). **Approve** the enrollment (Enrollments tab or the action detail). Then tell it to invoke (`POST /v2/actions/{id}/invoke`). Invokes need a live arbiter (`OPENROUTER_API_KEY`).
5. **Logs** — **Request log** shows each invoke (payloads, arbiter verdicts, provider attempts). **Audit trail** shows approvals, enrollments, and key issuance.

A scripted CRM sample (register/enroll/client without an LLM driving `/v2`) is in [`examples/README.md`](examples/README.md).

## Develop locally

Python 3.11+ (deploy/CI use 3.12). From a venv:

```
pip install -e ".[dev]"
dmz-serve
```

Same admin URL and `/v2` API as above. SQLite is `data/dmz.db` (gitignored); migrations apply on first use.

```
pytest -q
```

## Layout

```
src/admz/          Packaged Flask app (API, dispatch, admin console)
migrations/        Alembic
src/admz/skills/   Client and provider skill markdown (`/v2/skill`)
examples/          Sample CRM client/provider (`crm_provider.py`)
deploy/            Dockerfile and compose
tests/             Offline pytest suite
docs/              v2 PRDs (index-v2.md)
config.yaml        Runtime YAML (admins, DSN, arbiter)
pyproject.toml     Package and tool config
```

See [`examples/README.md`](examples/README.md) for the sample CRM client/provider (`crm_provider.py`).

## Beyond the scope of this document

Binding clarifications, ERD, and delivery protocols live in the PRD set, not here.
