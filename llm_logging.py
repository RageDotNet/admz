"""Shared logging helpers for LLM agents."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_CONFIGURED: set[str] = set()


def get_logger(agent_name: str) -> logging.Logger:
    name = f"llmdmz.{agent_name}"
    if name in _CONFIGURED:
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED.add(name)
    return logger


def log_json(logger: logging.Logger, level: int, prefix: str, payload: Any) -> None:
    logger.log(level, "%s %s", prefix, json.dumps(payload, default=str))
