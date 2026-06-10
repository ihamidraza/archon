"""Interactive terminal chat with the guarded support system — run via ``make chat``.

Exercises the whole pipeline built so far:
  * **Input guardrails** — injection attempts refused; high-risk PII redacted.
  * **Routing** — a supervisor sends each message to one of four specialists.
  * **Output guardrails** — answers are groundedness-checked; ungrounded ones retry/escalate.
  * **Human-in-the-loop** — low-confidence/ungrounded turns pause on ``interrupt()``.
  * **Memory** — one ``thread_id`` per session ties it together.
  * **Observability (Phase 6)** — every turn is traced to LangSmith (when a key is set)
    with ``archon`` tags + metadata, and you can attach feedback with ``/good`` / ``/bad``.

Commands:  /new (fresh thread) · /good · /bad [note] (feedback on last turn) · /exit
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.tracers.context import collect_runs
from langgraph.types import Command

from backend.app.core.observability import (
    configure_tracing,
    log_feedback,
    run_config,
    run_url,
)
from backend.app.core.settings import settings
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_checkpointer
from backend.app.llm.text import strip_reasoning, visible_so_far

# Specialist subgraphs stream answer tokens from an inner node named "agent". The
# refuse/escalate nodes emit pre-built messages (no LLM call), printed via the fallback.
_ANSWER_NODES = {"agent"}


def _stream_answer(graph, payload, config) -> tuple[bool, str | None]:
    """Stream a run, printing answer tokens (reasoning filtered). Returns (printed_any, run_id)."""
    streamed = False
    accumulated = ""  # full raw text of the current answer, to filter <think> live
    shown = 0  # how many visible chars we've already printed
    with collect_runs() as cb:
        for _ns, (chunk, meta) in graph.stream(
            payload, config=config, stream_mode="messages", subgraphs=True
        ):
            if meta.get("langgraph_node") in _ANSWER_NODES and isinstance(chunk, AIMessageChunk):
                if chunk.content:
                    accumulated += chunk.content
                    visible = visible_so_far(accumulated)
                    if len(visible) > shown:
                        print(visible[shown:], end="", flush=True)
                        shown = len(visible)
                        streamed = True
    run_id = str(cb.traced_runs[0].id) if cb.traced_runs else None
    return streamed, run_id


def _pending_interrupt(snapshot):
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def main() -> None:
    traced = configure_tracing()
    graph = build_support_graph(checkpointer=get_checkpointer())
    thread_id = f"cli-{uuid.uuid4().hex[:8]}"
    last_run_id: str | None = None

    status = f"tracing → LangSmith project '{settings.langchain_project}'" if traced else (
        "tracing off (set LANGCHAIN_API_KEY to enable LangSmith)"
    )
    print(f"Archon support [{status}]")
    print("commands: /new · /good · /bad [note] · /exit\n")

    while True:
        try:
            user = input("you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user == "/exit":
            break
        if user == "/new":
            thread_id = f"cli-{uuid.uuid4().hex[:8]}"
            last_run_id = None
            print(f"[started new conversation: {thread_id}]\n")
            continue
        if user.startswith("/good") or user.startswith("/bad"):
            _handle_feedback(user, last_run_id, traced)
            continue

        config = run_config(
            thread_id,
            tags=["cli"],
            metadata={"channel": "cli"},
            run_name="archon_support_turn",
        )
        print("bot ▸ ", end="", flush=True)
        streamed, last_run_id = _stream_answer(
            graph, {"messages": [HumanMessage(content=user)]}, config
        )

        snapshot = graph.get_state(config)
        while (payload := _pending_interrupt(snapshot)) is not None:
            print("\n\n[⚠ escalated to a human agent]")
            print(f"    reason: {payload.get('reason')}")
            agent = input("human agent ▸ ").strip() or "A human agent will follow up shortly."
            print("bot ▸ ", end="", flush=True)
            streamed, last_run_id = _stream_answer(graph, Command(resume=agent), config)
            snapshot = graph.get_state(config)

        values = snapshot.values
        if not streamed and values.get("messages"):
            print(strip_reasoning(str(values["messages"][-1].content)), end="", flush=True)

        _print_footer(values)
        print()


def _handle_feedback(command: str, run_id: str | None, traced: bool) -> None:
    """Record /good or /bad feedback on the most recent turn."""
    if not traced:
        print("[feedback ignored — tracing is off]\n")
        return
    if run_id is None:
        print("[no turn to rate yet]\n")
        return
    parts = command.split(maxsplit=1)
    score = 1.0 if parts[0] == "/good" else 0.0
    comment = parts[1] if len(parts) > 1 else None
    ok = log_feedback(run_id, key="user_score", score=score, comment=comment)
    url = run_url(run_id)
    print(f"[feedback {'recorded' if ok else 'failed'}{f' → {url}' if url else ''}]\n")


def _print_footer(values: dict) -> None:
    """Show how the turn was handled (route / refusal / escalation)."""
    if values.get("blocked"):
        print(f"\n   ↳ refused by input guardrail ({values.get('block_reason')})")
    elif values.get("escalation_reason"):
        print(f"\n   ↳ escalated ({values['escalation_reason']})")
    elif values.get("intent") is not None:
        conf = values.get("confidence", 0.0)
        label = "escalate" if conf < settings.router_confidence_threshold else values["intent"]
        print(f"\n   ↳ routed to {label} (intent {values['intent']}, confidence {conf:.2f})")


if __name__ == "__main__":
    main()
