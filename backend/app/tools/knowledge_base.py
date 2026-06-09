"""Knowledge-base search exposed as a LangChain tool.

Wrapping the Phase 2 retriever as a ``@tool`` lets a ReAct agent *decide* when it needs
to look something up, rather than us always front-loading retrieval. The agent calls
``search_knowledge_base`` with a focused query and gets back cited excerpts.
"""

from __future__ import annotations

from langchain_core.tools import tool

from backend.app.rag.retriever import format_docs, get_retriever


@tool
def search_knowledge_base(query: str) -> str:
    """Search the Nimbus help center for policies, how-tos, pricing, and troubleshooting.

    Use this whenever the customer asks something that could be answered by Nimbus
    documentation (billing, technical issues, account management, plans, features).

    Args:
        query: A focused natural-language search query.

    Returns:
        Relevant documentation excerpts, each tagged with its source filename.
    """
    docs = get_retriever().invoke(query)
    if not docs:
        return "No relevant articles were found in the knowledge base."
    return format_docs(docs)
