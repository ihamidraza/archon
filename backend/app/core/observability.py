"""LangSmith tracing, run tagging, and feedback — Archon's observability layer.

LangChain/LangGraph emit traces automatically *when the right environment variables are
set*. The catch: those are read from ``os.environ``, but our config lives in a
``.env``-backed ``settings`` object. :func:`configure_tracing` bridges the two — it copies
the LangSmith settings into ``os.environ`` so the global tracer picks them up, but only
when a real API key is present. With no key (the default, zero-cost path) tracing stays
off and everything still runs locally.

On top of raw tracing this module adds the two things that make traces *useful*:

* :func:`run_config` — a consistent ``RunnableConfig`` (tags + metadata + thread id) to
  attach to every graph invocation, so runs are filterable in the LangSmith UI.
* :func:`log_feedback` — record a score/comment against a run (thumbs up/down from the CLI,
  or automated signals), degrading to a no-op when tracing is off.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from backend.app.core.settings import settings

# Substrings that mark the shipped placeholder key in `.env.example` as "not a real key".
_PLACEHOLDER_MARKERS = ("replace-me", "your-key", "...", "xxx")


def _is_real_key(key: str) -> bool:
    """True if ``key`` looks like a genuine LangSmith API key (not blank/placeholder)."""
    if not key or not key.startswith("ls"):
        return False
    return not any(marker in key for marker in _PLACEHOLDER_MARKERS)


def configure_tracing(*, force: bool | None = None) -> bool:
    """Enable or disable LangSmith tracing by syncing settings → ``os.environ``.

    Args:
        force: Override the decision (``True``/``False``). When ``None`` (default), tracing
            is enabled iff ``LANGCHAIN_TRACING_V2`` is set *and* a real API key is present.

    Returns:
        Whether tracing was enabled.
    """
    enabled = (
        settings.langchain_tracing_v2 and _is_real_key(settings.langchain_api_key)
        if force is None
        else force
    )

    if not enabled:
        # Explicitly off so a stray shell env var can't half-enable a broken tracer.
        # NB: never set bare ``LANGCHAIN_TRACING`` — that's the removed V1 flag and raises.
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        return False

    # Modern flags only: ``LANGCHAIN_TRACING_V2`` (compat) and ``LANGSMITH_TRACING`` (new).
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    # Endpoint/key/project are read under either prefix — set both, they're harmless.
    for prefix in ("LANGCHAIN", "LANGSMITH"):
        os.environ[f"{prefix}_ENDPOINT"] = settings.langchain_endpoint
        os.environ[f"{prefix}_API_KEY"] = settings.langchain_api_key
        os.environ[f"{prefix}_PROJECT"] = settings.langchain_project
    return True


def tracing_enabled() -> bool:
    """Whether tracing is currently switched on in the process environment."""
    return os.environ.get("LANGCHAIN_TRACING_V2") == "true"


def run_config(
    thread_id: str | None = None,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    """Build a ``RunnableConfig`` with consistent tags/metadata for a graph run.

    Always includes the ``archon`` tag and an ``app`` metadata key so every traced run is
    easy to find and filter in LangSmith, plus the ``thread_id`` (also used by the
    checkpointer) for correlating a multi-turn conversation.
    """
    config: dict[str, Any] = {}

    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    run_tags = ["archon"]
    run_tags += [t for t in (tags or []) if t not in run_tags]
    config["tags"] = run_tags

    run_metadata: dict[str, Any] = {"app": "archon"}
    if thread_id:
        run_metadata["thread_id"] = thread_id
    if metadata:
        run_metadata.update(metadata)
    config["metadata"] = run_metadata

    if run_name:
        config["run_name"] = run_name
    return config


@lru_cache
def get_client():
    """Return a cached LangSmith ``Client`` when tracing is on, else ``None``."""
    if not tracing_enabled():
        return None
    try:
        from langsmith import Client

        return Client()
    except Exception:  # noqa: BLE001 — never let observability break the app
        return None


def log_feedback(
    run_id: str | None,
    *,
    key: str = "user_score",
    score: float | None = None,
    comment: str | None = None,
) -> bool:
    """Record feedback against a traced run. No-op (returns ``False``) when tracing is off.

    Args:
        run_id: The traced run's id (see :func:`run_id_from`); ``None`` is ignored.
        key: Feedback channel, e.g. ``"user_score"`` or ``"groundedness"``.
        score: Numeric score (commonly 0.0–1.0).
        comment: Optional free-text note.
    """
    client = get_client()
    if client is None or run_id is None:
        return False
    try:
        client.create_feedback(run_id, key=key, score=score, comment=comment)
        return True
    except Exception:  # noqa: BLE001
        return False


def run_url(run_id: str | None) -> str | None:
    """Best-effort LangSmith UI URL for a run, or ``None`` if unavailable."""
    client = get_client()
    if client is None or run_id is None:
        return None
    try:
        return client.read_run(run_id).url
    except Exception:  # noqa: BLE001
        return None
