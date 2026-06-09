"""Tests for the RAG pipeline.

Unit tests (no network) cover seeding, loading, and splitting. The retrieval test
actually embeds with Ollama, so it ingests into a *temporary* Chroma directory and is
skipped when Ollama is unreachable — keeping `make test` fast and isolated.
"""

from __future__ import annotations

import httpx
import pytest

from backend.app.core.settings import settings
from backend.app.rag import ingest as ingest_mod
from backend.scripts.seed_data import CATEGORIES, KNOWLEDGE_BASE, seed


# --------------------------------------------------------------------------- #
# Unit tests (no network)
# --------------------------------------------------------------------------- #
def test_seed_writes_all_documents():
    paths = seed()
    assert len(paths) == len(KNOWLEDGE_BASE)
    for doc in KNOWLEDGE_BASE:
        assert (settings.kb_path / doc.filename).exists()


def test_every_seed_doc_has_a_known_category():
    for doc in KNOWLEDGE_BASE:
        assert doc.category in CATEGORIES


def test_load_documents_attach_category_metadata():
    seed()
    docs = ingest_mod.load_documents()
    assert docs, "expected knowledge-base documents to load"
    for d in docs:
        assert d.metadata["category"] in CATEGORIES
        assert d.metadata["source"].endswith(".md")
        assert d.page_content.strip()


def test_split_preserves_metadata_and_shrinks_chunks():
    seed()
    docs = ingest_mod.load_documents()
    chunks = ingest_mod.split_documents(docs)
    assert len(chunks) >= len(docs)  # splitting never reduces count
    for c in chunks:
        assert c.metadata["category"] in CATEGORIES
        assert len(c.page_content) <= ingest_mod.CHUNK_SIZE + ingest_mod.CHUNK_OVERLAP


# --------------------------------------------------------------------------- #
# Integration test (needs Ollama embeddings; isolated temp Chroma dir)
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_retrieval_returns_relevant_category(tmp_path):
    seed()
    persist = str(tmp_path / "chroma")
    collection = "test_kb"
    n = ingest_mod.ingest(persist_directory=persist, collection_name=collection)
    assert n > 0

    from backend.app.rag.retriever import get_retriever

    hits = get_retriever(
        k=3, persist_directory=persist, collection_name=collection
    ).invoke("I was charged twice and want a refund")
    assert hits, "expected at least one retrieved chunk"
    assert hits[0].metadata["category"] == "billing"


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_category_filter_restricts_results(tmp_path):
    seed()
    persist = str(tmp_path / "chroma")
    collection = "test_kb_filter"
    ingest_mod.ingest(persist_directory=persist, collection_name=collection)

    from backend.app.rag.retriever import get_retriever

    hits = get_retriever(
        category="sales", k=4, persist_directory=persist, collection_name=collection
    ).invoke("anything")
    assert hits
    assert all(d.metadata["category"] == "sales" for d in hits)
