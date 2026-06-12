"""Knowledge-base search exposed as a LangChain tool.

Wrapping the Phase 2 retriever as a ``@tool`` lets a ReAct agent *decide* when it needs
to look something up, rather than us always front-loading retrieval. The agent calls
``search_knowledge_base`` with a focused query and gets back cited excerpts.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool, tool

from backend.app.rag.retriever import format_docs, get_retriever

# Phrased as a neutral internal signal: if the model echoes it verbatim, it still doesn't
# leak that there's a knowledge base / RAG pipeline behind the assistant.
_NO_RESULTS = "No matching information is available for this query."


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
        return _NO_RESULTS
    return format_docs(docs)


def make_kb_search_tool(category: str, label: str) -> BaseTool:
    """Build a knowledge-base search tool scoped to a single ``category``.

    Phase 4 gives each specialist its *own* search tool that only ever retrieves from
    its domain (e.g. the billing specialist can't accidentally surface sales docs). The
    retriever's ``category`` filter does the scoping; here we wrap it as a distinctly
    named tool with a tailored description so the specialist model knows exactly what it
    searches.

    Args:
        category: The KB category to filter on (``billing``/``technical``/…).
        label: Human-friendly domain name used in the tool description.
    """

    def _search(query: str) -> str:
        docs = get_retriever(category=category).invoke(query)
        if not docs:
            return _NO_RESULTS
        return format_docs(docs)

    return StructuredTool.from_function(
        func=_search,
        name=f"search_{category}_knowledge_base",
        description=(
            f"Search the Nimbus {label} help articles for policies, how-tos, and "
            "details in this domain. Pass a focused natural-language query; returns "
            "documentation excerpts tagged with their source filename."
        ),
    )
