"""Tests for the observability layer — all offline (no LangSmith calls)."""

from __future__ import annotations

import os

import pytest

from backend.app.core import observability as obs
from backend.app.core.observability import (
    _is_real_key,
    configure_tracing,
    log_feedback,
    run_config,
    tracing_enabled,
)

_TRACING_ENV_VARS = [
    f"{prefix}_{suffix}"
    for prefix in ("LANGCHAIN", "LANGSMITH")
    for suffix in ("TRACING_V2", "TRACING", "API_KEY", "ENDPOINT", "PROJECT")
]


@pytest.fixture(autouse=True)
def _isolate_env():
    """Keep tracing env vars from leaking between tests (configure_tracing writes os.environ
    directly, so we clear before *and* after each test rather than relying on monkeypatch)."""

    def _clear():
        for var in _TRACING_ENV_VARS:
            os.environ.pop(var, None)

    _clear()
    obs.get_client.cache_clear()
    yield
    _clear()
    obs.get_client.cache_clear()


# --------------------------------------------------------------------------- #
# Key validation
# --------------------------------------------------------------------------- #
def test_is_real_key_rejects_blank_and_placeholder():
    assert not _is_real_key("")
    assert not _is_real_key("ls-...replace-me...")
    assert not _is_real_key("sk-1234")  # not a LangSmith key
    assert _is_real_key("lsv2_pt_realish_key_value")


# --------------------------------------------------------------------------- #
# configure_tracing
# --------------------------------------------------------------------------- #
def test_configure_tracing_disabled_with_placeholder_key(monkeypatch):
    monkeypatch.setattr(obs.settings, "langchain_tracing_v2", True)
    monkeypatch.setattr(obs.settings, "langchain_api_key", "ls-...replace-me...")
    assert configure_tracing() is False
    assert tracing_enabled() is False


def test_configure_tracing_enabled_with_real_key(monkeypatch):
    monkeypatch.setattr(obs.settings, "langchain_tracing_v2", True)
    monkeypatch.setattr(obs.settings, "langchain_api_key", "lsv2_pt_realkey_123456")
    monkeypatch.setattr(obs.settings, "langchain_project", "archon-test")
    assert configure_tracing() is True
    assert tracing_enabled() is True
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_pt_realkey_123456"
    assert os.environ["LANGSMITH_PROJECT"] == "archon-test"


def test_configure_tracing_force_off(monkeypatch):
    monkeypatch.setattr(obs.settings, "langchain_tracing_v2", True)
    monkeypatch.setattr(obs.settings, "langchain_api_key", "lsv2_pt_realkey_123456")
    assert configure_tracing(force=False) is False
    assert tracing_enabled() is False


# --------------------------------------------------------------------------- #
# run_config
# --------------------------------------------------------------------------- #
def test_run_config_always_tags_archon_and_carries_thread():
    cfg = run_config("cli-abc", tags=["cli"], metadata={"channel": "cli"})
    assert "archon" in cfg["tags"]
    assert "cli" in cfg["tags"]
    assert cfg["configurable"]["thread_id"] == "cli-abc"
    assert cfg["metadata"]["thread_id"] == "cli-abc"
    assert cfg["metadata"]["app"] == "archon"
    assert cfg["metadata"]["channel"] == "cli"


def test_run_config_dedupes_archon_tag():
    cfg = run_config(tags=["archon", "extra"])
    assert cfg["tags"].count("archon") == 1


# --------------------------------------------------------------------------- #
# Feedback degrades gracefully when tracing is off
# --------------------------------------------------------------------------- #
def test_log_feedback_noops_when_tracing_off():
    assert tracing_enabled() is False
    assert log_feedback("some-run-id", score=1.0) is False


def test_log_feedback_ignores_missing_run_id():
    assert log_feedback(None, score=1.0) is False
