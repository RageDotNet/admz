"""Offline config-loader tests (T0.11): precedence, missing file, malformed YAML, bad admins."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from llmdmz.core.config import ConfigError, load_config

GOOD_ADMIN = "admins:\n  - username: root\n    password: hunter2\n"


def _write(tmp_path: Path, text: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "DMZ_CONFIG", "DMZ_DATABASE_URL", "FLASK_SECRET_KEY", "DMZ_APP_PORT",
        "ARBITER_MODEL", "OPENROUTER_API_KEY", "ARBITER_TIMEOUT",
        "DMZ_DISPATCH_RETRIES", "DMZ_DISPATCH_TIMEOUT", "LOG_LEVEL",
        "DMZ_KEY_PAYLOAD_CHARS",
    ):
        monkeypatch.delenv(var, raising=False)



def test_defaults_with_minimal_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("DMZ_CONFIG", raising=False)
    path = _write(tmp_path, GOOD_ADMIN)
    monkeypatch.setenv("DMZ_CONFIG", path)
    cfg = load_config()
    assert cfg.arbiter_model == "openai/gpt-4o-mini"
    assert cfg.dispatch_retries == 2
    assert cfg.dispatch_timeout == 180
    assert cfg.admins[0].username == "root"


def test_env_overrides_yaml(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        GOOD_ADMIN + "dispatch:\n  retries: 5\narbiter:\n  model: yaml/model\n",
    )
    monkeypatch.setenv("DMZ_CONFIG", path)
    monkeypatch.setenv("DMZ_DISPATCH_RETRIES", "7")
    monkeypatch.setenv("ARBITER_MODEL", "env/model")
    cfg = load_config()
    assert cfg.dispatch_retries == 7  # env beats YAML
    assert cfg.arbiter_model == "env/model"
    assert cfg.dispatch_timeout == 180  # YAML absent → code default


def test_yaml_overrides_defaults(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD_ADMIN + "dispatch:\n  retries: 0\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    cfg = load_config()
    assert cfg.dispatch_retries == 0


def test_missing_default_file_crashes_without_admins(monkeypatch, tmp_path):
    monkeypatch.delenv("DMZ_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)  # no ./config.yaml here
    with pytest.raises(ConfigError, match="no admin accounts"):
        load_config()


def test_explicit_dmz_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DMZ_CONFIG", str(tmp_path / "nope.yaml"))
    with pytest.raises(ConfigError, match="missing file"):
        load_config()


def test_malformed_yaml(tmp_path, monkeypatch):
    path = _write(tmp_path, "admins: [unclosed\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    with pytest.raises(ConfigError, match="malformed YAML"):
        load_config()


def test_bad_admin_entries(tmp_path, monkeypatch):
    cases = [
        "admins:\n  - username: ''\n    password: x\n",
        "admins:\n  - username: a\n    password: ''\n",
        "admins:\n  - notamapping\n",
        "admins: {}\n",
        GOOD_ADMIN + "admins:\n  - username: a\n    password: x\n    bogus: 1\n",
    ]
    for text in cases:
        path = _write(tmp_path, text)
        monkeypatch.setenv("DMZ_CONFIG", path)
        with pytest.raises(ConfigError):
            load_config()


def test_hashed_admin_password(tmp_path, monkeypatch):
    phash = generate_password_hash("s3cret", method="pbkdf2:sha256")
    path = _write(tmp_path, f"admins:\n  - username: root\n    password: \"{phash}\"\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    cfg = load_config()
    assert cfg.admins[0].check_password("s3cret")
    assert not cfg.admins[0].check_password("wrong")
    # Malformed hash crashes loudly.
    path2 = _write(tmp_path, "admins:\n  - username: r\n    password: 'pbkdf2:sha256:notavalidhash'\n")
    monkeypatch.setenv("DMZ_CONFIG", path2)
    with pytest.raises(ConfigError, match="malformed"):
        load_config()


def test_unknown_key_rejected(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD_ADMIN + "bogus_key: 1\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    with pytest.raises(ConfigError, match="unknown config key"):
        load_config()


def test_key_payload_chars_from_yaml_and_env(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD_ADMIN + "key_payload_chars: 32\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    cfg = load_config()
    assert cfg.key_payload_chars == 32
    monkeypatch.setenv("DMZ_KEY_PAYLOAD_CHARS", "48")
    cfg = load_config()
    assert cfg.key_payload_chars == 48


def test_key_payload_chars_bounds(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD_ADMIN + "key_payload_chars: 13\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    with pytest.raises(ConfigError, match="key_payload_chars"):
        load_config()
    path = _write(tmp_path, GOOD_ADMIN + "key_payload_chars: 129\n")
    monkeypatch.setenv("DMZ_CONFIG", path)
    with pytest.raises(ConfigError, match="key_payload_chars"):
        load_config()
