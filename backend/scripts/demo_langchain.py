"""Phase 1 demo — LangChain fundamentals against local Ollama models.

Run it:  uv run python -m backend.scripts.demo_langchain

It walks through the three building blocks every later phase relies on:
  1. LCEL chains          prompt | model | parser
  2. Structured output    model.with_structured_output(PydanticSchema)
  3. Streaming            model.stream(...) token-by-token

Nothing here is wired into the agent yet — it's a guided tour of the primitives.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.app.llm.factory import get_agent_model, get_router_model
from backend.app.llm.prompts import SUPPORT_SYSTEM_PROMPT

RULE = "=" * 70


# --------------------------------------------------------------------------- #
# 1. LCEL: prompt | model | parser
# --------------------------------------------------------------------------- #
def demo_lcel_chain() -> None:
    """Compose a prompt, a model, and an output parser with the ``|`` operator.

    LCEL (LangChain Expression Language) pipes the output of each runnable into
    the next. ``StrOutputParser`` pulls the plain text out of the chat message so
    the chain returns a ``str`` instead of an ``AIMessage``.
    """
    print(RULE, "\n1) LCEL chain:  prompt | model | StrOutputParser\n")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SUPPORT_SYSTEM_PROMPT),
            ("human", "A customer writes: {question}\nReply in one short paragraph."),
        ]
    )
    chain = prompt | get_agent_model() | StrOutputParser()

    answer = chain.invoke({"question": "How do I reset my password?"})
    print(answer.strip())


# --------------------------------------------------------------------------- #
# 2. Structured output: model.with_structured_output(schema)
# --------------------------------------------------------------------------- #
class IntentClassification(BaseModel):
    """Typed result the model must return — a preview of the Phase 4 router."""

    intent: Literal["billing", "technical", "account", "sales"] = Field(
        description="Which support team should handle this message."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="How confident you are, from 0 to 1."
    )
    reasoning: str = Field(description="One short sentence explaining the choice.")


def demo_structured_output() -> None:
    """Force the model to return a validated Pydantic object instead of free text.

    ``with_structured_output`` asks Ollama to emit JSON matching the schema, then
    LangChain parses + validates it into the Pydantic model. This is what makes
    routing reliable: we get a typed ``intent`` we can branch on, never prose.
    """
    print("\n" + RULE, "\n2) Structured output:  with_structured_output(IntentClassification)\n")

    classifier = get_router_model().with_structured_output(IntentClassification)

    samples = [
        "I was charged twice for my subscription this month.",
        "The export button throws a 500 error every time I click it.",
        "Do you offer a discount for annual enterprise plans?",
    ]
    for text in samples:
        result = classifier.invoke(f"Classify this support message:\n{text}")
        print(f"• {text}")
        print(f"    -> intent={result.intent}  confidence={result.confidence:.2f}")
        print(f"       reason: {result.reasoning}\n")


# --------------------------------------------------------------------------- #
# 3. Streaming
# --------------------------------------------------------------------------- #
def demo_streaming() -> None:
    """Stream tokens as they are generated — the basis for the chat UI later."""
    print(RULE, "\n3) Streaming tokens\n")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SUPPORT_SYSTEM_PROMPT),
            ("human", "{question}"),
        ]
    )
    chain = prompt | get_agent_model() | StrOutputParser()

    for chunk in chain.stream({"question": "In one sentence, what is two-factor authentication?"}):
        print(chunk, end="", flush=True)
    print("\n")


def main() -> None:
    demo_lcel_chain()
    demo_structured_output()
    demo_streaming()
    print(RULE, "\nDone. See docs/01-langchain-basics.md for the walkthrough.")


if __name__ == "__main__":
    main()
