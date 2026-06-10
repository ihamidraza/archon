# Archon — Automated Customer Support & Intelligent Routing Agent

A **production-grade, fully-local, zero-cost** customer-support agent built using
**LangChain, LangGraph, and LangSmith**.

An LLM **supervisor** classifies each incoming message and routes it to a **specialist
sub-agent** (Billing · Technical · Account · Sales). Specialists answer from a **RAG
knowledge base**, every turn passes through **input/output guardrails**, and low-confidence
or risky cases **escalate to a human**. All models run locally via **Ollama** — no paid APIs.

> **Status:** Phase 5 (guardrails + human-in-the-loop) complete. See [`PLAN.md`](./PLAN.md) for the full roadmap.

## Stack (all free / open-source)

| Concern       | Choice                                                    |
| ------------- | --------------------------------------------------------- |
| LLMs / embeds | **Ollama** — `llama3.2:3b`, `qwen3.6`, `nomic-embed-text` |
| Orchestration | **LangGraph** (`StateGraph`, supervisor pattern)          |
| LLM toolkit   | **LangChain**                                             |
| Observability | **LangSmith**                                             |
| Vector store  | **Chroma** (local, persistent)                            |
| Memory        | LangGraph **SqliteSaver** checkpointer                    |
| PII guardrail | **Microsoft Presidio**                                    |
| API           | **FastAPI** + SSE streaming                               |
| UI            | **Next.js** chat (built last)                             |
| Env / tasks   | **uv** (Python 3.12) + **Make**                           |

## Quickstart

```bash
# 0. Prereqs: ollama running, plus models pulled
ollama serve &
ollama pull llama3.2:3b && ollama pull qwen3.6 && ollama pull nomic-embed-text

# 1. Build the Python 3.12 env + install deps
make setup

# 2. Configure (LangSmith key optional but recommended)
cp .env.example .env        # then edit LANGCHAIN_API_KEY

# 3. Verify everything is wired up
make env-check
```

Run `make help` to see all tasks (`ingest`, `chat`, `run`, `test`, `eval`, `lint`, `fmt`).

## Layout

```
backend/app/      core (settings) · llm · rag · graph · guardrails · tools · api
backend/data/     knowledge_base/ (synthetic docs) · chroma/ (vectors)
backend/scripts/  env_check · ingest · chat_cli · seed_data
backend/evals/    LangSmith datasets + evaluators
docs/             one learning doc per phase (00–10)
frontend/         Next.js chat UI
```

## Documentation

Each build phase ships a standalone explainer in [`docs/`](./docs). Start with
[`docs/00-setup.md`](./docs/00-setup.md).
