"""Tests for the tiered LLM factory.

The unit tests need no Ollama server — they assert how models are *configured*.
The integration test actually calls the local model and is skipped automatically
when Ollama is unreachable, so `make test` stays green offline / in CI.
"""

from __future__ import annotations

from typing import Literal

import httpx
import pytest
from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import BaseModel

from backend.app.core.settings import settings
from backend.app.llm import factory


# --------------------------------------------------------------------------- #
# Unit tests (no network)
# --------------------------------------------------------------------------- #
def test_router_model_uses_router_settings():
    model = factory.get_chat_model("router")
    assert isinstance(model, ChatOllama)
    assert model.model == settings.router_model
    assert model.temperature == settings.router_temperature
    assert model.base_url == settings.ollama_base_url
    # Reasoning is disabled on the router so structured output stays clean.
    assert model.reasoning is False


def test_agent_model_uses_agent_settings():
    model = factory.get_chat_model("agent")
    assert model.model == settings.agent_model
    assert model.temperature == settings.agent_temperature


def test_temperature_override():
    model = factory.get_chat_model("agent", temperature=0.9)
    assert model.temperature == 0.9


def test_router_and_agent_use_different_context_windows():
    assert factory.get_chat_model("router").num_ctx < factory.get_chat_model("agent").num_ctx


def test_cached_builders_return_same_instance():
    assert factory.get_router_model() is factory.get_router_model()
    assert factory.get_agent_model() is factory.get_agent_model()


def test_embeddings_config():
    emb = factory.get_embeddings()
    assert isinstance(emb, OllamaEmbeddings)
    assert emb.model == settings.embed_model
    assert emb.base_url == settings.ollama_base_url


# --------------------------------------------------------------------------- #
# Integration test (needs Ollama; skipped if unreachable)
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_structured_output_classifies_billing():
    class Intent(BaseModel):
        intent: Literal["billing", "technical", "account", "sales"]

    classifier = factory.get_router_model().with_structured_output(Intent)
    result = classifier.invoke("I was charged twice for my subscription this month.")
    assert result.intent == "billing"
