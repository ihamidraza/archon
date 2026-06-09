"""Ingestion pipeline: knowledge-base markdown → chunks → Chroma vectors.

Pipeline stages:
  1. **Load**   — read every ``*.md`` file under the knowledge-base directory.
  2. **Split**  — break documents into overlapping chunks small enough to embed and
                  retrieve precisely, while attaching ``source``/``category`` metadata.
  3. **Embed & store** — embed each chunk with ``nomic-embed-text`` and persist to Chroma.

The ``category`` metadata (billing / technical / account / sales / general) is what lets
each Phase 4 specialist retrieve only from its own slice of the knowledge base.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.app.core.settings import settings
from backend.app.rag.vectorstore import get_vectorstore
from backend.scripts.seed_data import KNOWLEDGE_BASE

# Chunk sizing: large enough to keep a policy paragraph intact, small enough that a
# retrieved chunk is mostly relevant signal. Overlap preserves context across splits.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# filename -> category, derived from the seed manifest (single source of truth).
_CATEGORY_BY_FILENAME = {doc.filename: doc.category for doc in KNOWLEDGE_BASE}
_TITLE_BY_FILENAME = {doc.filename: doc.title for doc in KNOWLEDGE_BASE}


def load_documents(kb_dir: Path | None = None) -> list[Document]:
    """Load knowledge-base markdown files into LangChain ``Document`` objects.

    Each document carries ``source``, ``category``, and ``title`` metadata. Files not
    present in the seed manifest fall back to the ``general`` category.
    """
    directory = kb_dir or settings.kb_path
    docs: list[Document] = []
    for path in sorted(directory.glob("*.md")):
        category = _CATEGORY_BY_FILENAME.get(path.name, "general")
        title = _TITLE_BY_FILENAME.get(path.name, path.stem)
        docs.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={"source": path.name, "category": category, "title": title},
            )
        )
    return docs


def split_documents(docs: list[Document]) -> list[Document]:
    """Split documents into overlapping chunks, preserving metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    return splitter.split_documents(docs)


def ingest(
    *,
    kb_dir: Path | None = None,
    persist_directory: str | None = None,
    collection_name: str | None = None,
    reset: bool = True,
) -> int:
    """Run the full pipeline and persist vectors to Chroma.

    Args:
        reset: Drop any existing vectors in the collection first, so re-running
            ``make ingest`` produces a clean store instead of duplicates.

    Returns:
        The number of chunks embedded and stored.
    """
    store = get_vectorstore(
        persist_directory=persist_directory, collection_name=collection_name
    )
    if reset:
        # Clear the collection without deleting the whole on-disk database.
        existing = store.get()
        if existing and existing.get("ids"):
            store.delete(ids=existing["ids"])

    chunks = split_documents(load_documents(kb_dir))
    if chunks:
        store.add_documents(chunks)
    return len(chunks)
