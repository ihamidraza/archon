"""A hand-built ReAct agent in LangGraph — the core agent loop, explained.

LangGraph ships a one-liner (`langchain.agents.create_agent`) that does all of this,
but we build it by hand once so the mechanics are clear. Every specialist in Phase 4 is
an instance of this same loop, just with different tools and instructions.

The ReAct loop is two nodes and a decision:

        ┌──────────────────────────────────────────────┐
        │                                              ▼
    START ──▶ [agent] ──(has tool calls?)──▶ [tools] ──┘   (loop back to agent)
                  │
            (no tool calls)
                  ▼
                 END
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from backend.app.llm.factory import get_agent_model
from backend.app.llm.text import strip_reasoning


def build_react_agent(
    *,
    tools: Sequence[BaseTool],
    system_prompt: str,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    name: str | None = None,
) -> CompiledStateGraph:
    """Compile a ReAct agent over ``tools`` with a fixed ``system_prompt``.

    Args:
        tools: The tools the agent may call.
        system_prompt: Persona + instructions, prepended on every model call.
        model: Chat model (defaults to the capable agent-tier model).
        checkpointer: Optional memory; pass one to persist conversations by thread_id.
        name: Optional graph name (useful when nested as a subgraph in Phase 4).
    """
    llm = (model or get_agent_model()).bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        """Call the LLM with the system prompt + running conversation."""
        # The system prompt is prepended fresh each call rather than stored in state,
        # so it never duplicates as the message history grows.
        messages = [SystemMessage(content=system_prompt), *state["messages"]]
        result = llm.invoke(messages)
        # Defensively strip any leaked <think>…</think> reasoning from the answer text
        # (some Ollama models ignore reasoning=False). Tool calls are preserved.
        if isinstance(result.content, str):
            cleaned = strip_reasoning(result.content)
            if cleaned != result.content:
                result = result.model_copy(update={"content": cleaned})
        return {"messages": [result]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(list(tools)))

    builder.add_edge(START, "agent")
    # tools_condition routes to "tools" if the last AI message requested tool calls,
    # otherwise to END.
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")  # feed tool results back for another reasoning step

    return builder.compile(checkpointer=checkpointer, name=name)
