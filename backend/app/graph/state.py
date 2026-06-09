"""Shared state for the supervised support graph.

Phase 3 used LangGraph's built-in ``MessagesState`` (just a ``messages`` list). Phase 4
adds a **supervisor** that classifies each request, so the state needs to carry that
decision between nodes. ``SupportState`` extends ``MessagesState`` — it keeps the same
``messages`` channel (with the ``add_messages`` reducer) and adds the routing fields the
supervisor writes and the conditional edge reads.

Because specialists are compiled subgraphs that only declare ``messages``, they read and
write the shared message history transparently and simply ignore the routing fields.
Later phases extend this same state with guardrail/escalation fields (``retry_count``,
``escalate``, …).
"""

from __future__ import annotations

from typing import NotRequired

from langgraph.graph import MessagesState


class SupportState(MessagesState):
    """Conversation messages plus the supervisor's routing decision."""

    # Which specialist the supervisor picked (billing/technical/account/sales) or
    # "escalate" when confidence is too low. Absent until the supervisor runs.
    intent: NotRequired[str]
    # The supervisor's confidence in that label, 0.0–1.0.
    confidence: NotRequired[float]
