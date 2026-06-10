"""HTTP routes: streaming chat, human-in-the-loop resume, health, and feedback.

The two conversational endpoints return **Server-Sent Events**. A turn emits, in order:

    session  → token* → (done | interrupt)        (or a single error event)

* ``session`` first, so the client immediately knows its ``thread_id``.
* ``token`` deltas as the answer streams (with model reasoning filtered out live).
* ``done`` with routing/guardrail metadata, or ``interrupt`` when the graph paused for a
  human — in which case the client calls ``/resume`` with the agent's reply.

The compiled graph (with its async checkpointer) lives on ``app.state.graph``; it's built
once in the app lifespan, so every request shares the same memory store.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.tracers.context import collect_runs
from langgraph.types import Command
from sse_starlette import EventSourceResponse, ServerSentEvent

from backend.app.api.limiter import CHAT_RATE_LIMIT, limiter
from backend.app.api.schemas import (
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    InterruptEvent,
    ResumeRequest,
    SessionEvent,
    TokenEvent,
)
from backend.app.core.observability import log_feedback, run_config, tracing_enabled
from backend.app.core.settings import settings
from backend.app.llm.text import strip_reasoning, visible_so_far

router = APIRouter()

# Specialist subgraphs stream answer tokens from an inner node named "agent".
_ANSWER_NODES = {"agent"}


def _sse(event) -> ServerSentEvent:
    """Serialize an event model as one SSE ``data:`` line."""
    return ServerSentEvent(data=event.model_dump_json())


def _pending_interrupt(state) -> dict | None:
    """Return the payload of a pending ``interrupt()``, or ``None`` if not paused."""
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


async def _event_stream(graph, payload, config, thread_id: str) -> AsyncIterator[ServerSentEvent]:
    """Drive one graph turn and yield SSE events (session → token* → done/interrupt)."""
    yield _sse(SessionEvent(thread_id=thread_id))

    accumulated = ""  # raw answer text so far, for live <think> filtering
    shown = 0  # visible chars already emitted
    run_id: str | None = None
    try:
        with collect_runs() as cb:
            async for _ns, (chunk, meta) in graph.astream(
                payload, config=config, stream_mode="messages", subgraphs=True
            ):
                is_answer = meta.get("langgraph_node") in _ANSWER_NODES
                if is_answer and isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        accumulated += chunk.content
                        visible = visible_so_far(accumulated)
                        if len(visible) > shown:
                            yield _sse(TokenEvent(content=visible[shown:]))
                            shown = len(visible)
            if cb.traced_runs:
                run_id = str(cb.traced_runs[0].id)

        state = await graph.aget_state(config)
        values = state.values

        pending = _pending_interrupt(state)
        if pending is not None:
            yield _sse(
                InterruptEvent(
                    thread_id=thread_id,
                    reason=str(pending.get("reason", "")),
                    customer_message=str(pending.get("customer_message", "")),
                )
            )
            return

        # refuse/escalate-resolved messages are pre-built (no token stream) — emit once.
        if shown == 0 and values.get("messages"):
            text = strip_reasoning(str(values["messages"][-1].content))
            if text:
                yield _sse(TokenEvent(content=text))

        yield _sse(
            DoneEvent(
                thread_id=thread_id,
                intent=values.get("intent"),
                blocked=bool(values.get("blocked")),
                escalated=bool(values.get("escalation_reason")),
                run_id=run_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface as a stream error, don't 500 mid-stream
        yield _sse(ErrorEvent(detail=str(exc)))


@router.post("/chat")
@limiter.limit(CHAT_RATE_LIMIT)
async def chat(request: Request, payload: ChatRequest) -> EventSourceResponse:
    """Stream a support answer for a customer message (SSE)."""
    thread_id = payload.thread_id or f"web-{uuid.uuid4().hex[:12]}"
    config = run_config(
        thread_id, tags=["api"], metadata={"channel": "api"}, run_name="archon_support_turn"
    )
    graph = request.app.state.graph
    stream = _event_stream(
        graph, {"messages": [HumanMessage(content=payload.message)]}, config, thread_id
    )
    return EventSourceResponse(stream)


@router.post("/resume")
@limiter.limit(CHAT_RATE_LIMIT)
async def resume(request: Request, payload: ResumeRequest) -> EventSourceResponse:
    """Resume a thread that paused for human escalation, with the agent's reply (SSE)."""
    graph = request.app.state.graph
    config = run_config(payload.thread_id, tags=["api", "resume"], metadata={"channel": "api"})

    state = await graph.aget_state(config)
    if _pending_interrupt(state) is None:
        raise HTTPException(status_code=409, detail="Thread is not awaiting a human reply.")

    stream = _event_stream(graph, Command(resume=payload.message), config, payload.thread_id)
    return EventSourceResponse(stream)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness + dependency status (does not fail if Ollama is down)."""
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:  # noqa: BLE001
        ollama_ok = False
    return HealthResponse(ollama=ollama_ok, tracing=tracing_enabled())


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Attach feedback to a traced run (no-op when tracing is off)."""
    recorded = log_feedback(
        payload.run_id, key=payload.key, score=payload.score, comment=payload.comment
    )
    return FeedbackResponse(recorded=recorded)
