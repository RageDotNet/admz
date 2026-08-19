"""Shared pytest fixtures for the v2 offline test suite."""

from __future__ import annotations

import pytest

from llmdmz.core.config import AdminAccount, Config


def make_config(**overrides) -> Config:
    kwargs: dict = dict(
        database_url="sqlite:///:memory:",
        secret_key="test-secret",
        app_port=8000,
        flask_debug=False,
        log_level="INFO",
        session_cookie_secure=False,
        arbiter_model="openai/gpt-4o-mini",
        arbiter_api_key="",
        arbiter_timeout=30,
        arbiter_max_tokens=512,
        arbiter_temperature=0.0,
        dispatch_retries=2,
        dispatch_timeout=180,
        admins=(
            AdminAccount(
                username="admin",
                password="pw",
                token="dmzadm_testtoken0000000000000000000000000",
            ),
        ),
    )
    kwargs.update(overrides)
    return Config(**kwargs)


@pytest.fixture()
def config() -> Config:
    return make_config()
