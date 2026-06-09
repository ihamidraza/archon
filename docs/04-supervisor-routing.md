# Phase 4 — Supervisor Routing & Specialist Agents

> **Goal:** stop using one do-everything agent. Put a fast **supervisor** in front that
> classifies each message and hands it to the right **specialist** (Billing · Technical ·
> Account · Sales), each scoped to its own slice of the knowledge base and tools. This is
> the **multi-agent** pattern, hand-built in LangGraph.

---

## 1. Why route at all?

The Phase 3 agent had *every* tool and the *whole* knowledge base. That works, but it
scales badly: more tools = more chances to pick the wrong one, longer prompts, fuzzier
answers, and no way to give (say) the billing flow its own rules. **Routing** fixes this
by splitting one big agent into small, focused ones and adding a cheap classifier that
decides who handles what.

```
  START
    │
    ▼
┌─────────────┐   classify (structured output, fast model)
│ supervisor  │ ── billing? technical? account? sales? ── + confidence
└──────┬──────┘
       │ conditional edge (route_from_supervisor)
   ┌───┼─────────┬──────────┬──────────┐
   ▼   ▼         ▼          ▼          ▼
billing technical account  sales   escalate   ← low confidence
 (each a ReAct subgraph)              (human handoff stub → Phase 5)
   └───┴─────────┴──────────┴──────────┘
                   ▼
                  END
```

Two design rules pay off later:
- **Classify and route are separate.** `supervisor_node` only *records* a decision in
  state; `route_from_supervisor` *reads* state to choose the next node. Each is trivially
  testable on its own.
- **One source of truth.** The four specialists live in a registry (`SPECIALISTS`); the
  supervisor builds its menu of choices from that same registry, so they can never drift.

---

## 2. The supervisor: structured classification (`graph/supervisor.py`)

The supervisor uses the **fast** tier (`llama3.2:3b`) and, crucially, **structured
output** so we get a validated object instead of text to parse:

```python
class Route(BaseModel):
    intent: Literal["billing", "technical", "account", "sales"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

classifier = ROUTER_PROMPT | get_router_model().with_structured_output(Route)
```

`with_structured_output(Route)` makes LangChain hand the model the schema and return a
parsed `Route` — `route.intent`, `route.confidence`. No regex, no `json.loads`, no
"model added a sentence before the JSON" bugs.

The node writes the decision into state; the edge function reads it:

```python
def supervisor_node(state) -> dict:
    route = classify(_latest_user_text(state))
    return {"intent": route.intent, "confidence": route.confidence}

def route_from_supervisor(state) -> str:
    if state.get("confidence", 0.0) < settings.router_confidence_threshold:
        return "escalate"          # not sure enough → human handoff
    return state["intent"]         # node names == intent labels
```

**Confidence is a guardrail.** A vague or off-topic message ("can you help me?") still
gets a best-guess label but a *low* confidence, which routes to `escalate` instead of
guessing at a specialist. Phase 5 turns that stub into a real human-in-the-loop pause.

---

## 3. State that carries the decision (`graph/state.py`)

Phase 3's `MessagesState` only held `messages`. The supervisor needs to pass its decision
to the routing edge, so we extend it:

```python
class SupportState(MessagesState):     # keeps messages + add_messages reducer
    intent: NotRequired[str]
    confidence: NotRequired[float]
```

Because `SupportState` still has the `messages` channel, the specialist subgraphs (which
only declare `messages`) plug straight in — they read and append messages and simply
ignore `intent`/`confidence`.

---

## 4. Specialists: the same loop, differently equipped (`graph/agents/specialists.py`)

A specialist is **not a new kind of agent** — it's the Phase 3 `build_react_agent` loop
with three things swapped: a **domain-scoped KB search tool**, the **business tools** it
needs, and a **tailored system prompt**. We capture exactly those differences
declaratively:

```python
@dataclass(frozen=True)
class SpecialistSpec:
    key: str            # "billing"  — also KB category, intent label, and node name
    label: str          # "Billing"
    routing_hint: str   # how the supervisor decides to pick it
    focus: str          # injected into the system prompt
    tools_hint: str     # when-to-use guidance for its tools
    extra_tools: list[BaseTool]
```

