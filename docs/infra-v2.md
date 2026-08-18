# Infra v2 — Technology Stack & Runtime Reference

> Reference document describing the target infrastructure for the LLM DMZ. It is self-contained: an implementer should be able to build the stack from this document alone. The application model — DMZ gateways between untrusted clients and trusted providers, schema validation, LLM arbitration, human review — is assumed; this document covers how it's built, run, and deployed.

## Runtime & layout

- **Python 3.11+**, installed as a **packaged application** (see "Packaging") rather than run as loose scripts.
- Entry points are thin wrappers; core logic lives in a shared core package (storage, schemas, agents, arbiter, broker pipeline, admin/review routes, config), reused by the app's blueprints.
- Services run in containers (see "Docker & deployment"); local development can run in a venv or via compose.

Top-level layout (conceptual — exact names may shift):

```
src/               Packaged application code (app, core, agents)
templates/         Admin console Jinja2 templates (package data)
migrations/        Alembic migration scripts
config/            YAML configuration (system settings, admin accounts)
deploy/            Dockerfiles, compose files, deployment configs
fabfile.py         Fabric workflow helpers
tests/             Offline test suite
pyproject.toml     Packaging, lint/format, pytest config
```

## Web framework

**Flask**. A **single Flask application** hosts everything:

- The synchronous broker pipeline — validation, arbitration, and provider calls all run in-process; there is **no task queue and no Celery**.
- The agent-facing REST API (`completions` / `exec` / `post` per provider type) and `/skill` endpoints.
- The admin console and review UI.

Jinja2 templating; templates ship as package data so they work from an installed package and in containers.

## Admin console frontend

