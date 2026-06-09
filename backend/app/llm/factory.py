"""Tiered LLM factory — the single place models are constructed.

Everywhere in Archon we obtain models through this module rather than calling
``ChatOllama(...)`` directly. That gives us one chokepoint to:

* apply consistent connection settings (``base_url``, timeouts);
* enforce the *tiered model* strategy (fast ``router`` vs. capable ``agent``);
* toggle "thinking" output for reasoning models (qwen3) so structured-output and
  classification stay clean and parseable.

Usage::

    from backend.app.llm.factory import get_router_model, get_agent_model, get_embeddings

    router = get_router_model()          # fast, deterministic
    agent = get_agent_model()            # stronger reasoning + tool calling
    embeddings = get_embeddings()        # for RAG
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_ollama import ChatOllama, OllamaEmbeddings

from backend.app.core.settings import settings

ModelRole = Literal["router", "agent"]

# Roughly how much context each tier should keep. The router only ever sees a
# short message + label schema, so it can stay small and fast; agents may carry
# retrieved documents + conversation history.
_DEFAULT_NUM_CTX: dict[ModelRole, int] = {"router": 4096, "agent": 8192}


def get_chat_model(
    role: ModelRole = "agent",
    *,
    temperature: float | None = None,
    reasoning: bool | None = None,
    num_ctx: int | None = None,
    **overrides,
) -> ChatOllama:
    """Build a ``ChatOllama`` for the given role.

    Args:
        role: ``"router"`` (fast classification/guardrails) or ``"agent"``
            (specialist answering). Selects the model name + temperature default
            from :data:`settings`.
        temperature: Override the per-role default temperature.
        reasoning: Whether the model may emit chain-of-thought ("thinking").
            Defaults to ``False`` for ``router`` so structured output is clean.
            Has no effect on non-reasoning models.
        num_ctx: Override the context window size.
        **overrides: Any other ``ChatOllama`` parameter (e.g. ``format``,
            ``num_predict``, ``stop``).
    """
    if role == "router":
        model_name = settings.router_model
        default_temp = settings.router_temperature
        default_reasoning = False
    else:
        model_name = settings.agent_model
        default_temp = settings.agent_temperature
        default_reasoning = False

    return ChatOllama(
        model=model_name,
        base_url=settings.ollama_base_url,
        temperature=default_temp if temperature is None else temperature,
        reasoning=default_reasoning if reasoning is None else reasoning,
        num_ctx=_DEFAULT_NUM_CTX[role] if num_ctx is None else num_ctx,
        **overrides,
    )


@lru_cache
def get_router_model() -> ChatOllama:
    """Cached fast model for routing + guardrail classification."""
    return get_chat_model("router")


@lru_cache
def get_agent_model() -> ChatOllama:
    """Cached capable model for specialist answering + tool calling."""
    return get_chat_model("agent")


@lru_cache
def get_embeddings() -> OllamaEmbeddings:
    """Cached local embedding model used by the RAG pipeline."""
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_base_url,
    )
