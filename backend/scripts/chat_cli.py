"""Interactive terminal chat with the guarded support system — run via ``make chat``.

Exercises the whole Phase 5 pipeline:
  * **Input guardrails** — prompt-injection attempts are refused; high-risk PII (card/SSN)
    is redacted before any model sees it.
  * **Routing** — a supervisor sends each message to one of four specialists.
  * **Output guardrails** — answers are groundedness-checked; ungrounded ones retry then
    escalate.
  * **Human-in-the-loop** — low-confidence or ungrounded turns pause on ``interrupt()``;
    this CLI prompts a "human agent" and resumes the graph with their reply.
  * **Memory** — one ``thread_id`` per session ties it all together.

Commands inside the loop:  /new  (start a fresh thread)   ·   /exit  (quit)
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command

from backend.app.core.settings import settings
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_checkpointer

# Specialist subgraphs stream answer tokens from an inner node named "agent". The
# refuse/escalate nodes emit pre-built messages (no LLM call), printed via the fallback.
_ANSWER_NODES = {"agent"}


def _stream_answer(graph, payload, config) -> bool:
    """Stream a run, printing assistant answer tokens. Returns whether any were printed."""
    streamed = False
    for _ns, (chunk, meta) in graph.stream(
        payload, config=config, stream_mode="messages", subgraphs=True
    ):
        if meta.get("langgraph_node") in _ANSWER_NODES and isinstance(chunk, AIMessageChunk):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                streamed = True
    return streamed


def _pending_interrupt(snapshot):
    """Return the payload of a pending ``interrupt()``, or ``None`` if not paused."""
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def main() -> None:
    graph = build_support_graph(checkpointer=get_checkpointer())
    thread_id = f"cli-{uuid.uuid4().hex[:8]}"

    print("Archon support — type your message. (/new = new chat, /exit = quit)\n")
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
            print(f"[started new conversation: {thread_id}]\n")
            continue

        config = {"configurable": {"thread_id": thread_id}}
        print("bot ▸ ", end="", flush=True)
        streamed = _stream_answer(graph, {"messages": [HumanMessage(content=user)]}, config)

        # Human-in-the-loop: while the graph is paused on an interrupt, bring in a human.
        snapshot = graph.get_state(config)
        while (payload := _pending_interrupt(snapshot)) is not None:
            print("\n\n[⚠ escalated to a human agent]")
            print(f"    reason: {payload.get('reason')}")
            agent = input("human agent ▸ ").strip()
            if not agent:
                agent = "A human agent will follow up with you shortly."
            print("bot ▸ ", end="", flush=True)
            streamed = _stream_answer(graph, Command(resume=agent), config)
            snapshot = graph.get_state(config)

        # refuse/escalate deliver a pre-built message that doesn't stream as tokens.
        values = snapshot.values
        if not streamed and values.get("messages"):
            print(values["messages"][-1].content, end="", flush=True)

        # Footer: show how the turn was handled.
        if values.get("blocked"):
            print("\n   ↳ refused by input guardrail "
                  f"({values.get('block_reason')})")
        elif values.get("escalation_reason"):
            print(f"\n   ↳ escalated ({values['escalation_reason']})")
        elif values.get("intent") is not None:
            conf = values.get("confidence", 0.0)
            label = "escalate" if conf < settings.router_confidence_threshold else values["intent"]
            print(f"\n   ↳ routed to {label} (intent {values['intent']}, confidence {conf:.2f})")
        print()


if __name__ == "__main__":
    main()
