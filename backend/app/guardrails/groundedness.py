"""Groundedness checking — the main output guardrail against hallucination.

After a specialist answers, we verify the answer is actually *supported* by the context it
retrieved (knowledge-base excerpts and tool results from this turn). This is the
output-side complement to the Phase 2 grounded-answer prompt: the prompt *asks* the model
to stay grounded; this *verifies* it did, and can trigger a retry or a human handoff when
it didn't.

We use the fast model tier with **structured output** so the verdict is a validated object
(``grounded`` + ``reason``), not text to parse. The check only runs when there *is*
retrieved context to judge against; an answer produced with no tool evidence can't be
verified this way and is handled by routing/scope rules instead.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.app.llm.factory import get_router_model


class GroundednessVerdict(BaseModel):
    """Whether an answer is supported by the provided context."""

    grounded: bool = Field(
        description="True only if every factual claim in the answer is supported by the "
        "context. Generic pleasantries and offers to help count as grounded."
    )
    reason: str = Field(description="One short sentence explaining the verdict.")


_GROUNDEDNESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a strict fact-checker for a customer-support assistant. Decide "
            "whether the ANSWER is fully supported by the CONTEXT. Mark it ungrounded if "
            "it states any specific fact (a price, policy, number, account detail, or "
            "step) that is not present in the CONTEXT. Do not use outside knowledge.",
        ),
        ("human", "CONTEXT:\n{context}\n\nANSWER:\n{answer}"),
    ]
)


@lru_cache
def _checker():
    return _GROUNDEDNESS_PROMPT | get_router_model().with_structured_output(
        GroundednessVerdict
    )


def check_groundedness(answer: str, context: str) -> GroundednessVerdict:
    """Return whether ``answer`` is supported by ``context``."""
    return _checker().invoke({"answer": answer, "context": context})
