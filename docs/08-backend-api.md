# Phase 8 — FastAPI Backend

> **Goal:** put the whole graph behind HTTP so a browser (or anything) can talk to it.
> Answers **stream** token-by-token over Server-Sent Events, conversations persist by
> `thread_id`, the human-in-the-loop **pause/resume** works across requests, and the chat
> endpoints are **rate-limited**.

---

## 1. One app, one graph, async memory

The compiled graph is built **once** in the FastAPI *lifespan* and stored on
`app.state.graph`, so every request shares the same in-process pipeline and the same
durable conversation store:

```python
@asynccontextmanager
async def lifespan(app):
    configure_tracing()
    async with get_async_checkpointer(path) as saver:   # aiosqlite-backed
        app.state.graph = build_support_graph(checkpointer=saver)
        yield
```

The key change from earlier phases: the API runs on an event loop, so it uses the
**`AsyncSqliteSaver`** (`get_async_checkpointer`) instead of the blocking sync saver, and
drives the graph with `astream` / `aget_state`. The graph *nodes* are still ordinary sync
functions — LangGraph runs them in a worker thread — so nothing else had to change.

`create_app(checkpoint_path=...)` is a factory (tests pass `":memory:"`); `make run`
serves `backend.app.main:app` on `:8000`, with interactive docs at `/docs`.

---

## 2. Streaming with Server-Sent Events

`POST /chat` returns an **SSE** stream. One turn emits a small, typed event sequence:

```
session  →  token  token  token …  →  done
                                   └→ interrupt        (if it escalates)
                                   (or a single error event)
```

| Event | Payload | Meaning |
| ----- | ------- | ------- |
| `session` | `thread_id` | sent first, so the client learns its conversation id |
| `token` | `content` | an answer delta (model reasoning filtered out live) |
| `interrupt` | `reason`, `customer_message` | the graph paused for a human — call `/resume` |
| `done` | `intent`, `blocked`, `escalated`, `run_id` | turn finished; metadata for UI + feedback |
| `error` | `detail` | something failed mid-stream (we don't 500 a half-sent stream) |

The streaming loop reuses the Phase 7 reasoning filter (`visible_so_far`) so `<think>`
tokens never reach the client, and captures the LangSmith **`run_id`** via `collect_runs`
so the UI can attach feedback later. Pre-built replies (the refusal, a resolved
escalation) don't stream as tokens, so the handler emits them as a single `token` event
before `done`.

The event shapes are declared as Pydantic models in `api/schemas.py` — they *are* the wire
contract the Phase 9 frontend consumes.

---

## 3. Human-in-the-loop across HTTP requests

This is where the checkpointer earns its keep. When the supervisor is unsure (or an answer
can't be grounded), the graph hits `interrupt()` and the `/chat` stream ends with an
`interrupt` event instead of `done`. The conversation is durably saved, so a **separate**
HTTP request finishes it:

```
POST /chat   {"message": "hello", "thread_id": "t1"}
  → session · interrupt(reason="low_confidence_routing")

POST /resume {"thread_id": "t1", "message": "Hi, this is Dana from support!"}
  → session · token("Hi, this is Dana…") · done(escalated=true)
```

`/resume` first checks the thread is actually paused (`aget_state` → pending interrupt),
returning **409** if not, then resumes the graph with `Command(resume=<agent reply>)`. The
human's text is delivered to the customer as the assistant turn.

---

## 4. Guardrails at the edge, too

The in-graph guardrails (Phases 5) still run, and the HTTP layer adds edge protections:

- **Input validation** — `message` is length-bounded (`1..api_max_message_chars`); bad
  bodies get a `422` before any work happens.
- **Rate limiting** — `slowapi` caps `/chat` and `/resume` at `settings.api_rate_limit`
  (default `30/minute`) per client IP, returning `429` when exceeded.
- **CORS** — opened only to the configured origins (the Next.js dev server by default).
- **Health** — `GET /health` reports liveness + whether Ollama and tracing are up, without
  failing if Ollama is down.

`POST /feedback` records a thumbs-up/down against a run's `run_id` in LangSmith (a no-op
when tracing is off), closing the loop opened in Phase 6.

---

## 5. Run it yourself

```bash
make run     # uvicorn on http://localhost:8000  (docs at /docs)
```

```bash
# health
curl -s localhost:8000/health
# stream an answer (SSE)
curl -N -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is your refund policy for monthly plans?"}'
```

`make test` covers the API via FastAPI's `TestClient`: the injection-refuse path exercises
the **entire SSE pipeline with no model**, plus validation, the `/resume` 409, rate
limiting, and a live streamed answer.

### Files added/changed this phase
```
backend/app/main.py              # app factory: lifespan, CORS, rate limiter, router
backend/app/api/routes.py        # /chat, /resume (SSE) · /health · /feedback
backend/app/api/schemas.py       # request models + typed SSE event payloads
backend/app/api/limiter.py       # shared slowapi limiter
backend/app/graph/memory.py      # + get_async_checkpointer (AsyncSqliteSaver)   [updated]
backend/app/core/settings.py     # + CORS origins / rate limit / max message     [updated]
backend/tests/test_api.py        # TestClient: SSE, validation, 409, 429, live stream
```

---

## 6. Concepts to take away

- **Stream with SSE, structure your events.** A tiny typed protocol
  (`session/token/interrupt/done/error`) is far easier for a UI than a raw token firehose.
- **Async API ⇒ async checkpointer.** Swap `SqliteSaver` for `AsyncSqliteSaver`; sync graph
  nodes keep working unchanged.
- **Pause/resume is just two requests.** Because state lives in the checkpointer, an
  `interrupt` on one request and a `Command(resume=…)` on the next complete one
  conversation — even though HTTP is stateless.
- **Defend the edge as well as the graph.** Validation, rate limiting, and CORS sit in
  front of the in-graph guardrails.

**Next:** [`docs/09-frontend.md`](./09-frontend.md) — a polished **Next.js** chat UI that
consumes this SSE protocol, shows routing/guardrail state, and drives the human-in-the-loop
resume from the browser.
