"""Assemble the supervised support graph: supervisor → specialist → end.

This wires the Phase 4 system together:

    START → supervisor → (conditional) → one specialist subgraph → END
                              └─ low confidence ─→ escalate → END

The supervisor classifies; a conditional edge fans out to one of the four specialist
subgraphs (or the escalation stub). Each specialist is the Phase 3 ReAct loop nested as a
subgraph — because the parent :class:`SupportState` extends ``MessagesState``, the shared
``messages`` channel flows in and out of each subgraph automatically.

Memory works exactly as in Phase 3: pass a checkpointer here (the parent), not to the
specialists, and the whole multi-agent conversation is persisted per ``thread_id``.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph.agents.specialists import SPECIALISTS, build_all_specialists
from backend.app.graph.state import SupportState
from backend.app.graph.supervisor import route_from_supervisor, supervisor_node

ESCALATION_MESSAGE = (
    "Thanks for your patience. I want to make sure you get the right help, so I'm "
    "connecting you with a human teammate who can take it from here. Could you share a "
    "little more detail about what you need while I hand this off?"
)


def escalate_node(state: SupportState) -> dict:
    """Human-handoff stub for low-confidence routes.

    In Phase 4 this just returns a polite handoff message. Phase 5 replaces it with a
    real human-in-the-loop ``interrupt`` that pauses the graph until a human responds.
    """
    return {"messages": [AIMessage(content=ESCALATION_MESSAGE)]}


def build_support_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Compile the full supervisor + specialists graph.

    Args:
        checkpointer: Optional memory for the whole conversation, keyed by ``thread_id``.
            Specialists are nested without their own checkpointer so this one owns state.
    """
    specialists = build_all_specialists()

    builder = StateGraph(SupportState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("escalate", escalate_node)
    for key, agent in specialists.items():
        # A compiled subgraph is a valid node; it reads/writes the shared messages channel.
        builder.add_node(key, agent)

    builder.add_edge(START, "supervisor")
    # Fan out from the supervisor to exactly one specialist (or the escalation stub).
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {**{key: key for key in SPECIALISTS}, "escalate": "escalate"},
    )
    # Each terminal node ends the turn; the next user message re-enters at the supervisor.
    for key in SPECIALISTS:
        builder.add_edge(key, END)
    builder.add_edge("escalate", END)

    return builder.compile(checkpointer=checkpointer, name="support_supervisor")
