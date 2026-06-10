"""Tests for the evaluation harness.

Deterministic parts (dataset integrity, pure evaluators, the whole guardrails suite) are
asserted offline. Routing/QA accuracy need Ollama and are skipped when it's unreachable.
"""

from __future__ import annotations

import httpx
import pytest

from backend.app.core.settings import settings
from backend.evals.datasets import (
    GUARDRAIL_EXAMPLES,
    QA_EXAMPLES,
    ROUTING_EXAMPLES,
)
from backend.evals.evaluators import (
    answer_includes_facts,
    guardrail_action,
    routing_accuracy,
)
from backend.evals.run import SUITES, _call_evaluator, run_local
from backend.evals.targets import guardrail_target, route_target

_INTENTS = {"billing", "technical", "account", "sales"}


# --------------------------------------------------------------------------- #
# Dataset integrity
# --------------------------------------------------------------------------- #
def test_routing_dataset_labels_valid_and_balanced():
    labels = [e.outputs["intent"] for e in ROUTING_EXAMPLES]
    assert set(labels) == _INTENTS
    # Each intent has the same number of examples (a balanced routing set).
    counts = {i: labels.count(i) for i in _INTENTS}
    assert len(set(counts.values())) == 1


def test_guardrail_dataset_actions_valid():
    for e in GUARDRAIL_EXAMPLES:
        assert e.outputs["action"] in {"refuse", "redact", "allow"}


def test_qa_dataset_has_facts_and_categories():
    for e in QA_EXAMPLES:
        assert e.outputs["must_include"]
        assert e.outputs["category"] in _INTENTS


# --------------------------------------------------------------------------- #
# Pure evaluators
# --------------------------------------------------------------------------- #
def test_routing_accuracy_scoring():
    assert routing_accuracy({"intent": "billing"}, {"intent": "billing"})["score"] == 1.0
    assert routing_accuracy({"intent": "sales"}, {"intent": "billing"})["score"] == 0.0


def test_guardrail_action_scoring():
    assert guardrail_action({"action": "refuse"}, {"action": "refuse"})["score"] == 1.0
    assert guardrail_action({"action": "allow"}, {"action": "refuse"})["score"] == 0.0


def test_answer_includes_facts_scoring():
    good = answer_includes_facts({"answer": "Refunds within 7 days."}, {"must_include": ["7 days"]})
    bad = answer_includes_facts({"answer": "No idea."}, {"must_include": ["7 days"]})
    assert good["score"] == 1.0
    assert bad["score"] == 0.0


def test_call_evaluator_passes_only_declared_kwargs():
    # routing_accuracy declares (outputs, reference_outputs) — inputs must be dropped.
    result = _call_evaluator(
        routing_accuracy,
        {"message": "ignored"},
        {"intent": "billing"},
        {"intent": "billing"},
    )
    assert result["score"] == 1.0


# --------------------------------------------------------------------------- #
# Guardrails suite — fully deterministic, so we assert a perfect catch-rate
# --------------------------------------------------------------------------- #
def test_guardrail_target_matches_every_label():
    for example in GUARDRAIL_EXAMPLES:
        out = guardrail_target(example.inputs)
        assert out["action"] == example.outputs["action"], example.inputs["message"]


def test_redact_examples_detect_expected_entities():
    for example in GUARDRAIL_EXAMPLES:
        if example.outputs["action"] != "redact":
            continue
        out = guardrail_target(example.inputs)
        assert set(example.outputs["entities"]).issubset(set(out["entities"]))


def test_run_local_guardrails_scores_perfect():
    summary = run_local(["guardrails"])
    assert summary["guardrails"]["guardrail_action"] == 1.0


# --------------------------------------------------------------------------- #
# Live: routing accuracy over the labeled set
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


needs_ollama = pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")


@needs_ollama
def test_routing_target_accuracy_is_high():
    correct = sum(
        route_target(e.inputs)["intent"] == e.outputs["intent"] for e in ROUTING_EXAMPLES
    )
    accuracy = correct / len(ROUTING_EXAMPLES)
    assert accuracy >= 0.75, f"routing accuracy {accuracy:.0%} below threshold"


def test_suites_registry_is_consistent():
    assert set(SUITES) == {"routing", "guardrails", "qa"}
