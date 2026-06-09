# Phase 1 — LangChain Fundamentals

> **Goal:** master the three LangChain primitives the whole system is built on —
> **chains (LCEL)**, **structured output**, and **streaming** — and centralise model
> creation behind a single **tiered factory**. Everything here runs on local Ollama
> models at zero cost.
>
> **LangChain version:** this project resolved to **LangChain v1** (`langchain 1.3.x`,
> `langchain-core 1.4.x`, `langchain-ollama 1.1.x`). The primitives below are stable
> across v0.3 → v1, but imports come from `langchain_core`.

---

## 1. The model factory (`backend/app/llm/factory.py`)

Rather than scattering `ChatOllama(...)` calls across the codebase, **every model is
built in one place**. This is a small decision with big downstream payoff: when we later
add timeouts, swap a model, or tune temperature, we touch one file.

```python
from backend.app.llm.factory import get_router_model, get_agent_model, get_embeddings

router = get_router_model()      # llama3.2:3b  · temp 0.0 · reasoning OFF · ctx 4096
agent  = get_agent_model()       # qwen3.6      · temp 0.3 · reasoning OFF · ctx 8192
embeds = get_embeddings()        # nomic-embed-text
```

### Why two tiers?
| Tier | Model | Job | Why these settings |
| ---- | ----- | --- | ------------------ |
| `router` | `llama3.2:3b` | classification, guardrail checks | **temp 0.0** → deterministic labels; **small ctx** → fast; runs on *every* turn |
| `agent` | `qwen3.6` | writing answers, calling tools | **temp 0.3** → natural prose; **larger ctx** → fits retrieved docs + history |

### The `reasoning` flag (important for qwen3)
`qwen3.6` is a *thinking* model — left to itself it emits a `<think>…</think>` block
before answering. That chain-of-thought pollutes structured output and slows the hot
path. `langchain-ollama`'s `ChatOllama(reasoning=False, …)` disables it, so the factory
sets `reasoning=False` by default. It's a no-op on non-thinking models like
`llama3.2:3b`. You can opt back in per call: `get_chat_model("agent", reasoning=True)`.

### Caching
`get_router_model()`, `get_agent_model()` and `get_embeddings()` are wrapped in
`functools.lru_cache`, so repeated calls return the *same* client instance instead of
re-constructing it. (The test `test_cached_builders_return_same_instance` asserts this.)

---

## 2. LCEL — composing with the `|` operator

**LCEL (LangChain Expression Language)** lets you pipe *runnables* together. The output
of each stage becomes the input of the next:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", SUPPORT_SYSTEM_PROMPT),
    ("human", "A customer writes: {question}\nReply in one short paragraph."),
])
chain = prompt | get_agent_model() | StrOutputParser()
answer = chain.invoke({"question": "How do I reset my password?"})  # -> str
```

- `ChatPromptTemplate` turns a dict of variables into chat messages.
- `get_agent_model()` runs the model, returning an `AIMessage`.
- `StrOutputParser()` extracts the plain text, so the chain returns a `str` rather than a
  message object.

Every runnable shares the same interface — `.invoke()`, `.stream()`, `.batch()` and
their async variants — which is what makes them composable. This pipe-composed chain is
the unit we'll later wrap inside LangGraph nodes.

---

## 3. Structured output — typed results instead of prose

The single most important primitive for **reliable routing**. Instead of parsing free
text, we make the model return JSON that validates against a Pydantic schema:

```python
class IntentClassification(BaseModel):
    intent: Literal["billing", "technical", "account", "sales"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

classifier = get_router_model().with_structured_output(IntentClassification)
result = classifier.invoke("I was charged twice this month.")
result.intent       # -> "billing"   (a typed value you can branch on)
result.confidence   # -> 0.80
```

Under the hood `with_structured_output` passes the schema to Ollama's structured-output
mode, gets back JSON, and parses + validates it into the model. If the JSON is malformed
or violates the schema (e.g. `confidence` out of range), validation raises — turning a
"the model said something weird" failure into a catchable, typed error.

This is exactly how the **Phase 4 supervisor** decides where to route, and how several
**Phase 5 guardrails** return pass/fail verdicts. `IntentClassification` here is a
deliberate preview of the real router.

> **Why low temperature here?** Classification wants the *same* answer every time for the
> same input. The router's `temperature=0.0` makes that near-deterministic.

---

## 4. Streaming — tokens as they're generated

Any runnable can stream. Instead of waiting for the full answer, iterate chunks:

```python
for chunk in chain.stream({"question": "What is two-factor authentication?"}):
    print(chunk, end="", flush=True)
```

This is what gives the Phase 8 API its server-sent-events feel and the Phase 9 chat UI
its typewriter effect. The same `chain` object supports both `.invoke()` (wait for all)
and `.stream()` (incremental) with no code changes.

---

## 5. Run it yourself

```bash
uv run python -m backend.scripts.demo_langchain     # guided tour of all three
make test                                           # 7 tests, ~4s
```

Expected demo output: a password-reset paragraph (LCEL), three correctly-classified
intents with confidences (structured output), and a streamed one-liner on 2FA.

### Files added this phase
```
backend/app/llm/factory.py        # tiered model factory (the reusable core)
backend/app/llm/prompts.py        # shared assistant persona (SUPPORT_SYSTEM_PROMPT)
backend/scripts/demo_langchain.py # runnable walkthrough
backend/tests/test_llm_factory.py # unit + skippable integration tests
```

---

## 6. Concepts to take away

- **Centralise model construction.** One factory = one place to enforce the tiered
  strategy, connection settings, and reasoning toggles.
- **LCEL is just composition.** `prompt | model | parser` — every piece shares one
  runnable interface, so chains nest cleanly into the graph later.
- **Structured output is the backbone of control flow.** Typed Pydantic results let the
  router and guardrails *branch on data*, not on string matching.
- **Stream for UX, invoke for logic.** Same chain, two execution modes.

**Next:** [`docs/02-rag-pipeline.md`](./02-rag-pipeline.md) — generate the synthetic
Nimbus knowledge base, embed it with `nomic-embed-text`, and build a grounded retriever
over Chroma.
