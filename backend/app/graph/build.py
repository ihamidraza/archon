"""Assemble the full guarded support graph.

Phase 4 was ``supervisor → specialist → END``. Phase 5 wraps that core in guardrails and a
human-in-the-loop:

    START
      → input_guard ─(blocked)→ refuse ─────────────────────────────→ END
            │(ok)
            ▼
        supervisor ─(out of scope)────────────────→ decline ────────→ END
            │       ─(low confidence)──────────────→ escalate (HITL) → END
            │
            ▼ (chosen specialist)
        billing │ technical │ account │ sales   (ReAct subgraphs)
            │
            ▼
        output_guard ─(grounded)─────────────────────────────────────→ END
            ├─(ungrounded, retries left)→ back to the specialist
            └─(ungrounded, exhausted)───→ escalate (HITL) → END

The specialist subgraphs are unchanged from Phase 4; everything new is a node bolted onto
the edges. Memory still lives on the parent ``compile`` — and the checkpointer is now
load-bearing, because the ``escalate`` node uses ``interrupt()`` to pause for a human.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph.agents.specialists import SPECIALISTS, build_all_specialists
from backend.app.graph.nodes.escalation import escalation_node
from backend.app.graph.nodes.input_guard import (
    input_guard_node,
    refuse_node,
    route_after_input_guard,
)
from backend.app.graph.nodes.output_guard import (
    output_guard_node,
    route_after_output_guard,
)
from backend.app.graph.state import SupportState
from backend.app.graph.supervisor import (
    decline_node,
    route_from_supervisor,
    supervisor_node,
)


def build_support_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Compile the guarded supervisor + specialists + human-in-the-loop graph.

    Args:
        checkpointer: Conversation memory, keyed by ``thread_id``. Required for the
            human-in-the-loop ``escalate`` node to pause and resume; pass an in-memory
            saver in tests.
    """
    specialists = build_all_specialists()

    builder = StateGraph(SupportState)
    builder.add_node("input_guard", input_guard_node)
    builder.add_node("refuse", refuse_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("decline", decline_node)
    builder.add_node("output_guard", output_guard_node)
    builder.add_node("escalate", escalation_node)
    for key, agent in specialists.items():
        builder.add_node(key, agent)

    # Input guardrail first; refuse blocked input, otherwise classify.
    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {"refuse": "refuse", "supervisor": "supervisor"},
    )
    builder.add_edge("refuse", END)

    # Supervisor fans out to a specialist, declines out-of-scope requests, or escalates
    # an in-scope-but-uncertain request to a human.
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {**{key: key for key in SPECIALISTS}, "decline": "decline", "escalate": "escalate"},
    )
    builder.add_edge("decline", END)

    # Every specialist's answer passes through the output guardrail.
    for key in SPECIALISTS:
        builder.add_edge(key, "output_guard")

    # Output guardrail: end, retry the specialist, or escalate to a human.
    builder.add_conditional_edges(
        "output_guard",
        route_after_output_guard,
        {**{key: key for key in SPECIALISTS}, "escalate": "escalate", "__end__": END},
    )

    builder.add_edge("escalate", END)

    return builder.compile(checkpointer=checkpointer, name="support_supervisor")
