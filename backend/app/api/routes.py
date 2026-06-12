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
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.tracers.context import collect_runs
from langgraph.types import Command
from sse_starlette import EventSourceResponse, ServerSentEvent

from backend.app.api.escalation_registry import normalize_department, registry
from backend.app.api.limiter import CHAT_RATE_LIMIT, limiter
from backend.app.api.pubsub import pubsub
from backend.app.api.schemas import (
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    HumanReplyEvent,
    InterruptEvent,
    QueueItem,
    QueueResponse,
    ResumeRequest,
    SessionEvent,
    ThreadDetailResponse,
    TokenEvent,
    TranscriptMessage,
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


async def _event_stream(
    graph, payload, config, thread_id: str, *, publish: bool = False
) -> AsyncIterator[ServerSentEvent]:
    """Drive one graph turn and yield SSE events (session → token* → done/interrupt).

    When ``publish`` is set, every event is *also* fanned out via :data:`pubsub` to anyone
    subscribed to this thread's live stream. ``/resume`` uses this so a human agent's reply
    reaches the waiting customer's browser as well as the agent's own response.
    """

    async def emit(event) -> ServerSentEvent:
        if publish:
            await pubsub.publish(thread_id, event)
        return _sse(event)

    yield await emit(SessionEvent(thread_id=thread_id))

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
                            yield await emit(TokenEvent(content=visible[shown:]))
                            shown = len(visible)
            if cb.traced_runs:
                run_id = str(cb.traced_runs[0].id)

        state = await graph.aget_state(config)
        values = state.values

        pending = _pending_interrupt(state)
        if pending is not None:
            # Index the paused thread so the right department's console can pick it up.
            registry.add(
                thread_id=thread_id,
                department=normalize_department(values.get("intent")),
                customer_message=str(pending.get("customer_message", "")),
                reason=str(pending.get("reason", "")),
            )
            yield await emit(
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
                yield await emit(TokenEvent(content=text))

        # Ran to completion with no pending interrupt: the thread is resolved.
        registry.remove(thread_id)
        yield await emit(
            DoneEvent(
                thread_id=thread_id,
                intent=values.get("intent"),
                blocked=bool(values.get("blocked")),
                escalated=bool(values.get("escalation_reason")),
                run_id=run_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface as a stream error, don't 500 mid-stream
        yield await emit(ErrorEvent(detail=str(exc)))


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
    """Resume a thread paused for escalation with a human agent's reply (SSE).

    This is the agent console's send path. The reply streams back to the agent (the caller)
    and, via ``publish=True``, is fanned out to the customer's live ``/threads/{id}/stream``
    subscription so it lands in their chat too.
    """
    graph = request.app.state.graph
    config = run_config(payload.thread_id, tags=["api", "resume"], metadata={"channel": "api"})

    state = await graph.aget_state(config)
    if _pending_interrupt(state) is None:
        raise HTTPException(status_code=409, detail="Thread is not awaiting a human reply.")

    # Tell the customer's live stream to open a fresh human-agent bubble before tokens land.
    await pubsub.publish(payload.thread_id, HumanReplyEvent(thread_id=payload.thread_id))

    stream = _event_stream(
        graph, Command(resume=payload.message), config, payload.thread_id, publish=True
    )
    return EventSourceResponse(stream)


@router.post("/threads/{thread_id}/stream")
async def thread_stream(thread_id: str) -> EventSourceResponse:
    """Customer live stream: subscribe to a thread and receive a human agent's reply in real
    time after escalation. Opened by the customer's browser when ``/chat`` ends on an
    interrupt; closes once a terminal ``done`` event arrives.
    """

    async def subscription() -> AsyncIterator[ServerSentEvent]:
        async with pubsub.subscribe(thread_id) as queue:
            # Confirm attachment immediately so the client knows it's listening.
            yield _sse(SessionEvent(thread_id=thread_id))
            while True:
                event = await queue.get()
                yield _sse(event)
                if isinstance(event, DoneEvent):
                    break

    # sse-starlette pings idle connections (default 15s) to keep proxies from dropping them.
    return EventSourceResponse(subscription())


@router.get("/agent/queue", response_model=QueueResponse)
async def agent_queue(request: Request, department: str | None = None) -> QueueResponse:
    """List escalated conversations for a department's console (``general`` items included).

    Self-healing: each entry is verified against the live graph state, and any thread that is
    no longer paused (already resolved) is dropped from the registry.
    """
    graph = request.app.state.graph
    items: list[QueueItem] = []
    for entry in registry.list_for(department):
        state = await graph.aget_state(run_config(entry.thread_id))
        if _pending_interrupt(state) is None:
            registry.remove(entry.thread_id)
            continue
        items.append(
            QueueItem(
                thread_id=entry.thread_id,
                department=entry.department,
                customer_message=entry.customer_message,
                reason=entry.reason,
                created_at=entry.created_at,
                status=entry.status,
            )
        )
    return QueueResponse(department=department, items=items)


def _transcript(messages: list[BaseMessage]) -> list[TranscriptMessage]:
    """Flatten the graph's message history for display: human → user, AI → assistant.

    Tool/system messages and empty content are skipped. Prior human-agent replies are stored
    as plain ``AIMessage`` in state and so render as ``assistant`` here — adequate context.
    """
    out: list[TranscriptMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            content = str(message.content)
            role: str = "user"
        elif isinstance(message, AIMessage):
            content = strip_reasoning(str(message.content))
            role = "assistant"
        else:
            continue
        if content.strip():
            out.append(TranscriptMessage(role=role, content=content))
    return out


@router.get("/agent/threads/{thread_id}", response_model=ThreadDetailResponse)
async def agent_thread(request: Request, thread_id: str) -> ThreadDetailResponse:
    """Full transcript + escalation context for one thread, for the agent console."""
    graph = request.app.state.graph
    state = await graph.aget_state(run_config(thread_id))
    values = state.values
    messages = values.get("messages") or []
    if not messages:
        raise HTTPException(status_code=404, detail="Unknown thread.")

    pending = _pending_interrupt(state)
    intent = values.get("intent")
    return ThreadDetailResponse(
        thread_id=thread_id,
        department=normalize_department(intent),
        intent=intent,
        escalation_reason=values.get("escalation_reason"),
        reason=str(pending.get("reason", "")) if pending else "",
        customer_message=str(pending.get("customer_message", "")) if pending else "",
        pending=pending is not None,
        messages=_transcript(messages),
    )


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
