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
    """Conversation messages, the supervisor's routing decision, and guardrail signals."""

    # --- Routing (Phase 4) ---
    # Which specialist the supervisor picked (billing/technical/account/sales) or
    # "escalate" when confidence is too low. Absent until the supervisor runs.
    intent: NotRequired[str]
    # The supervisor's confidence in that label, 0.0–1.0.
    confidence: NotRequired[float]
    # Whether the latest message is about Nimbus at all. False routes to a standard
    # out-of-scope reply (``decline``) instead of escalating to a human.
    in_scope: NotRequired[bool]
    # Set when the customer explicitly asks for a human (or accepts our offer of one), so
    # the request always reaches the escalate node rather than the decline path.
    escalation_requested: NotRequired[bool]

    # --- Guardrails (Phase 5) ---
    # Set by the input guardrail when a message is refused (e.g. prompt injection).
    blocked: NotRequired[bool]
    block_reason: NotRequired[str]
    # Token→original map of high-risk PII redacted from the input, for a human handoff.
    pii_map: NotRequired[dict[str, str]]
    # How many times the output guardrail has bounced the answer back for a retry.
    retry_count: NotRequired[int]
    # The output guardrail's verdict for the current step: "ok" | "retry" | "escalate".
    # Refreshed every time the node runs, so the routing edge reads a current value.
    guard_decision: NotRequired[str]
    # Why the conversation was escalated to a human (for the escalation node + traces).
    escalation_reason: NotRequired[str]
