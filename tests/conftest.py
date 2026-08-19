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


@pytest.fixture()
def app_fixture(config):
    from llmdmz.app import create_app
    from llmdmz.core import storage
    from llmdmz.core.models import Base

    app = create_app(config)
    engine = app.extensions["DMZ_ENGINE"]
    Base.metadata.create_all(engine)
    with app.app_context():
        factory = app.extensions["DMZ_SESSION_FACTORY"]
        s = factory()
        _, provider_key = storage.register_agent(
            s, name="provider", is_client=False, is_provider=True
        )
        _, client_key = storage.register_agent(s, name="client", is_client=True, is_provider=False)
        s.commit()
        s.close()
    return app, provider_key, client_key


@pytest.fixture()
def client_http(app_fixture):
    app, _, _ = app_fixture
    app.config["TESTING"] = True
    return app.test_client()
