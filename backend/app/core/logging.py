"""Minimal structured logging setup for the service.

A single ``configure_logging()`` call (made in the API lifespan) installs a consistent,
parseable log format on stdout. Everything else just does ``get_logger(__name__)``. Kept
deliberately small — no external logging deps — so it stays zero-cost and dependency-light.
"""

from __future__ import annotations

import logging
import sys

from backend.app.core.settings import settings

_CONFIGURED = False

# Key=value-ish line format: timestamp level logger | message. Easy to grep and to ingest.
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Install the root logging config once (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=(level or settings.log_level).upper(),
        format=_FORMAT,
        datefmt=_DATEFMT,
        stream=sys.stdout,
    )
    # Uvicorn installs its own access logger; keep ours from double-printing access lines.
    logging.getLogger("uvicorn.access").propagate = False
    # Quiet chatty third-party loggers (httpx logs every Ollama call at INFO).
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (configures logging on first use as a safety net)."""
    configure_logging()
    return logging.getLogger(name)
