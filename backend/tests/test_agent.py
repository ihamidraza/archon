"""Tests for the single LangGraph ReAct agent.

Unit tests verify graph wiring and tool registration without any model calls. The live
test exercises real tool-use + memory and is skipped when Ollama is unreachable.
"""

from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import HumanMessage

from backend.app.core.settings import settings
from backend.app.graph.agent import SUPPORT_TOOLS, build_support_agent
from backend.app.graph.memory import get_checkpointer


# --------------------------------------------------------------------------- #
# Unit tests (no network)
# --------------------------------------------------------------------------- #
def test_agent_graph_has_react_loop():
    graph = build_support_agent().get_graph()
    assert "agent" in graph.nodes
    assert "tools" in graph.nodes


def test_support_agent_registers_expected_tools():
    names = {t.name for t in SUPPORT_TOOLS}
    assert names == {
        "search_knowledge_base",
        "get_subscription_status",
        "lookup_invoice",
        "check_service_status",
    }


def test_in_memory_checkpointer_builds():
    saver = get_checkpointer(":memory:")
    assert saver is not None


# --------------------------------------------------------------------------- #
# Integration test (needs Ollama; in-memory checkpointer)
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_agent_remembers_across_turns():
    agent = build_support_agent(checkpointer=get_checkpointer(":memory:"))
    config = {"configurable": {"thread_id": "test-thread"}}

    # The Phase 3 feature under test is the checkpointer carrying conversation history
    # across separate invocations of the same thread_id. We assert on that mechanism (the
    # first turn is present in the second turn's state) rather than on whether the small
    # model chooses to echo a remembered detail, which is persona-dependent and flaky.
    agent.invoke(
        {"messages": [HumanMessage(content="My name is Riley Parker.")]},
        config=config,
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content="What's my name?")]},
        config=config,
    )

    history = " ".join(str(m.content) for m in result["messages"])
    assert "Riley Parker" in history  # first turn persisted into the second
    assert len(result["messages"]) >= 4  # both turns accumulated, not reset
