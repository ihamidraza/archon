# Phase 7 — Evaluation

> **Goal:** stop *eyeballing* quality and start **measuring** it. We build labeled
> **datasets**, **targets** (the things under test), and **evaluators** (the scorers), then
> run them two ways: a fast **local** runner (`make eval`) and **LangSmith experiments**
> (`--langsmith`). The first eval run immediately earned its keep — it caught a real defect
> (see §6).

---

## 1. The anatomy of an eval

Three pieces, deliberately decoupled so each is independently testable:

```
 dataset (Example: inputs → reference outputs)
      │
      ▼
   target(inputs) → outputs          # the system under test
      │
      ▼
   evaluator(outputs, reference) → {score}   # the scorer
```

We measure three suites:

| Suite | Target | Measures |
| ----- | ------ | -------- |
| **routing** | `classify()` (supervisor) | does each message reach the right specialist? |
| **guardrails** | input-guard decision | are injections refused, secrets redacted, benign allowed? |
| **qa** | the *whole* guarded graph | is the end-to-end answer correct & grounded? |

Datasets live in `backend/evals/datasets.py`, one `Example(inputs, outputs)` per row. QA
"reference facts" are pulled **verbatim from the synthetic KB**, so they're objective.

---

## 2. Targets (`evals/targets.py`)

A target maps an example's `inputs` to `outputs` the evaluators can score:

- `route_target` → `{"intent", "confidence"}` (router model only — fast).
- `guardrail_target` → `{"action": "refuse"|"redact"|"allow", "entities": [...]}` —
  **deterministic, no model**, so this whole suite runs offline.
- `qa_target` → runs `build_support_graph()` end-to-end and returns
  `{"answer", "intent", "context"}`, capturing the retrieved context so groundedness can be
  judged.

---

## 3. Evaluators (`evals/evaluators.py`)

Pure functions with the exact parameter names LangSmith injects (`inputs`, `outputs`,
`reference_outputs`), so the **same function** works locally and in a hosted experiment.
Two tiers:

**Deterministic** (the backbone — reproducible, unit-tested):
- `routing_accuracy` — predicted intent == labeled intent.
- `guardrail_action` — predicted action == expected action.
- `answer_includes_facts` — every required fact appears in the answer (after **unicode +
  whitespace normalization** — see §6).

**Model-based** (reported, not asserted — inherently noisier):
- `answer_grounded` — reuses the Phase 5 groundedness check on `(answer, context)`.
- `qa_correctness_judge` — **LLM-as-judge** correctness. Runs on the **router** model
  (llama3.2), because the agent model (qwen3) emits `<think>` blocks that break structured
  output. Both model-based evaluators catch their own exceptions and return `score=None`
  so one flaky call never aborts a run.

---

## 4. Two runners (`evals/run.py`)

```bash
uv run python -m backend.evals.run                  # local, all suites
uv run python -m backend.evals.run --suite routing  # one suite
uv run python -m backend.evals.run --langsmith      # hosted LangSmith experiments
```

- **Local** runs everything in-process and prints a score table. It writes nothing
  external, is CI-safe, and the guardrails suite needs no model at all. If Ollama is down,
  it automatically runs only the suites that don't need it.
- **`--langsmith`** uploads each dataset (idempotently, keyed by name) and runs a
  `langsmith.evaluate` experiment, so runs are comparable in the UI. It requires a real
  `LANGCHAIN_API_KEY`.

`make eval` runs the local path.

---

## 5. Illustrative results (local, qwen3.6 + llama3.2)

```
guardrails   guardrail_action       100.0%   (11/11)
routing      routing_accuracy        87.5%   (14/16)
qa           answer_correctness      80.0%   (4/5)
qa           groundedness           100.0%   (4/4)
qa           qa_correctness_judge    80.0%   (4/5)
```

Honest numbers for small local models. Guardrails are deterministic (always 100%). Routing
misses ~2/16 genuinely ambiguous messages. The QA metrics *disagree* by design — that
disagreement is the point: a brittle substring check and a lenient LLM judge fail on
different examples, and groundedness confirms the answers are at least supported. Chasing
100% here would mean overfitting the dataset, not improving the system.

---

## 6. What the eval caught (and how it was fixed)

This is why you evaluate. The very first QA run surfaced three issues:

1. **Reasoning leak (real defect).** Specialist answers contained raw
   `<think>…</think>` chain-of-thought — qwen3.6 ignores `reasoning=False`. This polluted
   every customer-facing answer, not just the eval. **Fixed** at the agent layer:
   `backend/app/llm/text.py::strip_reasoning` removes the blocks from stored answers, and
   the chat CLI filters them from the *stream* live (`visible_so_far`). This also stabilized
   a previously-flaky memory test.
2. **Brittle substring matching.** The refund answer *did* say "7 days" — but with a
   non-breaking space, so the naive check failed. **Fixed** with NFKC + whitespace
   normalization in `answer_includes_facts`.
3. **Over-strict judge.** llama3.2 marked a correct `$99/month (or $990/year)` answer
   wrong for "also giving the yearly price". **Fixed** by tightening the judge prompt to
   explicitly allow extra accurate detail.

A separate finding stayed a finding, not a hack: the memory test was asserting that the
model would *echo* a remembered secret code — which the cautious support persona declines.
We re-pointed it at the actual Phase 3 feature (the checkpointer persisting history across
turns), which is deterministic.

### Files added/changed this phase
```
backend/evals/datasets.py            # 3 labeled suites + idempotent LangSmith upload
backend/evals/targets.py             # route / guardrail / end-to-end QA targets
backend/evals/evaluators.py          # deterministic + model-based scorers
backend/evals/run.py                 # local + --langsmith runner with a summary table
backend/app/llm/text.py              # strip_reasoning / visible_so_far  (defect fix)
backend/app/graph/react_agent.py     # strip leaked reasoning from answers   [updated]
backend/scripts/chat_cli.py          # filter reasoning from the live stream [updated]
backend/tests/test_evals.py          # dataset integrity + evaluator + offline suite tests
backend/tests/test_text.py           # reasoning-strip unit tests
backend/tests/test_agent.py          # memory test re-pointed at the checkpointer [updated]
```

---

## 7. Concepts to take away

- **Decouple dataset / target / evaluator.** Each becomes independently testable, and the
  evaluators run unchanged locally or on LangSmith.
- **Deterministic where you can, model-judged where you must.** Exact checks are your
  regression backbone; LLM-judges add coverage but are noisy — report them, don't gate on
  them.
- **Evals find real bugs.** The reasoning leak was a production defect that manual chatting
  had glossed over; a measured run made it obvious.
- **Don't overfit the metric.** Normalize unfair checks and fix genuine defects — but a
  disagreeing judge and a ~88% router are *information*, not failures to paper over.

**Next:** [`docs/08-backend-api.md`](./08-backend-api.md) — wrap the graph in a **FastAPI**
service with SSE streaming, sessions/threads, and rate limiting, so the whole system is
reachable over HTTP.
