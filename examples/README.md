# CRM example (client + provider)

This directory is a small **trusted CRM provider** and **client** that talk to Agent DMZ over `/v2`. It is not part of the `admz` package. The mock contact store is [`crmtool.py`](crmtool.py); JSON Schemas live in [`schemas/`](schemas/); sample invoke bodies are in [`requests/`](requests/).

You need a running DMZ (`dmz-serve` or Docker on port 8000), LiteLLM credentials for the arbiter (invokes; OpenRouter by default), and admin access to approve actions and enrollments.

You can run the same commands from the repo root as `python examples/crm_provider.py ...` (the script adds `examples/` to `sys.path` so `crmtool` imports).

## Environment

The script loads the **repo-root** `.env` (parent of `examples/`) via python-dotenv, regardless of cwd. Real environment variables still win. Put the reveal-once admin keys there so you do not edit this script when a key is reissued.

| Variable | Purpose | Default |
|---|---|---|
| `DMZ_BASE_URL` | DMZ origin | `http://127.0.0.1:8000` |
| `DMZ_PROVIDER_KEY` | Bearer key of a **provider** agent (from the admin console, reveal-once) | required for `register` / `update` |
| `DMZ_CLIENT_KEY` | Bearer key of a **client** agent (`enroll` / `client`) | same as `DMZ_PROVIDER_KEY` if unset |

Example repo-root `.env` (gitignored):

```
DMZ_PROVIDER_KEY=dmz_....
DMZ_CLIENT_KEY=dmz_....
```

## One-time setup in the admin console

1. Open `http://127.0.0.1:8000/admin` and sign in.
2. **Agents:** register a provider (and a client, or one agent with both flags). Copy each key when it is shown; it is not shown again.
3. Edit the provider’s **delivery** before invoking:
   - **completions** (typical with Docker): run `python crm_provider.py serve` on the host. Set the provider endpoint to the URL printed (`http://127.0.0.1:8090/v1/chat/completions`). If the DMZ runs in Docker on Windows/Mac, use `http://host.docker.internal:8090/v1/chat/completions` so the container can reach the host.
   - **exec** (same machine as `dmz-serve` only): command `python crm_provider.py run` with a working directory of `examples/`. This does **not** work when the DMZ is only inside Docker, unless the script is installed in the image.

## Provider: publish actions

```
python crm_provider.py register
```

That `POST`s `crm_search` and `crm_add_note` from the JSON Schema files in [`schemas/`](schemas/) (next to the script, not the repo root). In the console, **approve** each pending version so the actions become active.

To submit a new schema version later:

```
python crm_provider.py update
```

The previous approved version keeps serving until you approve the new one.

Keep `python crm_provider.py serve` running if delivery is completions.

## Client: enroll and invoke

```
python crm_provider.py enroll crm
```

Approve the enrollment in the console, then:

```
python crm_provider.py client crm_search requests/crm_search_request.json
python crm_provider.py client crm_add_note requests/crm_add_note_request.json
```

The third argument may be a JSON file path or a JSON object. Omit it to read the payload from stdin.

## Other modes

- `python crm_provider.py run` — exec delivery (stdin framing, JSON on stdout).
- `python crm_provider.py serve [host] [port]` — completions listener (default `127.0.0.1:8090`).

## Beyond the scope of this document

Action schemas, delivery protocols, and the REST contract are in `docs/schemas-v2.md`, `docs/dispatch-v2.md`, and `docs/rest-api-v2.md`.
