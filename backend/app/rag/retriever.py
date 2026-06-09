"""Retrieval + grounded question answering over the Chroma knowledge base.

Two things live here:

* ``get_retriever`` — a configured Chroma retriever, optionally filtered to one
  ``category`` so a specialist only sees its own documents.
* ``build_qa_chain`` / ``answer_question`` — an LCEL chain that retrieves context and
  instructs the model to answer **only** from it, citing sources, and to defer to a
  human when the answer isn't in the documents. This "grounding" is the first line of
  defense against hallucination; Phase 5 adds an automated check that verifies it.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.vectorstores import VectorStoreRetriever

from backend.app.core.settings import settings
from backend.app.llm.factory import get_agent_model
from backend.app.llm.prompts import SUPPORT_SYSTEM_PROMPT
from backend.app.rag.vectorstore import get_vectorstore

GROUNDED_QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUPPORT_SYSTEM_PROMPT),
        (
            "human",
            "Answer the customer's question using ONLY the context below. If the answer "
            "is not in the context, say you don't have that information and offer to "
            "connect them with a human agent — do not guess. Cite the sources you used "
            "in square brackets, e.g. [billing-refunds.md].\n\n"
            "Context:\n{context}\n\n"
            "Question: {question}",
        ),
    ]
)


def get_retriever(
    *,
    category: str | None = None,
    k: int | None = None,
    persist_directory: str | None = None,
    collection_name: str | None = None,
) -> VectorStoreRetriever:
    """Return a Chroma retriever, optionally restricted to a single category."""
    store = get_vectorstore(
        persist_directory=persist_directory, collection_name=collection_name
    )
    search_kwargs: dict = {"k": k or settings.rag_top_k}
    if category:
        search_kwargs["filter"] = {"category": category}
    return store.as_retriever(search_kwargs=search_kwargs)


def format_docs(docs: list[Document]) -> str:
    """Render retrieved documents into a single context string with source tags."""
    return "\n\n".join(f"[{d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs)


def build_qa_chain(*, category: str | None = None, k: int | None = None):
    """Compose retrieve → ground → answer into a single runnable returning a string."""
    retriever = get_retriever(category=category, k=k)
    return (
        {"context": retriever | RunnableLambda(format_docs), "question": RunnablePassthrough()}
        | GROUNDED_QA_PROMPT
        | get_agent_model()
        | StrOutputParser()
    )


def answer_question(question: str, *, category: str | None = None, k: int | None = None) -> dict:
    """Answer a question and return both the answer and the source documents used.

    Retrieves once and reuses the same context for the answer, so the returned
    ``sources`` are exactly what the model saw.

    Returns:
        ``{"answer": str, "sources": list[Document]}``.
    """
    sources = get_retriever(category=category, k=k).invoke(question)
    answer = (GROUNDED_QA_PROMPT | get_agent_model() | StrOutputParser()).invoke(
        {"context": format_docs(sources), "question": question}
    )
    return {"answer": answer, "sources": sources}
