"""CLI entrypoint for building the knowledge base — run via ``make ingest``.

Steps:
  1. Seed the synthetic Nimbus docs (if they don't already exist).
  2. Load → split → embed → persist into Chroma.
  3. Print a short summary and a sample retrieval so you can eyeball quality.
"""

from __future__ import annotations

from backend.app.core.settings import settings
from backend.app.rag.ingest import ingest, load_documents
from backend.app.rag.retriever import get_retriever
from backend.scripts.seed_data import seed


def main() -> None:
    print("1) Seeding synthetic knowledge base…")
    paths = seed()
    print(f"   {len(paths)} documents in {settings.kb_path}")

    print("2) Ingesting into Chroma (embedding with nomic-embed-text)…")
    n_docs = len(load_documents())
    n_chunks = ingest()
    print(f"   {n_docs} documents → {n_chunks} chunks → {settings.chroma_path}")

    print("3) Sample retrieval for 'I was double charged':")
    hits = get_retriever(k=3).invoke("I was double charged this month")
    for d in hits:
        print(f"   • [{d.metadata['category']}] {d.metadata['source']}")

    print("\n✅ Knowledge base ready.")


if __name__ == "__main__":
    main()
