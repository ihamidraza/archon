"""Output guardrail node — runs after a specialist answers, before the reply leaves.

Two safety nets:

1. **PII leak scan.** A last-line defense that redacts any high-risk secret (card/SSN/API
   key) the model might have echoed. Legitimate contact details returned by account tools
   are left intact.
2. **Groundedness gate.** Verifies the answer is supported by the context the specialist
   actually retrieved this turn (KB excerpts + tool results). The verdict drives routing:

       grounded            → end the turn
       ungrounded, retries left → bounce back to the specialist with a corrective note
       ungrounded, exhausted    → escalate to a human

The node records its verdict in ``guard_decision`` so the routing edge
(``route_after_output_guard``) stays a pure state→node function with no model calls.
Groundedness is only checked when there *is* retrieved context to judge against; an answer
with no tool evidence (e.g. a greeting) passes this gate.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.app.core.settings import settings
from backend.app.graph.state import SupportState
from backend.app.guardrails.groundedness import check_groundedness
from backend.app.guardrails.pii import contains_high_risk_pii, redact

CORRECTIVE_NOTE = (
    "[Quality check] Your previous answer may not be fully supported by the Nimbus "
    "documentation. Use your search tool again if needed and answer using ONLY the "
    "retrieved documents and tool results. If the answer isn't covered, say you don't "
    "have that information and offer to connect the customer with a human agent."
)


def _turn_context(state: SupportState) -> str:
    """Concatenate the tool outputs produced since the last user message this turn."""
    chunks: list[str] = []
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            chunks.append(str(message.content))
    return "\n\n".join(reversed(chunks))


def _final_answer(state: SupportState) -> AIMessage | None:
    last = state["messages"][-1]
    return last if isinstance(last, AIMessage) and last.content else None


def output_guard_node(state: SupportState) -> dict:
    """Scan the answer for leaks and check it's grounded; decide ok/retry/escalate."""
    answer_msg = _final_answer(state)
    if answer_msg is None:
        return {"guard_decision": "ok"}

    update: dict = {}
    answer = str(answer_msg.content)

    # 1. PII-leak scan (defense in depth): redact any high-risk secret in place.
    if contains_high_risk_pii(answer):
        redacted, _, _ = redact(answer)
        update["messages"] = [AIMessage(content=redacted, id=answer_msg.id)]
        answer = redacted

    # 2. Groundedness gate — only meaningful when we have retrieved context.
    context = _turn_context(state)
    if not context.strip():
        update["guard_decision"] = "ok"
        return update

    verdict = check_groundedness(answer, context)
    if verdict.grounded:
        update["guard_decision"] = "ok"
        return update

    retries = state.get("retry_count", 0)
    if retries < settings.max_output_retries:
        # Bounce back to the same specialist with a corrective instruction.
        update["guard_decision"] = "retry"
        update["retry_count"] = retries + 1
        update["messages"] = [*update.get("messages", []), HumanMessage(content=CORRECTIVE_NOTE)]
        return update

    update["guard_decision"] = "escalate"
    update["escalation_reason"] = f"ungrounded_answer: {verdict.reason}"
    return update


def route_after_output_guard(state: SupportState) -> str:
    """Route on the recorded verdict: end, retry the specialist, or escalate."""
    decision = state.get("guard_decision", "ok")
    if decision == "retry":
        return state["intent"]  # back to the same specialist node
    if decision == "escalate":
        return "escalate"
    return "__end__"
