"""Configuration loading: DMZ_CONFIG env → ./config.yaml fallback.

Precedence (highest wins): **env vars → YAML → code defaults** (#28).
Startup validation is loud: bad config raises :class:`ConfigError` and the
process crashes rather than misbehaving at runtime (system-prd-v2.md).
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml
from werkzeug.security import check_password_hash

# Optional .env support (python-dotenv): secrets like OPENROUTER_API_KEY live
# in .env (gitignored) instead of config.yaml. Real environment variables
# always win over .env values. Failure to find/parse .env is not an error.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is an optional convenience
    pass

DEFAULT_CONFIG_PATH = "./config.yaml"

# Code defaults (lowest precedence).
_DEFAULTS: dict[str, Any] = {
    "database_url": "sqlite:///data/dmz.db",
    "secret_key": "",
    "app_port": 8000,
    "flask_debug": False,
    "log_level": "INFO",
    "arbiter_model": "openai/gpt-4o-mini",  # #2
    "arbiter_api_key": "",
    "arbiter_timeout": 30,
    "arbiter_max_tokens": 512,
    "arbiter_temperature": 0.0,
    "dispatch_retries": 2,  # dispatch-v2.md default
    "dispatch_timeout": 180,  # dispatch-v2.md default
    "key_payload_chars": 14,  # dmz_ body entropy chars; last 2 of body are checksum
    # Optional prompt overrides (empty string = built-in default prompt).
    "arbiter_request_prompt": "",
    "arbiter_response_prompt": "",
    "arbiter_injection_focus": "",
    "arbiter_exfiltration_focus": "",
}

_ENV_MAP = {
    "database_url": "DMZ_DATABASE_URL",
    "secret_key": "FLASK_SECRET_KEY",
    "app_port": "DMZ_APP_PORT",
    "flask_debug": "FLASK_DEBUG",
    "log_level": "LOG_LEVEL",
    "arbiter_model": "ARBITER_MODEL",
    "arbiter_api_key": "OPENROUTER_API_KEY",
    "arbiter_timeout": "ARBITER_TIMEOUT",
    "arbiter_max_tokens": "ARBITER_MAX_TOKENS",
    "arbiter_temperature": "ARBITER_TEMPERATURE",
    "dispatch_retries": "DMZ_DISPATCH_RETRIES",
    "dispatch_timeout": "DMZ_DISPATCH_TIMEOUT",
    "key_payload_chars": "DMZ_KEY_PAYLOAD_CHARS",
}

_INT_KEYS = {
    "app_port",
    "arbiter_timeout",
    "arbiter_max_tokens",
    "dispatch_retries",
    "dispatch_timeout",
    "key_payload_chars",
}
_FLOAT_KEYS = {"arbiter_temperature"}
_BOOL_KEYS = {"flask_debug"}

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigError(RuntimeError):
    """Raised on invalid configuration; crashes startup loudly."""


@dataclass(frozen=True)
class AdminAccount:
    """An administrator defined in the config file (#23)."""

    username: str
    password: str  # plaintext or werkzeug-style hash, as written in YAML
    token: str | None = None  # optional admin bearer token (dmzadm_...)

    def check_password(self, candidate: str) -> bool:
        stored = self.password
        if stored.startswith(("pbkdf2:", "scrypt:", "argon2:")):
            return check_password_hash(stored, candidate)
        # Plaintext (operator's choice; hash strongly preferred, #23).
        return hmac.compare_digest(stored, candidate)


def _validate_admin(entry: Any, index: int) -> AdminAccount:
    where = f"admins[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: must be a mapping with username/password")
    username = entry.get("username")
    password = entry.get("password")
    if not isinstance(username, str) or not username.strip():
        raise ConfigError(f"{where}.username: non-empty string required")
    if not isinstance(password, str) or not password:
        raise ConfigError(f"{where}.password: non-empty string required")
    if password.startswith(("pbkdf2:", "scrypt:", "argon2:")):
        if password.startswith("pbkdf2:"):
            # Werkzeug format: pbkdf2:sha256:<iterations>$<salt>$<hash>.
            import re

            if re.fullmatch(
                r"pbkdf2:sha256:\d+\$[A-Za-z0-9+/=._-]+\$[A-Za-z0-9+/=._-]+",
                password,
            ) is None:
                raise ConfigError(
                    f"{where}.password: malformed pbkdf2 hash "
                    "(expected pbkdf2:sha256:<iter>$<salt>$<hash>)"
                )
        try:
            check_password_hash(password, "probe-value")
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"{where}.password: malformed hash: {exc}") from exc
    token = entry.get("token")
    if token is not None and (not isinstance(token, str) or not token):
        raise ConfigError(f"{where}.token: must be a non-empty string if present")
    extra = set(entry) - {"username", "password", "token"}
    if extra:
        raise ConfigError(f"{where}: unknown keys {sorted(extra)}")
    return AdminAccount(username=username, password=password, token=token)


