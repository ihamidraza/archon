# Phase 6 — LangSmith Observability

> **Goal:** see *inside* the agent. Every routing decision, tool call, guardrail verdict,
> and token now shows up as a structured **trace** in LangSmith — searchable, taggable, and
> attachable to **feedback**. Crucially, this stays **opt-in and zero-cost**: with no API
> key the whole system runs exactly as before, just untraced.

---

## 1. Why tracing matters here

By Phase 5 a single user message can fan out through ~6 nodes, two model tiers, tool calls,
a groundedness check, and maybe a retry. When something goes wrong ("why did this route to
*sales*?", "why did the answer get flagged ungrounded?"), reading logs is hopeless. A trace
is the call tree — inputs, outputs, latency, and token counts at every node — so you can
*see* the decision instead of guessing.

LangChain and LangGraph emit these traces **automatically**. The only real work is
(a) turning it on safely from our config, (b) labelling runs so they're findable, and
(c) recording feedback.

---

## 2. The config bridge (`core/observability.py`)

The subtlety: LangChain reads tracing settings from **`os.environ`**, but ours live in a
`.env`-backed `settings` object. `configure_tracing()` copies them across — but only when a
**real** API key is present:

```python
def configure_tracing(*, force=None) -> bool:
    enabled = settings.langchain_tracing_v2 and _is_real_key(settings.langchain_api_key)
    if not enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return False
    os.environ["LANGCHAIN_TRACING_V2"] = "true"   # compat flag
    os.environ["LANGSMITH_TRACING"]   = "true"    # modern flag
    # … endpoint / api key / project for both prefixes …
    return True
```

`_is_real_key` rejects blanks and the shipped placeholder (`ls-...replace-me...`), so a
fresh clone traces **nothing** and costs **nothing** until you paste a key into `.env`.

> ⚠️ **Gotcha worth remembering:** never set the bare `LANGCHAIN_TRACING` env var — that's
> the *removed V1* flag and raises `RuntimeError` at the first model call. Only
> `LANGCHAIN_TRACING_V2` and `LANGSMITH_TRACING` are valid. (We hit this; the fix is why
> `configure_tracing` is careful about exactly which vars it sets.)

Call it once at startup — `make chat` and `make env-check` both do. `env-check` now prints:

```
✅ LangSmith tracing enabled → project 'archon'      # or:
⚠️ LangSmith tracing off (optional; set LANGCHAIN_API_KEY to enable)
```

---

## 3. Labelling runs (`run_config`)

A trace you can't find is useless. `run_config()` builds a `RunnableConfig` attached to
every graph invocation so runs are filterable in the LangSmith UI:

```python
config = run_config(
    thread_id,                       # also drives the checkpointer → ties a conversation together
    tags=["cli"],                    # + always-on "archon" tag
    metadata={"channel": "cli"},     # + app + thread_id
    run_name="archon_support_turn",  # friendly name in the trace list
)
graph.stream({"messages": [...]}, config=config, ...)
```

Now in LangSmith you can filter to `tag:archon`, group by `thread_id`, or open a single
`archon_support_turn` and drill into the supervisor's structured `Route`, each specialist's
tool calls, and the groundedness verdict — the whole Phase 4/5 pipeline, visualized.

---

## 4. Feedback (`log_feedback`)

Traces become a dataset when you attach judgments to them. We capture the **root run id**
during streaming with `collect_runs()` and let the user score the turn:

```python
with collect_runs() as cb:
    graph.stream(..., config=config)
run_id = str(cb.traced_runs[0].id)

log_feedback(run_id, key="user_score", score=1.0, comment="…")   # /good
```

In `make chat`, `/good` and `/bad [note]` record feedback on the last turn and print the
trace URL. `log_feedback` is a **no-op when tracing is off**, so the commands never error on
a keyless setup. These labels feed directly into Phase 7's evaluation datasets.

---

## 5. Run it yourself

```bash
# optional: paste a key from https://smith.langchain.com into .env
LANGCHAIN_API_KEY=lsv2_...        # LANGCHAIN_TRACING_V2=true is already set

make env-check     # confirms "LangSmith tracing enabled → project 'archon'"
make chat          # every turn is traced; rate one with /good or /bad
make test          # observability unit tests are hermetic (no key, no network)
```

Then open the project in LangSmith: filter by the `archon` tag, open a turn, and watch the
supervisor → specialist → guardrail tree.

### Files added/changed this phase
```
backend/app/core/observability.py    # configure_tracing · run_config · log_feedback · run_url
backend/app/core/settings.py         # + langchain_api_key / langchain_endpoint   [updated]
backend/scripts/chat_cli.py          # tracing on, tagged runs, /good /bad feedback [updated]
backend/scripts/env_check.py         # reports tracing status                       [updated]
backend/tests/test_observability.py  # hermetic unit tests (env isolated)
```

---

## 6. Concepts to take away

- **Tracing is config, not code.** LangChain auto-instruments; your job is to set the right
  env vars (safely) and never the deprecated V1 one.
- **Opt-in keeps it free.** Gate on a *real* key so the default clone traces nothing.
- **Tags + metadata + `run_name` make traces usable.** A consistent `run_config` turns a
  pile of runs into a filterable history keyed by conversation.
- **`collect_runs` → `run_id` → `log_feedback`.** Capturing the run id is what lets you
  attach human judgment, which becomes evaluation data next.

**Next:** [`docs/07-evaluation.md`](./07-evaluation.md) — build **LangSmith datasets** and
**evaluators** (routing accuracy, RAG correctness, guardrail catch-rate) to measure the
system instead of eyeballing it.
