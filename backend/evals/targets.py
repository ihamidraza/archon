"""Targets — the functions under evaluation.

Each takes a dataset example's ``inputs`` dict and returns an ``outputs`` dict that the
evaluators score. They're the seam between "the system" and "the measurement":

* :func:`route_target` — just the supervisor classifier (fast, router model only).
* :func:`guardrail_target` — the input-guardrail decision (deterministic, no model).
* :func:`qa_target` — the *whole* guarded graph end-to-end, returning the final answer plus
  the retrieval context used, so groundedness can be judged.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_checkpointer
from backend.app.graph.supervisor import classify
from backend.app.guardrails.injection import detect_injection
from backend.app.guardrails.pii import detect, redact


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_target(inputs: dict) -> dict:
    """Classify a message into a specialist intent + confidence."""
    route = classify(inputs["message"])
    return {"intent": route.intent, "confidence": route.confidence}


# --------------------------------------------------------------------------- #
# Guardrails (deterministic — no model)
# --------------------------------------------------------------------------- #
def _entity_types(token_map: dict[str, str]) -> list[str]:
    """Recover entity types from redaction tokens like ``<CREDIT_CARD_1>``."""
    return sorted({token.strip("<>").rsplit("_", 1)[0] for token in token_map})


def guardrail_target(inputs: dict) -> dict:
    """Mirror the input guardrail's decision: refuse / redact / allow."""
    text = inputs["message"]

    injection = detect_injection(text)
    if injection.flagged:
        return {"action": "refuse", "entities": [], "block_reason": injection.categories}

    redacted, token_map, detected = redact(text)
    if token_map:
        return {"action": "redact", "entities": _entity_types(token_map), "redacted": redacted}

    # Clean (possibly with low-risk contact info that's intentionally passed through).
    return {"action": "allow", "entities": [s.entity_type for s in detect(text)]}


# --------------------------------------------------------------------------- #
# End-to-end QA
# --------------------------------------------------------------------------- #
_qa_graph = None


def _graph():
    """Lazily build one in-memory graph reused across QA examples."""
    global _qa_graph
    if _qa_graph is None:
        _qa_graph = build_support_graph(checkpointer=get_checkpointer(":memory:"))
    return _qa_graph


def qa_target(inputs: dict) -> dict:
    """Run the full guarded graph and return the answer + retrieval context + route."""
    graph = _graph()
    config = {"configurable": {"thread_id": f"eval-{uuid4().hex[:8]}"}}
    result = graph.invoke({"messages": [HumanMessage(content=inputs["message"])]}, config=config)

    messages = result.get("messages", [])

    answer = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            answer = str(message.content)
            break

    # Context = tool outputs produced for the final answer (since the last user message).
    context_chunks: list[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            context_chunks.append(str(message.content))

    return {
        "answer": answer,
        "intent": result.get("intent"),
        "context": "\n\n".join(reversed(context_chunks)),
    }
