"""Celery application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    f"sqla+sqlite:///{(DATA_DIR / 'celery_broker.db').as_posix()}",
)
RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    f"db+sqlite:///{(DATA_DIR / 'celery_results.db').as_posix()}",
)

celery_app = Celery(
    "llmdmz",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["dmz.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue="llmdmz",
)
