# Contributing

Thanks for helping with Agent DMZ.

## Pull requests

Open a pull request from a **fork** of this repository (do not push feature branches to the upstream unless you are a maintainer).

Before you open the PR:

1. Install with `pip install -e ".[dev]"`.
2. Run the same checks CI runs: `ruff check src tests fabfile.py`, `mypy`, and `pytest -q`.
3. **All tests must pass.** Do not open a PR with a red suite.

Keep changes focused. Do not invent REST fields or error shapes; see [`docs/rest-api-v2.md`](docs/rest-api-v2.md). Config keys are documented in [`config.yaml.example`](config.yaml.example).

Normative product behavior is in [`docs/index-v2.md`](docs/index-v2.md). Coding-agent notes are in [`AGENTS.md`](AGENTS.md).

## License

By contributing you agree that your work is licensed under the same [MIT License](LICENSE) as the rest of the project.

## Beyond the scope of this document

Deployment secrets, production hardening, and issue triage live in [`SECURITY.md`](SECURITY.md) and [`deploy/README.md`](deploy/README.md).
