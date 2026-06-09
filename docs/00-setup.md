# Phase 0 — Project Setup

> **Goal:** a reproducible, fully-local, zero-cost foundation we can build every later
> phase on. By the end of this phase, `make env-check` confirms the toolchain is ready.

---

## 1. Why these choices

### `uv` + pinned Python 3.12 (not system 3.14)
The machine ships Python **3.14**, which is too new — many ML/LangChain dependencies
(spaCy/Presidio, tokenizers, chromadb) don't yet publish 3.14 wheels, so installs fail
while compiling from source. [`uv`](https://docs.astral.sh/uv/) solves this cleanly:

- It downloads and pins an **isolated Python 3.12** (`.python-version`) without touching
  the system interpreter.
- It resolves and installs dependencies an order of magnitude faster than pip, into a
  project-local `.venv/`.
- `uv run <cmd>` executes inside that env — no manual `activate` needed.

### Tiered local models (cost/latency routing)
We never call a paid API. Instead we use **Ollama** with three roles:

| Role     | Model              | Why |
| -------- | ------------------ | --- |
| `router` | `llama3.2:3b`      | Tiny + fast; classification & guardrail checks happen on every turn, so speed matters. Supports structured/tool output. |
| `agent`  | `qwen3.6:latest`   | Stronger reasoning + reliable tool-calling for the specialist agents that actually answer. |
| `embed`  | `nomic-embed-text` | Small, high-quality local embeddings for RAG. |

This mirrors a real production pattern: spend cheap/fast compute on the hot path
(routing, guards) and reserve the heavyweight model for the actual answer.

### Everything else local
- **Chroma** — embedded vector store, persists to `backend/data/chroma/`.
- **SqliteSaver** — LangGraph checkpointer for conversation memory + human-in-the-loop.
- **LangSmith** — the one cloud dependency, but its **free Developer tier** (5k traces/mo,
  one seat) is enough for learning and costs nothing.

---

## 2. What this phase created

```
pyproject.toml        # deps + tool config (ruff, pytest), python pinned >=3.12,<3.13
.python-version       # tells uv to use 3.12
.env.example          # all tunables; copy to .env
.gitignore            # excludes .venv, .env, local data, checkpoints
Makefile              # task runner (make help)
README.md             # project overview + quickstart
backend/app/core/settings.py   # typed config singleton (pydantic-settings)
backend/scripts/env_check.py   # this phase's verification script
docs/00-setup.md      # you are here
```

### `settings.py` — the config singleton
Every module imports one place for configuration:

```python
from backend.app.core.settings import settings
settings.agent_model            # "qwen3.6:latest"
settings.chroma_path            # absolute Path, resolved from repo root
```

It reads environment variables (and `.env`) with typed fields and sensible local-first
defaults, so the system runs even **before** you create a `.env`. Relative paths in the
env (e.g. `backend/data/chroma`) are resolved to absolute paths against the repo root via
the `*_path` properties — so scripts work regardless of the current working directory.

---

## 3. Setup steps

```bash
# Install the toolchain (uv installs Python 3.12 + all deps into .venv/)
make setup

# Configure secrets/tunables
cp .env.example .env
#   → set LANGCHAIN_API_KEY from https://smith.langchain.com (Settings → API Keys)
#   → LANGCHAIN_TRACING_V2=true to send traces (optional for Phase 0)

# Pull the embedding model if you haven't already
ollama pull nomic-embed-text
```

> **Getting the LangSmith key (free):** sign up at <https://smith.langchain.com>, open
> **Settings → API Keys → Create API Key**, paste it into `.env`. The free Developer plan
> needs no credit card. Tracing isn't required until Phase 6, so you can defer this.

---

## 4. Verify

```bash
make env-check
```

Expected output:

```
✅ Settings loaded
✅ Ollama reachable — 4 model(s) installed
✅ router model present: llama3.2:3b
✅ agent  model present: qwen3.6:latest
✅ embed  model present: nomic-embed-text
✅ Environment ready.
```

`env_check.py` (`backend/scripts/env_check.py`) calls Ollama's `/api/tags` endpoint to
confirm the server is up and each tiered model is installed, matching by name prefix so a
`:latest` tag still resolves. If a model is missing it prints the exact `ollama pull`
command to fix it.

---

## 5. Concepts to take away

- **Reproducible envs matter for agents.** LLM stacks have heavy, version-sensitive deps;
  pinning the interpreter + lockfile (`uv.lock`) prevents "works on my machine" drift.
- **Config as a typed singleton** keeps model names, thresholds, and paths out of the code
  and in one auditable place — essential when you later tune guardrail thresholds.
- **Tiered models** are the first cost/performance guardrail, even with free local models:
  they keep the always-on hot path (routing, safety checks) fast.

**Next:** [`docs/01-langchain-basics.md`](./01-langchain-basics.md) — the model factory,
prompt templates, and structured output that the router and agents are built on.
