"""Tests for the Phase 4 supervisor + specialist graph.

Unit tests verify graph wiring, the specialist registry, and the routing function with no
model calls. Live tests exercise real classification + end-to-end routing and are skipped
when Ollama is unreachable.
"""

from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from backend.app.core.settings import settings
from backend.app.graph.agents.specialists import SPECIALISTS, build_all_specialists
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_checkpointer
from backend.app.graph.supervisor import Route, classify, route_from_supervisor


# --------------------------------------------------------------------------- #
# Unit tests (no network)
# --------------------------------------------------------------------------- #
def test_graph_wires_supervisor_and_all_specialists():
    nodes = build_support_graph().get_graph().nodes
    assert "supervisor" in nodes
    assert "escalate" in nodes
    for key in ("billing", "technical", "account", "sales"):
        assert key in nodes


def test_specialist_registry_keys_match_categories():
    assert set(SPECIALISTS) == {"billing", "technical", "account", "sales"}


def test_each_specialist_has_scoped_kb_search_plus_tools():
    specialists = build_all_specialists()
    assert set(specialists) == set(SPECIALISTS)

    expected = {
        "billing": {
            "search_billing_knowledge_base",
            "lookup_invoice",
            "get_subscription_status",
        },
        "technical": {"search_technical_knowledge_base", "check_service_status"},
        "account": {"search_account_knowledge_base", "get_subscription_status"},
        "sales": {"search_sales_knowledge_base"},
    }
    for key, spec in SPECIALISTS.items():
        assert {t.name for t in spec.tools} == expected[key]


def test_route_falls_back_to_escalate_on_low_confidence():
    low = {"intent": "billing", "confidence": 0.1}
    high = {"intent": "billing", "confidence": 0.95}
    assert route_from_supervisor(low) == "escalate"
    assert route_from_supervisor(high) == "billing"


def test_route_schema_constrains_confidence():
    with pytest.raises(ValueError):
        Route(intent="billing", confidence=1.5, reasoning="too high")


# --------------------------------------------------------------------------- #
# Integration tests (need Ollama; in-memory checkpointer)
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


needs_ollama = pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")


@needs_ollama
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I was charged twice and want a refund for invoice INV-1002.", "billing"),
        ("The API returns a 500 error whenever I call the export endpoint.", "technical"),
        ("How do I enable SSO and reset my password?", "account"),
        ("What's the difference between the Pro and Enterprise plans?", "sales"),
    ],
)
def test_classify_routes_clear_messages(message: str, expected: str):
    route = classify(message)
    assert route.intent == expected
    assert 0.0 <= route.confidence <= 1.0


@needs_ollama
def test_graph_routes_and_answers_end_to_end():
    graph = build_support_graph(checkpointer=get_checkpointer(":memory:"))
    config = {"configurable": {"thread_id": "test-supervisor"}}

    result = graph.invoke(
        {"messages": [HumanMessage(content="What is your refund policy?")]},
        config=config,
    )

    assert result["intent"] == "billing"
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.content.strip()
