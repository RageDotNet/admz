# Agent DMZ

**Agent DMZ** (`admz`) is a directory-driven broker between **untrusted client agents** and **trusted provider agents**. The two sides never talk directly. Clients discover actions, request enrollment, and invoke; providers publish versioned actions; an LLM arbiter plus JSON Schema check every request and response; humans approve enrollments and action versions in the admin console.

See [Why We Built This](docs/why-we-built-this.md) for the problem statement. Normative v2 behavior is in the [PRD index](docs/index-v2.md).

## Run locally

Python 3.11+ (deploy/CI use 3.12). From a venv:

```
pip install -e ".[dev]"
```

Copy or edit [`config.yaml`](config.yaml) (admin accounts, SQLite URL, arbiter model). Put `OPENROUTER_API_KEY` in a gitignored `.env`. Then:

```
dmz-serve
```

- Admin console: `http://127.0.0.1:8000/admin` (default `admin` / `changeme`)
- Agent API: `/v2/...` (see [`docs/rest-api-v2.md`](docs/rest-api-v2.md))
- SQLite file: `data/dmz.db` (gitignored); migrations apply on first use / container start

Offline tests:

```
pytest -q
```

Docker: [`deploy/README.md`](deploy/README.md) and `docker compose -f deploy/docker-compose.yml up`.

## Layout

```
src/admz/          Packaged Flask app (API, dispatch, admin console)
migrations/        Alembic
skills/            Client and provider skill markdown (`/v2/skill`)
schemas/           Sample CRM JSON Schemas for crm_provider.py
deploy/            Dockerfile and compose
tests/             Offline pytest suite
docs/              v2 PRDs (index-v2.md)
config.yaml        Runtime YAML (admins, DSN, arbiter)
pyproject.toml     Package and tool config
```

[`crm_provider.py`](crm_provider.py) (backed by [`crmtool.py`](crmtool.py) mock contacts) registers sample CRM actions, serves completions, and can invoke as a client.

## Beyond the scope of this document

Binding clarifications, ERD, and delivery protocols live in the PRD set, not here.
