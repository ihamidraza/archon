"""Input guardrail node — runs before anything else in the graph.

Two checks on the latest customer message, in order of severity:

1. **Prompt-injection / jailbreak** (deterministic heuristics). If flagged, we *refuse*:
   the message never reaches a specialist, and a safe canned reply is returned. We don't
   escalate attacks to a human.
2. **High-risk PII redaction.** Credit cards, SSNs, API keys, etc. are stripped from the
   message *in place* before any model sees it; the original values are kept in
   ``pii_map`` for a potential human handoff. Contact details (email/phone) are detected
   but passed through so account lookups still work.

The node mutates the conversation by **overwriting** the user message with its redacted
form, using the same message id so LangGraph's ``add_messages`` reducer replaces rather
than appends.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from backend.app.graph.state import SupportState
from backend.app.guardrails.injection import detect_injection
from backend.app.guardrails.pii import redact

REFUSAL_MESSAGE = (
    "I'm sorry, but I can't help with that request. I'm Archon, Nimbus's support "
    "assistant — I can help with billing, technical, account, and product questions. "
    "What can I help you with?"
)


def _latest_human(state: SupportState) -> HumanMessage | None:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message
    return None


def input_guard_node(state: SupportState) -> dict:
    """Screen and sanitize the latest user message."""
    message = _latest_human(state)
    if message is None:
        return {}

    text = str(message.content)

    injection = detect_injection(text)
    if injection.flagged:
        return {
            "blocked": True,
            "block_reason": f"prompt_injection:{','.join(injection.categories)}",
        }

    redacted_text, token_map, _ = redact(text)
    # Reset per-turn guardrail signals so a previous turn's retry/escalation can't leak in.
    update: dict = {
        "blocked": False,
        "retry_count": 0,
        "guard_decision": "ok",
        "escalation_reason": "",
    }
    if redacted_text != text:
        # Overwrite the message in place (same id ⇒ reducer replaces it) so no model ever
        # sees the raw secret, and record what we removed for a human agent.
        update["messages"] = [HumanMessage(content=redacted_text, id=message.id)]
        update["pii_map"] = token_map
    return update


def refuse_node(state: SupportState) -> dict:
    """Return the safe canned reply for a blocked (injection/abuse) message."""
    return {"messages": [AIMessage(content=REFUSAL_MESSAGE)]}


def route_after_input_guard(state: SupportState) -> str:
    """Refuse blocked input; otherwise continue to the supervisor."""
    return "refuse" if state.get("blocked") else "supervisor"
