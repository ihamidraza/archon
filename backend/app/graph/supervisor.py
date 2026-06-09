"""The supervisor: classify each request, then route it to a specialist.

This is the heart of Phase 4. A small, fast model (`llama3.2:3b`) reads the latest
customer message and emits a **structured** decision — which specialist should handle it
and how confident it is — using ``with_structured_output`` so we get a validated Pydantic
object instead of free text to parse.

The supervisor node only *records* that decision in the graph state; a separate routing
function (``route_from_supervisor``) reads it to pick the next node. Keeping classification
and routing separate keeps each piece trivial to test: the classifier is a pure
message → :class:`Route`, and routing is pure state → node name.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.app.core.settings import settings
from backend.app.graph.agents.specialists import SPECIALISTS
from backend.app.graph.state import SupportState
from backend.app.llm.factory import get_router_model

# The valid routing labels, derived from the specialist registry so they never drift.
Intent = Literal["billing", "technical", "account", "sales"]


class Route(BaseModel):
    """The supervisor's structured routing decision."""

    intent: Intent = Field(description="The single best specialist for this request.")
    confidence: float = Field(
        description="Confidence in the chosen specialist, from 0.0 to 1.0.",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        description="One short sentence justifying the choice (for traces/debugging)."
    )


def _routing_options() -> str:
    """Render the specialist menu the classifier chooses from."""
    return "\n".join(
        f"- {spec.key}: {spec.routing_hint}" for spec in SPECIALISTS.values()
    )


ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the routing supervisor for Nimbus customer support. Classify the "
            "customer's message into exactly one specialist team and rate your "
            "confidence.\n\n"
            "Teams:\n{options}\n\n"
            "Guidance:\n"
            "- Pick the single best-fitting team.\n"
            "- If the message is vague, off-topic, or you are unsure, still pick the "
            "closest team but give a LOW confidence (below {threshold}).\n"
            "- Judge only the latest customer message.",
        ),
        ("human", "{message}"),
    ]
)


@lru_cache
def _classifier():
    """Cached router model bound to the :class:`Route` schema."""
    return ROUTER_PROMPT | get_router_model().with_structured_output(Route)


def _latest_user_text(state: SupportState) -> str:
    """The most recent human message — what the supervisor classifies."""
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    # Fall back to the last message of any kind if no HumanMessage is present.
    return str(state["messages"][-1].content) if state["messages"] else ""


def classify(text: str) -> Route:
    """Classify a single message into a :class:`Route` (pure; easy to unit-test live)."""
    return _classifier().invoke(
        {
            "message": text,
            "options": _routing_options(),
            "threshold": settings.router_confidence_threshold,
        }
    )


def supervisor_node(state: SupportState) -> dict:
    """Classify the latest message and write the decision into state."""
    route = classify(_latest_user_text(state))
    return {"intent": route.intent, "confidence": route.confidence}


def route_from_supervisor(state: SupportState) -> str:
    """Pick the next node from the supervisor's decision.

    Low confidence routes to ``escalate`` (a human-handoff stub in Phase 4; wired to a
    real human-in-the-loop interrupt in Phase 5). Otherwise we go to the chosen
    specialist node, whose name equals the intent label.
    """
    if state.get("confidence", 0.0) < settings.router_confidence_threshold:
        return "escalate"
    return state["intent"]
