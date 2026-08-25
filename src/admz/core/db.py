"""Database engine/session management (SQLAlchemy 2.x)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from admz.core.config import Config

_ENGINE_KEY = "DMZ_ENGINE"
_SESSION_FACTORY_KEY = "DMZ_SESSION_FACTORY"

_DEFAULT_DSN = "sqlite:///data/dmz.db"


def build_engine(config: Config):
    dsn = config.database_url or _DEFAULT_DSN
    return create_engine(dsn, future=True)


def init_db(app: Flask, config: Config) -> None:
    engine = build_engine(config)
    app.extensions[_ENGINE_KEY] = engine
    app.extensions[_SESSION_FACTORY_KEY] = sessionmaker(
        bind=engine, future=True, expire_on_commit=False
    )


def get_engine(app: Flask):
    return app.extensions[_ENGINE_KEY]


def get_session_factory(app: Flask):
    return app.extensions[_SESSION_FACTORY_KEY]


@contextmanager
def session_scope(app: Flask) -> Iterator[Session]:
    """Transactional session scope; commits on success, rolls back on error."""
    factory = get_session_factory(app)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
