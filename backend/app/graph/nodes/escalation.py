"""Escalation node — a real human-in-the-loop handoff via LangGraph ``interrupt``.

When the supervisor is unsure or the output guardrail can't get a grounded answer, we stop
automating and bring in a person. ``interrupt()`` **pauses the whole graph** mid-run and
returns control to the caller; the conversation state is durably saved by the checkpointer
(hence escalation requires memory). The caller (CLI in Phase 5, the API in Phase 8) shows
the pending request to a human agent, then **resumes** the graph with
``Command(resume=<agent reply>)`` — at which point ``interrupt()`` returns that reply and
the node delivers it to the customer.

This is the same pause/resume machinery foreshadowed since Phase 3; the checkpointer is
what makes "stop now, continue later, possibly in a different process" possible.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from backend.app.graph.state import SupportState


def _latest_user_text(state: SupportState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def escalation_node(state: SupportState) -> dict:
    """Pause for a human agent, then relay their reply to the customer."""
    reason = state.get("escalation_reason") or "low_confidence_routing"

    # Pauses here. The payload is what a human agent sees; the return value is whatever
    # the caller passes via Command(resume=...). On the first pass this never returns —
    # the graph run ends with an interrupt the caller must handle.
    agent_reply = interrupt(
        {
            "reason": reason,
            "customer_message": _latest_user_text(state),
            "instructions": "A human agent should review and reply to this customer.",
        }
    )

    return {
        "messages": [AIMessage(content=str(agent_reply))],
        "escalation_reason": reason,
    }
