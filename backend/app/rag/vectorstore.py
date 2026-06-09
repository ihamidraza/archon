"""Chroma vector store access — a local, persistent, zero-cost vector DB.

This module is the single place that knows *how* to connect to Chroma. Callers ask
for a configured store and never touch Chroma's constructor directly, so the
embedding model, persistence directory, and collection name stay consistent.
"""

from __future__ import annotations

from langchain_chroma import Chroma

from backend.app.core.settings import settings
from backend.app.llm.factory import get_embeddings


def get_vectorstore(
    *,
    persist_directory: str | None = None,
    collection_name: str | None = None,
) -> Chroma:
    """Return a Chroma store backed by the local ``nomic-embed-text`` embeddings.

    Args:
        persist_directory: Where vectors live on disk. Defaults to
            ``settings.chroma_path``. Override (e.g. a tmp dir) for isolated tests.
        collection_name: Chroma collection. Defaults to ``settings.chroma_collection``.
    """
    directory = persist_directory or str(settings.chroma_path)
    return Chroma(
        collection_name=collection_name or settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=directory,
    )
