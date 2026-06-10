"""Evaluators — pure scoring functions shared by the local runner and LangSmith.

Each evaluator takes some subset of ``inputs`` / ``outputs`` / ``reference_outputs`` (the
exact parameter names LangSmith's ``evaluate`` injects by signature inspection) and returns
a ``{"key", "score", ...}`` dict. Keeping them pure means the local runner calls them with
plain kwargs and the unit tests assert on them directly — no LangSmith required.

Two tiers:

* **Deterministic** — ``routing_accuracy``, ``guardrail_action``, ``answer_includes_facts``.
  No model calls; fully reproducible; the backbone of the test suite.
* **Model-based** — ``answer_grounded`` (reuses the Phase 5 groundedness check) and
  ``qa_correctness_judge`` (LLM-as-judge). These need Ollama and are inherently noisier, so
  they're reported but not asserted on exact values.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.app.guardrails.groundedness import check_groundedness
from backend.app.llm.factory import get_router_model


def _normalize(text: str) -> str:
    """Fold unicode + whitespace so substring checks aren't defeated by formatting.

    Models love fancy punctuation — non-breaking spaces, en-dashes, narrow hyphens. NFKC
    normalization + whitespace collapse means "7 days" matches "7 days" regardless of which
    space/dash variant the model emitted.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.replace("‑", "-")  # non-breaking hyphen → hyphen
    return re.sub(r"\s+", " ", folded).strip().lower()


# --------------------------------------------------------------------------- #
# Deterministic evaluators
# --------------------------------------------------------------------------- #
def routing_accuracy(outputs: dict, reference_outputs: dict) -> dict[str, Any]:
    """1.0 if the predicted intent matches the labeled intent, else 0.0."""
    predicted = outputs.get("intent")
    expected = reference_outputs.get("intent")
    return {
        "key": "routing_accuracy",
        "score": float(predicted == expected),
        "comment": f"predicted={predicted!r} expected={expected!r}",
    }


def guardrail_action(outputs: dict, reference_outputs: dict) -> dict[str, Any]:
    """1.0 if the input guardrail took the expected action (refuse/redact/allow)."""
    predicted = outputs.get("action")
    expected = reference_outputs.get("action")
    return {
        "key": "guardrail_action",
        "score": float(predicted == expected),
        "comment": f"predicted={predicted!r} expected={expected!r}",
    }


def answer_includes_facts(outputs: dict, reference_outputs: dict) -> dict[str, Any]:
    """1.0 if the answer contains every required fact (unicode/whitespace-normalized)."""
    answer = _normalize(outputs.get("answer") or "")
    required = reference_outputs.get("must_include", [])
    missing = [fact for fact in required if _normalize(fact) not in answer]
    return {
        "key": "answer_correctness",
        "score": float(not missing),
        "comment": "all facts present" if not missing else f"missing: {missing}",
    }


# --------------------------------------------------------------------------- #
# Model-based evaluators
# --------------------------------------------------------------------------- #
def answer_grounded(outputs: dict) -> dict[str, Any]:
    """1.0 if the answer is supported by the context the system retrieved.

    Reuses the same groundedness check the live output guardrail uses (Phase 5). Skipped
    (score ``None``) when the target captured no retrieval context.
    """
    answer = outputs.get("answer") or ""
    context = outputs.get("context") or ""
    if not context.strip() or not answer.strip():
        return {"key": "groundedness", "score": None, "comment": "no context to judge"}
    try:
        verdict = check_groundedness(answer, context)
    except Exception as exc:  # noqa: BLE001 — a flaky judge call shouldn't abort the run
        return {"key": "groundedness", "score": None, "comment": f"judge error: {exc}"}
    return {
        "key": "groundedness",
        "score": float(verdict.grounded),
        "comment": verdict.reason,
    }


class _JudgeVerdict(BaseModel):
    correct: bool = Field(description="True if the answer correctly addresses the question.")
    reason: str = Field(description="One short sentence explaining the judgment.")


_JUDGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You grade a customer-support answer. Given the QUESTION and the REQUIRED "
            "FACTS a correct answer must convey, decide whether the ANSWER is correct and "
            "helpful. Mark it correct if it conveys the required facts and contradicts "
            "none of them. It need not be word-for-word. Extra accurate detail (e.g. also "
            "giving the yearly price when asked the monthly price) is fine and must NOT be "
            "penalized. Only mark incorrect if a required fact is missing or contradicted.",
        ),
        (
            "human",
            "QUESTION:\n{question}\n\nREQUIRED FACTS:\n{facts}\n\nANSWER:\n{answer}",
        ),
    ]
)


def qa_correctness_judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict[str, Any]:
    """LLM-as-judge correctness: does the answer convey the required facts? (needs Ollama)."""
    answer = outputs.get("answer") or ""
    if not answer.strip():
        return {"key": "qa_correctness_judge", "score": 0.0, "comment": "empty answer"}
    # Use the router model (llama3.2): it's a non-"thinking" model, so structured output
    # parses cleanly — the agent model (qwen3) emits <think> blocks that break the parser.
    chain = _JUDGE_PROMPT | get_router_model().with_structured_output(_JudgeVerdict)
    try:
        verdict = chain.invoke(
            {
                "question": inputs.get("message", ""),
                "facts": ", ".join(reference_outputs.get("must_include", [])),
                "answer": answer,
            }
        )
    except Exception as exc:  # noqa: BLE001 — never let a judge parse error abort the run
        return {"key": "qa_correctness_judge", "score": None, "comment": f"judge error: {exc}"}
    return {
        "key": "qa_correctness_judge",
        "score": float(verdict.correct),
        "comment": verdict.reason,
    }


# Which evaluators run for each suite (local runner + LangSmith).
SUITE_EVALUATORS = {
    "routing": [routing_accuracy],
    "guardrails": [guardrail_action],
    "qa": [answer_includes_facts, answer_grounded, qa_correctness_judge],
}
