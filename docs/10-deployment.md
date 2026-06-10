# Phase 10 — Hardening & Deployment

> **Goal:** take the working system from "runs on my machine" to "safe to run for real" —
> request timeouts, structured logging, a dependency audit, clean tests, and honest notes on
> what is and isn't production-ready.

---

## 1. What hardening added

| Area | Change |
| ---- | ------ |
| **Resilience** | Every model call carries a `request_timeout` (`client_kwargs`), so a hung Ollama surfaces as an error instead of wedging a request forever. |
| **Observability** | A small structured logger (`core/logging.py`) on stdout, an HTTP access-log middleware (`method / path / status / dur_ms`), and quieted third-party loggers. |
| **Error handling** | A catch-all exception handler returns clean JSON `500`s and logs the traceback; streaming errors are still delivered as in-stream `error` events. |
| **Dependencies** | Frontend bumped to **Next.js 15** + a `postcss` override → `npm audit` is **0 vulnerabilities**. The TestClient deprecation warning is suppressed. |
| **Config** | New env knobs documented in `.env.example`: timeouts, log level, CORS, rate limit, max message length. |

The full suite stays green (`make test`) and the frontend builds clean (`make ui-build`).

---

## 2. Running it for real

Three processes: Ollama, the API, the UI.

```bash
# 0. models
ollama serve &
ollama pull llama3.2:3b && ollama pull qwen3.6 && ollama pull nomic-embed-text

# 1. backend (drop --reload; add workers behind a process manager)
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2

# 2. knowledge base (once)
make ingest

# 3. frontend (static build + serve, or host on Vercel/Node)
cd frontend && npm ci && npm run build && npm run start
```

Point the UI at the API with `NEXT_PUBLIC_API_BASE`, and allow the UI origin from the API
with `ARCHON_API_CORS_ORIGINS`. Put both behind a TLS-terminating reverse proxy (nginx,
Caddy) in any real deployment.

### A note on workers and memory

Conversation state lives in a **SQLite** checkpointer on local disk. That is perfect for a
single host, but it does **not** share across machines. For multi-node scaling, swap the
checkpointer for a Postgres-backed one (`langgraph-checkpoint-postgres`) — the graph code
doesn't change, only `get_async_checkpointer`.

---

## 3. Operational surface

- **Health:** `GET /health` reports liveness + whether Ollama and tracing are reachable —
  wire it to your orchestrator's readiness probe.
- **Rate limiting:** `ARCHON_API_RATE_LIMIT` (per IP) guards the streaming endpoints; behind
  a proxy, ensure the real client IP is forwarded.
- **Timeouts:** `ARCHON_REQUEST_TIMEOUT` bounds model calls; tune to your hardware.
- **Logs:** structured stdout lines (`ARCHON_LOG_LEVEL`) — ship them to your aggregator.
- **Tracing:** set a real `LANGCHAIN_API_KEY` to get full LangSmith traces + feedback;
  leave it unset for a fully offline, zero-telemetry run.

---

## 4. Security posture — honest limits

What the system **does** defend:

- Prompt-injection / jailbreak refusal and high-risk PII redaction **before** the model.
- Output groundedness checks, PII-leak rescan, and scope enforcement **after** the model.
- Input validation, rate limiting, and CORS at the HTTP edge.

What it deliberately **does not** include (out of scope for a portfolio demo):

- **AuthN/AuthZ** — there is no user authentication; add your own (API keys / OAuth) before
  exposing it. The mock account tools return canned data and must not be wired to real PII.
- **Secrets management** — keys come from `.env`; use a real secret store in production.
- **Abuse/cost controls** beyond basic rate limiting.

The guardrails are a strong *first* line, not a guarantee — pair them with monitoring
(LangSmith traces + feedback) and human review for anything high-stakes.

---

## 5. Known limitations

- **Local model quality.** `llama3.2:3b` and `qwen3.6` are small; routing is ~88% on the
  eval set and answers occasionally miss nuance. The architecture is model-agnostic — point
  the factory at larger Ollama models (or a hosted provider) for better quality at higher
  cost. Evals (`make eval`) make the trade-off measurable.
- **Synthetic knowledge base.** The "Nimbus" docs are hand-authored fixtures; swap in real
  content via `backend/data/knowledge_base/` and re-run `make ingest`.
- **Single-host state.** SQLite checkpointer (see §2).

---

## 6. Concepts to take away

- **Hardening is unglamorous and essential:** timeouts, logging, error shaping, and a clean
  dependency audit are what separate a demo from something you can leave running.
- **Make the limits explicit.** A credible "production-grade" claim names what it does *not*
  cover (auth, multi-node state) as clearly as what it does.
- **Keep the swap points obvious.** Model tier, checkpointer backend, and knowledge base are
  each a single seam — the rest of the system doesn't care.

This is the final phase. The full journey — local LLMs → RAG → a supervised, guarded,
observable, evaluated multi-agent system behind a streaming API and a browser UI — lives
across [`docs/00`](./00-setup.md)–`10`.
