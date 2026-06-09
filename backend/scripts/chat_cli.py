"""Interactive terminal chat with the supervised support system — run via ``make chat``.

Demonstrates the whole Phase 4 flow at once:
  * **Routing** — a supervisor classifies each message and hands it to one of four
    specialists (or escalates). The chosen specialist is printed after each answer.
  * **Tool use** — the specialist searches its domain knowledge base / looks up accounts.
  * **Memory** — every turn shares one ``thread_id``, so the conversation is remembered
    across turns and specialists. Restart with the same thread to resume it.

Commands inside the loop:  /new  (start a fresh thread)   ·   /exit  (quit)
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessageChunk, HumanMessage

from backend.app.core.settings import settings
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_checkpointer

# Specialist subgraphs stream their answer tokens from an inner node named "agent";
# the escalation stub emits its message from the "escalate" node.
_ANSWER_NODES = {"agent", "escalate"}


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
        # subgraphs=True so we also receive token chunks emitted inside specialist
        # subgraphs; we print only assistant answer tokens (not the supervisor's
        # structured-output call or tool plumbing).
        streamed_any = False
        for _ns, (chunk, meta) in graph.stream(
            {"messages": [HumanMessage(content=user)]},
            config=config,
            stream_mode="messages",
            subgraphs=True,
        ):
            if meta.get("langgraph_node") in _ANSWER_NODES and isinstance(
                chunk, AIMessageChunk
            ):
                if chunk.content:
                    print(chunk.content, end="", flush=True)
                    streamed_any = True

        # The escalation stub returns a pre-built message (no LLM call), so it never
        # streams as tokens — fall back to printing the final assistant message.
        snapshot = graph.get_state(config).values
        if not streamed_any and snapshot.get("messages"):
            print(snapshot["messages"][-1].content, end="", flush=True)

        # Surface which specialist the supervisor routed to this turn.
        intent = snapshot.get("intent")
        confidence = snapshot.get("confidence")
        if intent is not None:
            label = "escalate" if confidence < settings.router_confidence_threshold else intent
            print(f"\n   ↳ routed to {label} (intent {intent}, confidence {confidence:.2f})")
        print()


if __name__ == "__main__":
    main()