| Specialist | KB scope | Extra tools |
| ---------- | -------- | ----------- |
| **Billing**   | `billing`   | `lookup_invoice`, `get_subscription_status` |
| **Technical** | `technical` | `check_service_status` |
| **Account**   | `account`   | `get_subscription_status` |
| **Sales**     | `sales`     | — (KB only) |

### Domain-scoped search

Each specialist gets its *own* search tool that can only see its category, built by a
small factory (`tools/knowledge_base.py`):

```python
def make_kb_search_tool(category, label) -> BaseTool:
    def _search(query: str) -> str:
        docs = get_retriever(category=category).invoke(query)   # filtered to one category
        return format_docs(docs) if docs else _NO_RESULTS
    return StructuredTool.from_function(
        func=_search,
        name=f"search_{category}_knowledge_base",
        description=f"Search the Nimbus {label} help articles …",
    )
```

The billing agent literally cannot surface a sales doc — the `category` filter we added
to the retriever back in Phase 2 does the scoping. `StructuredTool.from_function` lets us
mint a distinctly **named** tool with a tailored description at runtime (a plain `@tool`
has one fixed name/docstring).

---

## 5. Wiring it together (`graph/build.py`)

```python
builder = StateGraph(SupportState)
builder.add_node("supervisor", supervisor_node)
builder.add_node("escalate", escalate_node)
for key, agent in build_all_specialists().items():
    builder.add_node(key, agent)          # a compiled subgraph IS a valid node

builder.add_edge(START, "supervisor")
builder.add_conditional_edges(
    "supervisor", route_from_supervisor,
    {**{k: k for k in SPECIALISTS}, "escalate": "escalate"},
)
for key in SPECIALISTS:
    builder.add_edge(key, END)
builder.add_edge("escalate", END)

graph = builder.compile(checkpointer=checkpointer, name="support_supervisor")
```

Two things worth calling out:

- **Subgraphs as nodes.** A compiled specialist graph is added as a single node. Because
  the parent and child share the `messages` channel, the message history flows in and the
  specialist's reply flows out — no glue code.
- **Memory lives at the top.** Pass the checkpointer to the *parent* `compile`, never to
  the nested specialists. The whole multi-agent conversation is then persisted under one
  `thread_id`, exactly like Phase 3. The next user turn re-enters at the supervisor, so a
  follow-up can be re-routed to a different specialist while keeping full history.

---

## 6. Run it yourself

```bash
make ingest     # ensure the category-tagged KB exists (Phase 2)
make chat       # supervised chat: watch the route printed after each answer
make test       # graph wiring + registry unit tests + live routing tests
```

In `make chat`, try messages that should land in different teams and watch the
`↳ routed to …` footer:

- *"I was double-charged, can I get a refund?"* → **billing**
- *"The export API returns a 500 error."* → **technical**
- *"How do I turn on SSO?"* → **account**
- *"What's in the Enterprise plan?"* → **sales**
- *"hi"* / something vague → low confidence → **escalate**

### Files added this phase
```
backend/app/graph/state.py              # SupportState (messages + intent + confidence)
backend/app/graph/supervisor.py         # structured-output classifier + routing fn
backend/app/graph/agents/specialists.py # SpecialistSpec registry + builders
backend/app/graph/build.py              # assembles supervisor + specialists + escalate
backend/app/tools/knowledge_base.py     # make_kb_search_tool (category-scoped)  [extended]
backend/scripts/chat_cli.py             # now drives the supervised graph        [updated]
backend/tests/test_supervisor.py        # wiring/registry unit tests + live routing
```

---

## 7. Concepts to take away

- **Supervisor pattern = classify, then dispatch.** A cheap structured-output classifier
  in front of focused specialists beats one agent holding every tool.
- **Structured output replaces parsing.** `with_structured_output(PydanticModel)` turns
  "route this" into a validated object with a confidence you can threshold on.
- **A specialist is just the ReAct loop + a config.** Keeping that config in one registry
  means the router and the agents share a single source of truth.
- **Subgraphs compose.** A compiled graph is a node; shared state channels (`messages`)
  connect parent and child with no boilerplate, and the parent's checkpointer gives the
  whole system memory.

**Next:** [`docs/05-guardrails.md`](./05-guardrails.md) — wrap this graph in **input and
output guardrails** (PII redaction, prompt-injection detection, groundedness checks) and
turn the `escalate` stub into a real **human-in-the-loop** interrupt.
