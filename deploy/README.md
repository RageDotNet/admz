# Agent DMZ v2 — Deployment Checklist

Operational notes for deploying the DMZ container. Read together with
`docs/infra-v2.md`.

## Server

- The image runs **gunicorn with gthread workers** (clarification #5):

  ```
  gunicorn -w 2 --threads 16 --timeout 900 --graceful-timeout 900 --keep-alive 5 \
      -b 0.0.0.0:8000 --access-logfile - --error-logfile - --capture-output \
      'admz.app:create_app_standalone()'
  ```

- Invokes are synchronous and I/O-bound; worst case is
  `timeout × (retries + 1)` ≈ **9 minutes** at defaults (`timeout: 180`,
  `retries: 2`).

## Reverse proxy

- Any proxy in front (nginx, Caddy, Traefik) must set
  **`proxy_read_timeout` ≥ 900s** (and equivalent send/connect timeouts) —
  a shorter value truncates legitimate invokes.

## LiteLLM arbiter

- Put the provider key in the repo-root `.env` (compose loads
  `deploy/../.env` into the container). Compose's project dir is `deploy/`,
  so a `.env` next to `docker-compose.yml` is a different file. Default path:
  `OPENROUTER_API_KEY` with model `openrouter/...`. Direct OpenAI/Anthropic
  (and other LiteLLM backends) use `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
  (etc.) and a matching `arbiter.model`. Optional `ARBITER_API_KEY` forces
  the key LiteLLM receives.
- Compose does **not** default `ARBITER_MODEL` in `environment` (that
  overrode repo `.env` and `config.yaml` with `openai/gpt-4o-mini`). Model
  comes from `config.yaml` (`arbiter.model`) or `ARBITER_MODEL` in `.env`.
  Call knobs: temperature 0, `max_tokens=512`, per-call timeout 30s, no LiteLLM retries.
- An invalid key or unknown model surfaces as **`500 internal_error`** on
  invokes — alerts on `internal_error` spikes are the operator's early
  warning that arbiter credentials/config broke (clarification #6).

## Storage

- SQLite database lives on a mounted volume (see `docker-compose.yml`);
  the entrypoint enforces `0600` on the DB file (#16).
- The DB grows without bound: every request stores full payloads and every
  dispatch attempt stores its framing (request log retention is unbounded
  by design, #14). Monitor size; export/prune manually if needed — no
  automatic purge exists in this version.
- Alembic migrations run automatically at container start
  (`alembic upgrade head` before serving).

## Secrets

- Admin credentials and optional admin bearer tokens live in the YAML
  config (`admins:` entries; hashed `pbkdf2:sha256` passwords preferred).
- `FLASK_SECRET_KEY` must be set in production (startup warns loudly if empty).
- Provider delivery configs (including header credentials) are stored in
  the DB and treated as sensitive: they are never returned through any API
  or console render.

## Vendor assets

- Datastar and the utility CSS bundle are vendored under
  `src/admz/static/vendor/` (no CDN, no runtime fetch, #22). To upgrade,
  edit the pins in `scripts/update_vendor.py` and run it, then commit the
  refreshed files.

## Smoke run

1. `docker compose up` — entrypoint migrates then serves.
2. Log into `/admin/login` with the YAML admin credentials.
3. Register a provider agent (reveal-once key), configure its delivery
   config, then submit an action via `POST /v2/actions` with the key.
4. Approve the version in the console; enroll a client agent; invoke.

## Live smoke script

`scripts/smoke_live.py` exercises the real LiteLLM arbiter adapter
(not covered by the offline suite, clarification #31). Run manually with
the same provider keys as production (`OPENROUTER_API_KEY=... python scripts/smoke_live.py`
or OpenAI/Anthropic env vars + `ARBITER_MODEL`); it prints the parsed
verdict and exits non-zero on failure.
