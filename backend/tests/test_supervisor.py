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
from backend.app.graph.supervisor import (
    OUT_OF_SCOPE_MESSAGE,
    Route,
    _active_specialist_awaiting_reply,
    _looks_like_answer,
    classify,
    decline_node,
    requests_human,
    route_from_supervisor,
    supervisor_node,
    wants_human_handoff,
)


# --------------------------------------------------------------------------- #
# Unit tests (no network)
# --------------------------------------------------------------------------- #
def test_graph_wires_supervisor_and_all_specialists():
    nodes = build_support_graph().get_graph().nodes
    assert "supervisor" in nodes
    assert "escalate" in nodes
    assert "decline" in nodes
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
    low = {"intent": "billing", "confidence": 0.1, "in_scope": True}
    high = {"intent": "billing", "confidence": 0.95, "in_scope": True}
    assert route_from_supervisor(low) == "escalate"
    assert route_from_supervisor(high) == "billing"


def test_route_declines_out_of_scope_before_escalating():
    # Out of scope wins over confidence: an off-topic question is declined, not handed to
    # a human — even if the (meaningless) confidence is low.
    off_topic = {"intent": "technical", "confidence": 0.1, "in_scope": False}
    assert route_from_supervisor(off_topic) == "decline"


def test_decline_node_returns_standard_message():
    result = decline_node({"messages": []})
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.content == OUT_OF_SCOPE_MESSAGE


def test_route_schema_carries_scope_flag():
    route = Route(in_scope=False, intent="billing", confidence=0.0, reasoning="off-topic")
    assert route.in_scope is False


# --------------------------------------------------------------------------- #
# Human-handoff requests always escalate (never decline) — offline
# --------------------------------------------------------------------------- #
def test_wants_human_handoff_detects_explicit_requests():
    for text in (
        "yes. connect me with human agent",
        "can I talk to a human?",
        "please transfer me to an agent",
        "I'd like to speak to a real person",
        "connect me with a representative",
        "live agent please",
    ):
        assert wants_human_handoff(text), text


def test_wants_human_handoff_ignores_lookalikes():
    # "agent" in a technical sense, or a plain affirmation, must not trigger a handoff.
    assert not wants_human_handoff("what is the agent status of my export job?")
    assert not wants_human_handoff("yes, I was charged twice this month")
    assert not wants_human_handoff("how do I add a team member?")


def test_requests_human_on_affirmation_after_offer():
    offered = {
        "messages": [
            AIMessage(content="Would you like me to connect you with a human agent?"),
            HumanMessage(content="yes please"),
        ]
    }
    assert requests_human(offered)
    # The same "yes" with no prior human offer is just an affirmation, not a handoff.
    bare = {"messages": [HumanMessage(content="yes please")]}
    assert not requests_human(bare)


def test_human_request_escalates_over_scope_and_confidence():
    # escalation_requested beats both the decline and specialist paths.
    state = {"escalation_requested": True, "in_scope": False, "confidence": 0.99}
    assert route_from_supervisor(state) == "escalate"


def test_supervisor_node_flags_human_request_without_classifying():
    # No model call needed: the explicit request is detected deterministically.
    state = {"messages": [HumanMessage(content="connect me with a human agent")]}
    update = supervisor_node(state)
    assert update["escalation_requested"] is True
    assert update["escalation_reason"] == "customer_requested_human"
    assert update["in_scope"] is True


# --------------------------------------------------------------------------- #
# Conversation continuity: a reply to a specialist's question stays with it
# --------------------------------------------------------------------------- #
def _pending_account_thread() -> dict:
    """Thread state where the account specialist just asked for the customer's email."""
    return {
        "intent": "account",
        "messages": [
            HumanMessage(content="My subscription is not working"),
            AIMessage(content="Could you please provide the email on your Nimbus account?"),
            HumanMessage(content="hamid@new.co"),
        ],
    }


def test_active_specialist_detected_when_question_pending():
    assert _active_specialist_awaiting_reply(_pending_account_thread()) == "account"


def test_active_specialist_detected_when_question_is_not_at_end():
    # Regression: the specialist asks mid-sentence but the message ends with a statement.
    state = {
        "intent": "billing",
        "messages": [
            HumanMessage(content="I subscribed yesterday, now I want a refund"),
            AIMessage(
                content="To help with a refund, could you provide your account email or "
                "an invoice ID? This lets me look up your subscription details."
            ),
            HumanMessage(content="hamid@new.co"),
        ],
    }
    assert _active_specialist_awaiting_reply(state) == "billing"


def test_active_specialist_detected_for_answer_after_a_statement_request():
    # The specialist requested info without a literal "?"; an ID reply still continues it.
    state = {
        "intent": "billing",
        "messages": [
            HumanMessage(content="I was overcharged"),
            AIMessage(content="Please share your invoice ID."),
            HumanMessage(content="INV-1002"),
        ],
    }
    assert _active_specialist_awaiting_reply(state) == "billing"


def test_no_active_specialist_without_pending_question():
    # A specialist statement that doesn't ask anything isn't awaiting a reply.
    state = {
        "intent": "account",
        "messages": [
            HumanMessage(content="hi"),
            AIMessage(content="Here's how SSO works. Glad to help further."),
            HumanMessage(content="what's the weather"),
        ],
    }
    assert _active_specialist_awaiting_reply(state) is None


def test_no_active_specialist_after_decline_reply():
    # The canned out-of-scope reply doesn't count as a pending specialist question.
    state = {
        "intent": "account",
        "messages": [
            HumanMessage(content="tell me a joke"),
            AIMessage(content=OUT_OF_SCOPE_MESSAGE),
            HumanMessage(content="hamid@new.co"),
        ],
    }
    assert _active_specialist_awaiting_reply(state) is None


def test_looks_like_answer():
    # Bare answers to a pending question.
    assert _looks_like_answer("hamid@new.co")
    assert _looks_like_answer("INV-1002")
    assert _looks_like_answer("42")
    assert _looks_like_answer("yes please")
    assert _looks_like_answer("John Smith")
    # A new question/request is NOT an answer — topic switches must not be mistaken for one.
    assert not _looks_like_answer("what's the weather")
    assert not _looks_like_answer("how much is the Pro plan?")
    assert not _looks_like_answer(
        "I want to compare the Pro and Enterprise plans before upgrading my team"
    )


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


@needs_ollama
def test_followup_answer_stays_with_active_specialist():
    # A bare email answering the account agent's question must route back to account,
    # not be re-classified (and declined/mis-routed) as a standalone message.
    update = supervisor_node(_pending_account_thread())
    assert update["intent"] == "account"
    assert update["in_scope"] is True


@needs_ollama
def test_off_topic_is_declined_not_escalated():
    graph = build_support_graph(checkpointer=get_checkpointer(":memory:"))
    config = {"configurable": {"thread_id": "test-off-topic"}}

    result = graph.invoke(
        {"messages": [HumanMessage(content="What's the capital of France?")]},
        config=config,
    )

    # Out-of-scope ⇒ standard decline reply, and the graph did not pause for a human.
    assert result.get("in_scope") is False
    assert result["messages"][-1].content == OUT_OF_SCOPE_MESSAGE
    assert not [t.interrupts for t in graph.get_state(config).tasks if t.interrupts]