- **[Datastar](https://data-star.dev/)** for hypermedia reactivity — server-rendered HTML fragments, signals, multi-patch responses; **no custom JavaScript**.
- **[0build](https://github.com/0builddotdev/0build)** CSS — zero-build utility classes; no CSS pipeline.
- **No npm/Node anywhere** — the frontend is entirely buildless.

## Storage

**SQLAlchemy ORM over a relational database** (SQLite by default):

| Aspect | Detail |
|---|---|
| DB access | **SQLAlchemy 2.x** declarative models — requests, reviews, and lifecycle tables such as schema submissions |
| Schema management | **Alembic migrations** under `migrations/`; all schema changes go through migrations — no ad-hoc `CREATE TABLE` in application code |
| Connection | SQLAlchemy engine/session; DSN from `DMZ_DATABASE_URL`, defaulting to a SQLite file |
| Portability | Because access is via the ORM and a configurable DSN, the database can move to Postgres etc. without code changes |

Notes:

- The storage module exposes a stable query interface (list/get/resolve requests and reviews); ORM queries are an implementation detail behind it.
- `alembic upgrade head` runs as part of deployment (see "Docker & deployment") before the app starts.
- A single-container deploy needs no external database (SQLite file on a volume); a production deploy points `DMZ_DATABASE_URL` at Postgres.

## LLM stack

- **LiteLLM** for every model call — LLM agents (internal/external) and the security arbiter.
- Calls route through **OpenRouter** (`OPENROUTER_API_KEY`; arbiter model configurable via `ARBITER_MODEL`).

## Schema validation

- **jsonschema** + **dydantic** (Pydantic model generation) for two-pass payload validation: structural JSON Schema validation followed by a Pydantic model pass for type/format coercion.
- **email-validator** backs `format: email` in schemas.
- JSON Schema draft 2020-12 documents; the action registry (schemas and their lifecycle) lives in the **database**, populated by provider submissions (see the schemas PRD).

## Configuration

- **python-dotenv** loads `.env` for secrets in local dev; in containers, environment variables are injected by compose.
- **Application config files are YAML** — supporting comments, anchors, and multi-document files. YAML holds only:
  - **system settings** (ports, retries, arbiter model, etc.), and
  - **admin accounts** (admin reviewers).
- **Agents and schemas live in the database, not config files** — agents are administered via the admin console; schemas arrive by provider submission.
- JSON Schema *payload* documents stay JSON (they're wire-format contracts, not app config).
- Loading is centralized in the config module with typed validation (fail fast on malformed config at startup).

Key environment variables:

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter API key (agents + arbiter) |
| `ARBITER_MODEL` | Arbiter model string |
| `DMZ_DATABASE_URL` | SQLAlchemy DSN (default: SQLite file) |
| `DMZ_APP_PORT` | Bind port for the Flask app |
| `FLASK_SECRET_KEY` | Admin console session cookies |
| `FLASK_DEBUG` | Debug/auto-reload toggle |
| `LOG_LEVEL` | Logging verbosity |

## Packaging

- **Python packaging via `pyproject.toml`** as part of the deploy step — the application is installed, not run from a checkout.
- The package (e.g. `llmdmz`) declares a console-script entry point for the app (plus a review CLI), so the service starts as a named command inside containers.
- Templates and static files ship as **package data**.
- Dependencies are pinned in `pyproject.toml` as the single source of truth.
- Container images `pip install` the package (from source or a wheel built in CI) — the Dockerfile stays thin.

## Docker & deployment

- **Dockerfile(s)** under `deploy/`: a Python base image, install of the packaged app, non-root user, and the app command. A single image keeps the build simple.
- **docker-compose** (`deploy/docker-compose.yml`) wires the stack for local/production-style runs:
  - `dmz` (single Flask app: broker pipeline, agent-facing REST API, admin console)
  - SQLite volume (or an external DB service when `DMZ_DATABASE_URL` points elsewhere)
- **Compose config file** — a committed, version-checked compose configuration (e.g. `docker compose -f deploy/docker-compose.yml --env-file deploy/compose.env config` validated in tests/CI) so overrides and interpolation are deterministic.
- **Startup ordering**: migrations (`alembic upgrade head`) run as an entrypoint step or a one-shot init container before the app starts.
- Secrets/env injected via compose environment; `.env`-style files only for local dev.

## Workflow helpers — Fabric

- **Fabric** with a `fabfile.py` at the repo root provides workflow commands wrapping the common dev/deploy operations:

| Command (illustrative) | Purpose |
|---|---|
| `fab dev.up` / `fab dev.down` | Bring the compose stack up/down for local development |
| `fab test` | Run the offline test suite |
| `fab lint` | Run linter + formatter checks |
| `fab fmt` | Apply formatting fixes |
| `fab db.migrate` / `fab db.upgrade` | Generate / apply Alembic migrations |
| `fab build` / `fab deploy` | Build images / deploy the stack |

- Fabric is the single entry point so contributors don't need to memorize the underlying docker/alembic/pytest invocations.

## Testing & quality

- **pytest** test suite — fully offline (LLM and provider calls mocked); no network access required.
- **Linter/formatter integrated into the test workflow**: lint and format checks (e.g. ruff for linting + formatting, mypy optional for type checks) run as part of `fab test` / CI, so the suite fails on style violations — not just on a separate manual step.
- CI runs: lint → tests → compose config validation → image build.

## Stack summary

| Area | Choice |
|---|---|
| Language | Python 3.11+, packaged app (`pyproject.toml`) |
| Web framework | Flask — single app (broker pipeline, agent REST API, admin console); synchronous, no task queue |
| Frontend | Datastar + 0build CSS, buildless, no Node |
| Database | SQLAlchemy 2.x ORM; SQLite default, DSN-configurable (Postgres-ready) |
| Migrations | Alembic (`alembic upgrade head` at deploy) |
| LLM | LiteLLM → OpenRouter |
| Validation | jsonschema + dydantic/Pydantic + email-validator |
| Config | YAML (system settings + admin accounts only) + env vars; agents and schemas live in the DB |
| Deployment | Docker, docker-compose, committed compose config |
| Workflows | Fabric (`fabfile.py`) |
| Quality | Linter/formatter (ruff, optional mypy) enforced in the test workflow |

