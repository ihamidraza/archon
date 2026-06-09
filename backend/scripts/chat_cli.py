"""Interactive terminal chat with the support agent — run via ``make chat``.

Demonstrates two LangGraph features at once:
  * **Tool use** — the agent searches the knowledge base / looks up accounts as needed.
  * **Memory** — every turn shares one ``thread_id``, so the agent remembers the
    conversation. Restart the script with the same thread to resume it.

Commands inside the loop:  /new  (start a fresh thread)   ·   /exit  (quit)
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessageChunk, HumanMessage

from backend.app.graph.agent import build_support_agent
from backend.app.graph.memory import get_checkpointer


def main() -> None:
    agent = build_support_agent(checkpointer=get_checkpointer())
    thread_id = f"cli-{uuid.uuid4().hex[:8]}"

    print("Archon support agent — type your message. (/new = new chat, /exit = quit)\n")
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
        # stream_mode="messages" yields (message_chunk, metadata); we print only the
        # assistant's text tokens from the agent node (not tool-call plumbing).
        for chunk, meta in agent.stream(
            {"messages": [HumanMessage(content=user)]},
            config=config,
            stream_mode="messages",
        ):
            if meta.get("langgraph_node") == "agent" and isinstance(chunk, AIMessageChunk):
                if chunk.content:
                    print(chunk.content, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
