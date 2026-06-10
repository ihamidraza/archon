# Archon — Automated Customer Support & Intelligent Routing Agent

A **production-grade, fully-local, zero-cost** customer-support agent built using
**LangChain, LangGraph, and LangSmith**.

An LLM **supervisor** classifies each incoming message and routes it to a **specialist
sub-agent** (Billing · Technical · Account · Sales). Specialists answer from a **RAG
knowledge base**, every turn passes through **input/output guardrails**, and low-confidence
or risky cases **escalate to a human**. All models run locally via **Ollama** — no paid APIs.

> **Status:** Complete — all 10 build phases shipped (AI core → guardrails → observability →
> evaluation → API → UI → hardening). Each phase has a standalone explainer in [`docs/`](./docs).

## Architecture

```
                        ┌──────────────── one LangGraph StateGraph ────────────────┐
  customer message ─▶   │  input guard ─▶ supervisor ─▶ specialist ─▶ output guard │ ─▶ streamed answer
       (HTTP / SSE)     │   │  PII redact    │ classify    │ ReAct loop   │ grounded?│
                        │   │  injection?    │ + route     │ RAG + tools  │          │
                        │   ▼                ▼             │              ▼          │
                        │ refuse        (low confidence)   │      ungrounded → retry │
                        │                     └────────────┴──────▶ escalate ◀───────┘
                        │                          human-in-the-loop (interrupt / resume)
                        └──────────────────────────────────────────────────────────┘
   every turn is traced to LangSmith · memory persists per thread via a SQLite checkpointer
```

Four specialists (Billing · Technical · Account · Sales), each a ReAct subgraph scoped to
its slice of the knowledge base. See [`docs/`](./docs) for a phase-by-phase walkthrough.

## Stack (all free / open-source)

| Concern       | Choice                                                    |
| ------------- | --------------------------------------------------------- |
| LLMs / embeds | **Ollama** — `llama3.2:3b`, `qwen3.6`, `nomic-embed-text` |
| Orchestration | **LangGraph** (`StateGraph`, supervisor pattern)          |
| LLM toolkit   | **LangChain**                                             |
| Observability | **LangSmith**                                             |
| Vector store  | **Chroma** (local, persistent)                            |
| Memory        | LangGraph **SqliteSaver** checkpointer                    |
| PII guardrail | regex engine (+ optional **Microsoft Presidio**)          |
| API           | **FastAPI** + SSE streaming + rate limiting               |
| UI            | **Next.js 15** chat (Tailwind, SSE)                       |
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

### HTTP API

```bash
make run    # FastAPI on http://localhost:8000  (interactive docs at /docs)

# stream an answer over Server-Sent Events
curl -N -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is your refund policy for monthly plans?"}'
```

Endpoints: `POST /chat` & `POST /resume` (SSE streaming + human-in-the-loop), `GET /health`,
`POST /feedback`. See [`docs/08-backend-api.md`](./docs/08-backend-api.md).

### Web UI

```bash
make ui-install   # one-time: install frontend deps
make ui           # Next.js chat UI on http://localhost:3000  (needs the backend running)
```

A polished Next.js chat UI consuming the SSE protocol — streaming answers, routing/guardrail
badges, thumbs feedback, and the human-in-the-loop handoff. See
[`frontend/`](./frontend) and [`docs/09-frontend.md`](./docs/09-frontend.md).

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

Each build phase ships a standalone explainer in [`docs/`](./docs):

| # | Doc | Topic |
| - | --- | ----- |
| 00 | [setup](./docs/00-setup.md) | uv env, Ollama, toolchain |
| 01 | [langchain-basics](./docs/01-langchain-basics.md) | model factory, prompts, structured output |
| 02 | [rag-pipeline](./docs/02-rag-pipeline.md) | synthetic KB → Chroma, grounded QA |
| 03 | [langgraph-agents](./docs/03-langgraph-agents.md) | hand-built ReAct loop + memory |
| 04 | [supervisor-routing](./docs/04-supervisor-routing.md) | classifier + specialist subgraphs |
| 05 | [guardrails](./docs/05-guardrails.md) | PII, injection, groundedness, human-in-the-loop |
| 06 | [langsmith-observability](./docs/06-langsmith-observability.md) | tracing, tags, feedback |
| 07 | [evaluation](./docs/07-evaluation.md) | datasets + evaluators (local & hosted) |
| 08 | [backend-api](./docs/08-backend-api.md) | FastAPI, SSE, pause/resume |
| 09 | [frontend](./docs/09-frontend.md) | Next.js chat UI |
| 10 | [deployment](./docs/10-deployment.md) | hardening + running it for real |
