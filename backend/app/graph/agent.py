"""The Phase 3 single support agent.

One general-purpose ReAct agent with access to the knowledge base and the mock business
tools. Phase 4 will split this into a supervisor routing to four specialists, but the
agent loop stays identical — only the tool set and instructions change.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph.react_agent import build_react_agent
from backend.app.llm.prompts import SUPPORT_SYSTEM_PROMPT
from backend.app.tools.knowledge_base import search_knowledge_base
from backend.app.tools.mock_account import (
    check_service_status,
    get_subscription_status,
    lookup_invoice,
)

SUPPORT_TOOLS = [
    search_knowledge_base,
    get_subscription_status,
    lookup_invoice,
    check_service_status,
]

AGENT_INSTRUCTIONS = (
    SUPPORT_SYSTEM_PROMPT
    + "\n\nYou have tools available:\n"
    "- search_knowledge_base: for policies, how-tos, pricing, and troubleshooting.\n"
    "- get_subscription_status / lookup_invoice: for account-specific lookups (ask for "
    "the email or invoice ID first if you don't have it).\n"
    "- check_service_status: to confirm whether services are operational.\n"
    "Prefer searching the knowledge base before answering policy questions. Always base "
    "answers on tool results, and cite knowledge-base sources when you use them."
)


def build_support_agent(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the single support agent, optionally with conversation memory."""
    return build_react_agent(
        tools=SUPPORT_TOOLS,
        system_prompt=AGENT_INSTRUCTIONS,
        checkpointer=checkpointer,
        name="support_agent",
    )