@dataclass(frozen=True)
class Config:
    """Resolved application configuration."""

    database_url: str
    secret_key: str
    app_port: int
    flask_debug: bool
    log_level: str
    session_cookie_secure: bool
    arbiter_model: str
    arbiter_api_key: str
    arbiter_timeout: int
    arbiter_max_tokens: int
    arbiter_temperature: float
    dispatch_retries: int
    dispatch_timeout: int
    key_payload_chars: int
    arbiter_request_prompt: str = ""
    arbiter_response_prompt: str = ""
    arbiter_injection_focus: str = ""
    arbiter_exfiltration_focus: str = ""
    admins: tuple[AdminAccount, ...] = field(default_factory=tuple)

    def admin_by_username(self, username: str) -> AdminAccount | None:
        for admin in self.admins:
            if admin.username == username:
                return admin
        return None


def _coerce(key: str, raw: str) -> Any:
    try:
        if key in _INT_KEYS:
            return int(raw)
        if key in _FLOAT_KEYS:
            return float(raw)
        if key in _BOOL_KEYS:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return raw
    except ValueError as exc:
        raise ConfigError(f"env override for {key!r} is not a valid value: {raw!r}") from exc


def _flatten_yaml(data: dict[str, Any]) -> dict[str, Any]:
    """Map the YAML section structure onto flat config keys."""
    flat: dict[str, Any] = {}
    sections = {"arbiter": "arbiter_", "dispatch": "dispatch_"}
    for key, value in data.items():
        if key in sections:
            prefix = sections[key]
            if not isinstance(value, dict):
                raise ConfigError(f"{key}: expected a mapping section")
            for sub_key, sub_value in value.items():
                flat[prefix + sub_key] = sub_value
        elif key in (
            "arbiter_request_prompt",
            "arbiter_response_prompt",
            "arbiter_injection_focus",
            "arbiter_exfiltration_focus",
        ):
            if not isinstance(value, str):
                raise ConfigError(f"{key}: must be a string (prompt text)")
            flat[key] = value
        elif key in ("admins", "session_cookie_secure"):
            flat[key] = value
        elif key in _DEFAULTS:
            flat[key] = value
        else:
            raise ConfigError(f"unknown config key: {key!r}")
    return flat


def load_config(path: str | None = None) -> Config:
    """Load config with env > YAML > default precedence; validate loudly."""
    path = path or os.environ.get("DMZ_CONFIG") or DEFAULT_CONFIG_PATH

    merged: dict[str, Any] = dict(_DEFAULTS)
    merged["session_cookie_secure"] = False
    admins: list[AdminAccount] = []

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"malformed YAML in {path}: {exc}") from exc
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: top-level YAML must be a mapping")
        flat = _flatten_yaml(raw)
        admins_raw = flat.pop("admins", None)
        for key, value in flat.items():
            merged[key] = value
        if admins_raw is not None:
            if not isinstance(admins_raw, list):
                raise ConfigError("admins: expected a list")
            admins = [_validate_admin(e, i) for i, e in enumerate(admins_raw)]
    elif os.environ.get("DMZ_CONFIG"):
        # Explicit path was requested but does not exist — loud failure.
        raise ConfigError(f"DMZ_CONFIG points at a missing file: {path}")

    # Env overrides win over YAML.
    for key, env_name in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is not None and raw != "":
            merged[key] = _coerce(key, raw)

    # Loud validation of the merged result.
    for key in _INT_KEYS:
        if not isinstance(merged[key], int) or isinstance(merged[key], bool):
            raise ConfigError(f"{key}: integer required, got {merged[key]!r}")
    if merged["app_port"] <= 0 or merged["app_port"] > 65535:
        raise ConfigError(f"app_port out of range: {merged['app_port']}")
    if merged["dispatch_retries"] < 0:
        raise ConfigError("dispatch_retries must be >= 0")
    if merged["dispatch_timeout"] <= 0 or merged["arbiter_timeout"] <= 0:
        raise ConfigError("timeouts must be positive")
    kpc = merged["key_payload_chars"]
    if kpc < 14 or kpc > 128:
        raise ConfigError("key_payload_chars must be between 14 and 128")
    level = merged["log_level"]
    if not isinstance(level, str) or level.upper() not in VALID_LOG_LEVELS:
        raise ConfigError(f"log_level invalid: {level!r}")
    merged["log_level"] = level.upper()
    if not merged["secret_key"]:
        logging.getLogger(__name__).warning(
            "secret_key is empty; set FLASK_SECRET_KEY in production"
        )
    if not admins:
        raise ConfigError("no admin accounts defined (admins: in config)")

    merged["admins"] = tuple(admins)
    known = set(_DEFAULTS) | {"admins", "session_cookie_secure"}
    return Config(**{k: merged[k] for k in known})

