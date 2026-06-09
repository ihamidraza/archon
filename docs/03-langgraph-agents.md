# Phase 3 — A Stateful LangGraph Agent

> **Goal:** turn the RAG retriever and some tools into a real **agent** that decides when
> to act, loops until it has an answer, and **remembers the conversation**. We hand-build
> the **ReAct loop** in LangGraph so the mechanics are clear, then add memory with a
> SQLite **checkpointer**.

---

## 1. Why LangGraph (vs. a plain chain)

A Phase 1 chain runs start-to-finish, once. An **agent** needs to *loop*: think → maybe
call a tool → look at the result → think again → answer. That's a cycle with a decision in
it, which is exactly what **LangGraph** models — a graph of **nodes** (functions) connected
by **edges**, where some edges are **conditional**.

LangGraph also gives us, for free:
- **State** that flows between nodes (here, the list of messages).
- **Checkpointing** — durable memory + the ability to pause/resume (used for human-in-the-
  loop in Phase 5).
- **Streaming** of tokens and intermediate steps.

---

## 2. The ReAct loop (`backend/app/graph/react_agent.py`)

ReAct = *Reasoning + Acting*. Two nodes and one decision:

```
        ┌──────────────────────────────────────────────┐
        │                                              ▼
    START ──▶ [agent] ──(wants a tool?)──▶ [tools] ────┘   (loop back)
                  │
            (no tool call)
                  ▼
                 END
```

```python
llm = get_agent_model().bind_tools(tools)          # model can now emit tool calls

def agent_node(state: MessagesState) -> dict:
    messages = [SystemMessage(content=system_prompt), *state["messages"]]
    return {"messages": [llm.invoke(messages)]}     # appended via the add_messages reducer

builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")
graph = builder.compile(checkpointer=checkpointer)
```

Key pieces:
- **`MessagesState`** — a built-in state schema whose `messages` field uses the
  `add_messages` reducer, so returning `{"messages": [new_msg]}` *appends* rather than
  overwrites.
- **`bind_tools`** — tells the model which tools exist and their schemas; the model
  responds with `tool_calls` when it wants one.
- **`ToolNode`** — executes the requested tool calls and appends `ToolMessage` results.
- **`tools_condition`** — the conditional edge: if the last AI message has tool calls →
  go to `tools`; otherwise → `END`.
- **System prompt prepended per call**, not stored in state, so it never duplicates as
  history grows.

> **The shortcut:** `langchain.agents.create_agent(model, tools, ...)` builds this exact
> loop in one line. We hand-built it because every Phase 4 specialist *is* this loop —
> understanding it is the whole point.

`build_react_agent(tools=…, system_prompt=…, checkpointer=…)` is reusable; the concrete
Phase 3 agent lives in `backend/app/graph/agent.py` and wires in four tools.

---

## 3. Tools (`backend/app/tools/`)

| Tool | What it does |
| ---- | ------------ |
| `search_knowledge_base` | wraps the Phase 2 retriever — the agent calls it for policy/how-to questions |
| `get_subscription_status` | mock account lookup by email |
| `lookup_invoice` | mock invoice lookup by ID |
| `check_service_status` | mock status check |

Tools are plain functions decorated with `@tool`; the **docstring becomes the schema the
model sees**, so clear docstrings directly improve tool-selection accuracy. The mock tools
return deterministic canned data — enough to demonstrate tool-calling with no external
systems or cost.

---

## 4. Memory: the checkpointer (`backend/app/graph/memory.py`)

```python
graph = build_support_agent(checkpointer=get_checkpointer())
config = {"configurable": {"thread_id": "user-123"}}
graph.invoke({"messages": [HumanMessage("My email is sam@example.com")]}, config)
graph.invoke({"messages": [HumanMessage("What plan am I on?")]}, config)   # remembers!
```

A **checkpointer** saves graph state after every step, keyed by the `thread_id` you pass
at invoke time. Same thread = same memory. We use `SqliteSaver`, which persists to
`backend/data/checkpoints.sqlite`, so memory survives restarts. Pass `":memory:"` for an
ephemeral store (tests). This same pause/resume machinery is what enables human-in-the-loop
escalation in Phase 5.

---

## 5. Run it yourself

```bash
make ingest     # ensure the knowledge base exists (Phase 2)
make chat       # interactive agent: tool use + memory
make test       # graph-wiring unit tests + a live memory test
```

In `make chat`, try: *"What's your refund policy?"* (watch it search the KB), then tell it
your email is `sam@example.com` and ask *"what plan am I on?"* (watch it remember + look up
the account). `/new` starts a fresh thread; `/exit` quits.

### Files added this phase
```
backend/app/tools/knowledge_base.py   # KB search as a tool
backend/app/tools/mock_account.py     # mock subscription/invoice/status tools
backend/app/graph/react_agent.py      # reusable hand-built ReAct loop
backend/app/graph/agent.py            # the concrete single support agent
backend/app/graph/memory.py           # SqliteSaver checkpointer
backend/scripts/chat_cli.py           # `make chat`
backend/tests/test_agent.py           # wiring unit tests + live memory test
```

---

## 6. Concepts to take away

- **Agents are graphs with a loop.** The conditional edge (`tools_condition`) is what
  turns a one-shot chain into an agent that acts and re-evaluates.
- **`MessagesState` + `add_messages`** is the standard pattern: nodes return new messages,
  the reducer accumulates them.
- **Tool docstrings are prompts.** The model picks tools from their descriptions — write
  them well.
- **Memory is just a checkpointer + thread_id.** The same mechanism later powers
  pause/resume for human handoff.

**Next:** [`docs/04-supervisor-routing.md`](./04-supervisor-routing.md) — promote this
single agent into a **supervisor** that classifies each message and routes it to one of
four specialist agents.
