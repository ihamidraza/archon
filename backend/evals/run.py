"""Evaluation runner — ``make eval`` (local) or ``--langsmith`` (hosted experiments).

Two modes, same datasets/targets/evaluators:

* **local** (default) — runs every target + evaluator in-process and prints a score table.
  Deterministic, offline-friendly (the guardrails suite needs no model at all), and
  CI-safe: it writes nothing external.
* **--langsmith** — uploads each dataset (idempotently) and runs a LangSmith ``evaluate``
  experiment, so results show up as comparable experiments in the UI. Requires a real
  ``LANGCHAIN_API_KEY``.

Usage::

    uv run python -m backend.evals.run                 # all suites, local
    uv run python -m backend.evals.run --suite routing # one suite
    uv run python -m backend.evals.run --langsmith     # upload + hosted experiments
"""

from __future__ import annotations

import argparse
import inspect
from collections import defaultdict

import httpx

from backend.app.core.observability import configure_tracing
from backend.app.core.settings import settings
from backend.evals.datasets import (
    DATASETS,
    GUARDRAIL_EXAMPLES,
    QA_EXAMPLES,
    ROUTING_EXAMPLES,
    sync_dataset,
)
from backend.evals.evaluators import SUITE_EVALUATORS
from backend.evals.targets import guardrail_target, qa_target, route_target

# suite key -> (dataset name, examples, target). Order is cheap → expensive.
SUITES = {
    "guardrails": ("archon-guardrails", GUARDRAIL_EXAMPLES, guardrail_target),
    "routing": ("archon-routing", ROUTING_EXAMPLES, route_target),
    "qa": ("archon-qa", QA_EXAMPLES, qa_target),
}
_NEEDS_OLLAMA = {"routing", "qa"}


def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


def _call_evaluator(evaluator, inputs, outputs, reference_outputs) -> dict:
    """Invoke an evaluator with just the kwargs its signature declares."""
    params = inspect.signature(evaluator).parameters
    kwargs = {}
    if "inputs" in params:
        kwargs["inputs"] = inputs
    if "outputs" in params:
        kwargs["outputs"] = outputs
    if "reference_outputs" in params:
        kwargs["reference_outputs"] = reference_outputs
    return evaluator(**kwargs)


# --------------------------------------------------------------------------- #
# Local mode
# --------------------------------------------------------------------------- #
def run_local(suite_keys: list[str]) -> dict[str, dict[str, float]]:
    """Run suites in-process and print a score table. Returns {suite: {metric: mean}}."""
    summary: dict[str, dict[str, float]] = {}

    for key in suite_keys:
        name, examples, target = SUITES[key]
        evaluators = SUITE_EVALUATORS[key]
        scores: dict[str, list[float]] = defaultdict(list)

        print(f"\n▶ {key}  ({len(examples)} examples · dataset '{name}')")
        for example in examples:
            outputs = target(example.inputs)
            for evaluator in evaluators:
                result = _call_evaluator(evaluator, example.inputs, outputs, example.outputs)
                if result.get("score") is not None:
                    scores[result["key"]].append(float(result["score"]))

        suite_means: dict[str, float] = {}
        for metric, values in scores.items():
            mean = sum(values) / len(values)
            suite_means[metric] = mean
            print(f"    {metric:<22} {mean:6.1%}  ({sum(values):.0f}/{len(values)})")
        summary[key] = suite_means

    _print_summary(summary)
    return summary


def _print_summary(summary: dict[str, dict[str, float]]) -> None:
    print("\n" + "=" * 48)
    print("Summary")
    print("-" * 48)
    for suite, metrics in summary.items():
        for metric, mean in metrics.items():
            print(f"  {suite:<12} {metric:<22} {mean:6.1%}")
    print("=" * 48)


# --------------------------------------------------------------------------- #
# LangSmith mode
# --------------------------------------------------------------------------- #
def run_langsmith(suite_keys: list[str]) -> None:
    """Upload datasets and run hosted LangSmith experiments for each suite."""
    from langsmith import Client, evaluate

    client = Client()
    for key in suite_keys:
        name, examples, target = SUITES[key]
        description = DATASETS[name][0]
        sync_dataset(client, name, description, examples)
        print(f"\n▶ {key}: running LangSmith experiment over '{name}' …")
        results = evaluate(
            target,
            data=name,
            evaluators=SUITE_EVALUATORS[key],
            experiment_prefix=name,
            client=client,
            max_concurrency=1,  # one at a time — local Ollama is the bottleneck
        )
        print(f"    experiment: {getattr(results, 'experiment_name', name)}")
    print("\nView results at https://smith.langchain.com")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Run Archon evaluations.")
    parser.add_argument(
        "--suite", choices=[*SUITES, "all"], default="all", help="Which suite to run."
    )
    parser.add_argument(
        "--langsmith", action="store_true", help="Upload + run hosted LangSmith experiments."
    )
    args = parser.parse_args()

    suite_keys = list(SUITES) if args.suite == "all" else [args.suite]

    if _NEEDS_OLLAMA.intersection(suite_keys) and not _ollama_up():
        running = [k for k in suite_keys if k not in _NEEDS_OLLAMA]
        if not running:
            print(f"❌ Ollama unreachable at {settings.ollama_base_url}; nothing to run.")
            return 1
        print(f"⚠️  Ollama unreachable — running only: {', '.join(running)}")
        suite_keys = running

    if args.langsmith:
        if not configure_tracing():
            print("❌ --langsmith needs a real LANGCHAIN_API_KEY in .env.")
            return 1
        run_langsmith(suite_keys)
    else:
        run_local(suite_keys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
