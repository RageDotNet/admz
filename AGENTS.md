# Agent notes

**Agent DMZ** (`admz`) brokers untrusted client agents and trusted provider agents. Humans use the admin console; agents use `/v2`. Package lives in `src/admz/`. Humans start at [README.md](README.md); how to send a PR is [CONTRIBUTING.md](CONTRIBUTING.md). Normative behavior is [docs/index-v2.md](docs/index-v2.md). Licensed MIT ([LICENSE](LICENSE)).

## Commands

```
pip install -e ".[dev]"
pytest -q
ruff check src tests fabfile.py
mypy
dmz-serve
```

CI is [.github/workflows/ci.yml](.github/workflows/ci.yml) (Python 3.12, plus compose config and image build). Match that before finishing a change.

## Layout and config

- App, templates, static: `src/admz/`
- Alembic: `migrations/`
- Agent-facing skill markdown (served at `/v2/skill`): `src/admz/skills/`
- Sample CRM: `examples/crm_provider.py`
- Config path: `DMZ_CONFIG` or `./config.yaml`. Keys are documented in [config.yaml.example](config.yaml.example). Do not commit `config.yaml` or `.env`.

## Conventions

- Do not number markdown section headings (e.g. `## 3. Storage`). Use descriptive headings and refer to sections by name.
- The closing section of a document, when used, is titled `Beyond the scope of this document`.
- PRDs under `docs/` are normative. Do not rewrite them to match code unless the user asked for a docs change.
- Do not invent REST fields or error shapes; see [docs/rest-api-v2.md](docs/rest-api-v2.md).
- Arbiter prompt invariants are asserted by tests. Do not weaken them without updating those tests.
- Never put secrets in files that will be committed.

## Admin UI

Jinja templates are under `src/admz/templates/` (Bootstrap 5 utilities, vendor assets in `src/admz/static/vendor/`). With Flask debug off, templates are cached: restart `dmz-serve` (or the container) after HTML changes; a browser hard-refresh alone is not enough.
