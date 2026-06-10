"""Tests for Phase 10 hardening: model timeouts and logging setup (offline)."""

from __future__ import annotations

import logging

from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.settings import settings
from backend.app.llm.factory import get_chat_model


def test_chat_models_have_a_request_timeout():
    for role in ("router", "agent"):
        model = get_chat_model(role)
        assert model.client_kwargs.get("timeout") == settings.request_timeout


def test_explicit_client_kwargs_override_is_respected():
    model = get_chat_model("router", client_kwargs={"timeout": 5.0})
    assert model.client_kwargs["timeout"] == 5.0


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()  # second call must not raise or duplicate handlers
    assert logging.getLogger().level <= logging.WARNING


def test_get_logger_returns_named_logger():
    logger = get_logger("archon.test")
    assert logger.name == "archon.test"
