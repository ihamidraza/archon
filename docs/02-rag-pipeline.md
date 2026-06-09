# Phase 2 — RAG Pipeline (Grounded Knowledge Base)

> **Goal:** give the agent real knowledge to answer from. We generate a synthetic
> knowledge base for the fictional **Nimbus** SaaS, embed it locally with
> `nomic-embed-text`, store the vectors in **Chroma**, and build a **grounded** retriever
> that answers *only* from retrieved context — the foundation for trustworthy support.

**RAG** (Retrieval-Augmented Generation) = retrieve relevant documents for a question,
then ask the model to answer using them. It's how we keep answers accurate and current
without fine-tuning, and how we make the model say *"I don't know"* instead of inventing
policies.

---

## 1. The synthetic knowledge base (`backend/scripts/seed_data.py`)

Nine hand-authored markdown docs describe Nimbus across five **categories** that line up
with the Phase 4 support specialists:

| Category    | Docs |
| ----------- | ---- |
| `billing`   | subscriptions & invoices · refunds & duplicate charges |
| `technical` | troubleshooting · API reference & rate limits |
| `account`   | account & team management · security & SSO |
| `sales`     | pricing & plans · features overview |
| `general`   | FAQ |

Content is **hand-written, not LLM-generated**, so it's deterministic and we can assert
against it in tests (e.g. "a refund question retrieves the billing doc"). Each document is
a `KBDoc` dataclass carrying its `category` and `title`; `seed()` writes them to
`backend/data/knowledge_base/` and is idempotent (won't clobber existing files unless
`force=True`).

> **Why categories matter:** the `category` becomes vector metadata, so each specialist
> can later retrieve *only* from its own slice — a billing agent never pulls API docs.

---

## 2. Ingestion: load → split → embed → store (`backend/app/rag/ingest.py`)

```
markdown files ──load──▶ Documents ──split──▶ chunks ──embed──▶ Chroma vectors
                 (+metadata)          (overlapping)   (nomic-embed-text)
```

### Load (`load_documents`)
Reads every `*.md` file into a LangChain `Document` with metadata
`{source, category, title}`. Category/title come from the seed manifest (single source of
truth), so the data and its labels never drift apart.

### Split (`split_documents`)
`RecursiveCharacterTextSplitter` breaks each doc into **~800-char chunks with 120-char
overlap**, trying to split on markdown headings (`\n## `) first, then paragraphs, then
lines. Why split at all?
- **Precision** — a small chunk is mostly relevant signal; a whole document dilutes it.
- **Embeddings** — embedding models have a context limit; chunks stay well under it.
- **Overlap** — keeps a sentence that straddles a boundary from losing its context.

Metadata is copied onto every chunk, so a retrieved chunk still knows its `source` and
`category`.

### Embed & store (`ingest`)
Each chunk is embedded with `nomic-embed-text` (local, free) and persisted to Chroma at
`backend/data/chroma/`. `ingest(reset=True)` clears the collection first so re-running
`make ingest` rebuilds cleanly instead of accumulating duplicates. Our 9 docs produce
**14 chunks**.

---

## 3. Retrieval & grounded answering (`backend/app/rag/retriever.py`)

### `get_retriever(category=None, k=4)`
Returns a Chroma retriever that embeds the query and returns the `k` nearest chunks by
cosine similarity. Pass a `category` to add a metadata filter
(`{"category": "billing"}`) so only that domain's chunks are searched.

### `answer_question(question, category=None)`
The grounded QA path:
1. Retrieve the top-k chunks (once).
2. Format them into a context block tagged with `[source.md]` markers.
3. Prompt the **agent model** to answer **using only that context**, cite sources, and —
   crucially — say it doesn't have the information and offer a human handoff when the
   answer isn't present.

```python
from backend.app.rag.retriever import answer_question

r = answer_question("I was charged twice, can I get a refund?", category="billing")
r["answer"]    # grounded answer citing [billing-refunds.md]
r["sources"]   # the exact Documents the model saw
```

The grounding instruction lives in `GROUNDED_QA_PROMPT`. This is our **first defense
against hallucination**: in-scope questions get cited answers; out-of-scope questions
("What's the capital of France?") get a polite "I don't have that information, want a
human?" instead of a confident wrong answer. Phase 5 adds an *automated* groundedness
check that verifies the model actually obeyed this.

---

## 4. Run it yourself

```bash
make ingest      # seed + build the vector store, prints a sample retrieval
make test        # unit tests always run; retrieval tests run if Ollama is up
```

`make ingest` output ends with a sample retrieval for *"I was double charged"* — all three
hits should be `billing` chunks, confirming semantic search works.

### Files added this phase
```
backend/scripts/seed_data.py      # synthetic Nimbus knowledge base (9 docs)
backend/app/rag/vectorstore.py    # Chroma access (one configured place)
backend/app/rag/ingest.py         # load → split → embed → store
backend/app/rag/retriever.py      # retriever + grounded QA chain
backend/scripts/ingest.py         # `make ingest` CLI
backend/tests/test_rag.py         # unit + skippable retrieval tests
```

---

## 5. Concepts to take away

- **Chunking is a quality knob.** Too big = noisy retrieval; too small = lost context.
  Overlap bridges boundaries.
- **Metadata turns one store into many.** A single `category` field lets specialists
  scope retrieval without separate databases.
- **Grounding is a prompt contract first.** "Answer only from context, else defer" is the
  cheapest, most important guardrail in a support agent — enforced for real in Phase 5.
- **Local embeddings are enough.** `nomic-embed-text` gives strong retrieval at zero cost
  and never sends your knowledge base to a third party.

**Next:** [`docs/03-langgraph-agents.md`](./03-langgraph-agents.md) — wrap this retriever
and some mock tools in a stateful **LangGraph** ReAct agent with conversation memory.
