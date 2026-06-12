"""The supervisor: classify each request, then route it to a specialist.

This is the heart of Phase 4. A small, fast model (`llama3.2:3b`) reads the latest
customer message and emits a **structured** decision — which specialist should handle it
and how confident it is — using ``with_structured_output`` so we get a validated Pydantic
object instead of free text to parse.

The supervisor node only *records* that decision in the graph state; a separate routing
function (``route_from_supervisor``) reads it to pick the next node. Keeping classification
and routing separate keeps each piece trivial to test: the classifier is a pure
message → :class:`Route`, and routing is pure state → node name.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.app.core.settings import settings
from backend.app.graph.agents.specialists import SPECIALISTS
from backend.app.graph.nodes.input_guard import REFUSAL_MESSAGE
from backend.app.graph.state import SupportState
from backend.app.llm.factory import get_router_model

# The valid routing labels, derived from the specialist registry so they never drift.
Intent = Literal["billing", "technical", "account", "sales"]

# Explicit "get me a human" requests. Detected deterministically so a request to escalate
# is never (mis)judged as off-topic by the scope classifier — it must always reach a human,
# not the decline path.
_HUMAN_REQUEST_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\b(?:speak|talk|chat|connect|transfer|escalate|put me through)\b[^.?!]*\b"
        r"(?:human|person|someone|agent|representative|rep|advisor|operator|staff|"
        r"live\s+\w+)\b",
        r"\b(?:human|live|real)\s+(?:agent|person|rep|representative|support|being)\b",
        r"\breal\s+(?:human|person)\b",
        r"\bconnect me\b",
    )
]

# A short affirmation — used to catch "yes" / "ok please" right after we *offer* a human.
_AFFIRMATION = re.compile(
    r"^\W*(?:yes|yep|yeah|yup|sure|ok(?:ay)?|please(?:\s+do)?|go ahead|do it|"
    r"that works|sounds good|absolutely|definitely)\b",
    re.I,
)

# How we phrase the offer ourselves; used to tell whether the prior turn proposed a human.
_OFFERED_HUMAN = re.compile(
    r"\b(?:human agent|human|a person|live agent)\b[^.?!]*\b"
    r"(?:agent|help|assist|connect|representative)\b|\bconnect you with\b",
    re.I,
)


def wants_human_handoff(text: str) -> bool:
    """True if the message is an explicit request to talk to a human agent."""
    return any(p.search(text) for p in _HUMAN_REQUEST_PATTERNS)

# The standard reply for a question that has nothing to do with Nimbus or its product.
# We *decline* these (no human handoff) so we don't burn an agent on "write me a poem".
OUT_OF_SCOPE_MESSAGE = (
    "I'm Archon, Nimbus's support assistant, so I can only help with questions about "
    "Nimbus — billing, technical issues, your account, and our plans and features. "
    "I'm not able to help with that one, but if you have a Nimbus question I'm happy to "
    "dig in."
)


class Route(BaseModel):
    """The supervisor's structured routing decision."""

    in_scope: bool = Field(
        description=(
            "True if the message is a customer-support request about Nimbus (billing, "
            "technical, account, or product/sales) OR a greeting/pleasantry/follow-up. "
            "False ONLY when the message is clearly unrelated to Nimbus or its services "
            "— e.g. general knowledge, world facts, other companies, coding help, "
            "homework, jokes, or chit-chat with no support intent."
        )
    )
    intent: Intent = Field(description="The single best specialist for this request.")
    confidence: float = Field(
        description="Confidence in the chosen specialist, from 0.0 to 1.0.",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        description="One short sentence justifying the choice (for traces/debugging)."
    )


def _routing_options() -> str:
    """Render the specialist menu the classifier chooses from."""
    return "\n".join(
        f"- {spec.key}: {spec.routing_hint}" for spec in SPECIALISTS.values()
    )


ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the routing supervisor for Nimbus, a SaaS company. First decide "
            "whether the message is in scope, then route it to the right team.\n\n"
            "Teams:\n{options}\n\n"
            "Step 1 — Scope: set in_scope=false ONLY when the message is clearly not "
            "about Nimbus or its services (general knowledge, other companies, coding "
            "help, homework, jokes, random chit-chat). Greetings, thanks, and vague "
            "support questions are in_scope=true.\n\n"
            "Step 2 — Team: pick the single best-fitting team.\n"
            "Disambiguation:\n"
            "- sales is ONLY for prospective customers choosing or buying a plan they "
            "don't yet have: pricing, plan comparisons, trials, upgrades, 'what can it "
            "do'.\n"
            "- billing covers money and existing accounts: invoices, charges, payment "
            "methods, refunds, refund/cancellation policy, renewals. Anything about a "
            "refund or a policy is billing EVEN IF it mentions a plan — the word 'plan' "
            "alone does not make it sales.\n"
            "- account: login, SSO, passwords, members/permissions, profile/workspace "
            "settings. technical: errors, outages, bugs, API/integration problems.\n\n"
            "Step 3 — Confidence: rate 0.0–1.0. If the message is in scope but vague or "
            "you are genuinely unsure which team fits, pick the closest team but give a "
            "LOW confidence (below {threshold}) so a human can take over.\n"
            "Judge only the latest customer message.",
        ),
        ("human", "I was double-charged on invoice INV-2031, can I get a refund?"),
        (
            "ai",
            "in_scope=true, intent=billing, confidence=0.95 — existing charge and refund.",
        ),
        ("human", "Does the Pro plan include SSO, and how much is it per seat?"),
        (
            "ai",
            "in_scope=true, intent=sales, confidence=0.9 — pre-sale pricing/feature "
            "comparison.",
        ),
        ("human", "What's your refund policy for monthly plans?"),
        (
            "ai",
            "in_scope=true, intent=billing, confidence=0.9 — refund policy is billing "
            "even though a plan is mentioned.",
        ),
        ("human", "Your export API keeps returning a 500 error."),
        ("ai", "in_scope=true, intent=technical, confidence=0.95 — API error."),
        ("human", "What's the capital of France?"),
        (
            "ai",
            "in_scope=false, intent=technical, confidence=0.0 — unrelated to Nimbus.",
        ),
        ("human", "{message}"),
    ]
)


@lru_cache
def _classifier():
    """Cached router model bound to the :class:`Route` schema."""
    return ROUTER_PROMPT | get_router_model().with_structured_output(Route)


def _latest_user_text(state: SupportState) -> str:
    """The most recent human message — what the supervisor classifies."""
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    # Fall back to the last message of any kind if no HumanMessage is present.
    return str(state["messages"][-1].content) if state["messages"] else ""


def _accepted_human_offer(state: SupportState) -> bool:
    """True if the user just said "yes" to an assistant offer to fetch a human agent.

    The scope classifier only sees the latest message, so a bare "yes please" looks
    off-topic. Here we use one turn of context: if our previous reply offered a human and
    the customer affirmed, that's an escalation request.
    """
    text = _latest_user_text(state)
    if not _AFFIRMATION.match(text):
        return False
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage) and message.content:
            return bool(_OFFERED_HUMAN.search(str(message.content)))
    return False


def requests_human(state: SupportState) -> bool:
    """Whether the customer is asking for a human agent (explicitly or by accepting one)."""
    return wants_human_handoff(_latest_user_text(state)) or _accepted_human_offer(state)


# Words that mark a message as a question/new request rather than a bare answer.
_QUESTION_WORD = re.compile(
    r"\?|\b(?:what|how|why|when|where|who|which|whose|whom|can|could|would|should|"
    r"do|does|did|is|are|will)\b",
    re.I,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_ID_TOKEN = re.compile(r"^[A-Za-z#]*[-#]?\d[\w-]*$")  # INV-1002, #12345, 42, ORD7…


def _looks_like_answer(text: str) -> bool:
    """Heuristic: a reply that *answers* a question (email, ID, number, name, "yes").

    Such messages carry no standalone intent — judged alone they look off-topic — so when a
    specialist is waiting on one we must not re-classify them as a brand-new request. We
    deliberately exclude anything that reads like its own question/request so a genuine
    topic switch ("how much is Pro?") is never mistaken for an answer.
    """
    t = text.strip()
    if not t or "?" in t:
        return False
    if _EMAIL.search(t) or _ID_TOKEN.match(t):
        return True
    # A short message with no question word is almost always an answer ("yes", a name…).
    return len(t.split()) <= 4 and not _QUESTION_WORD.search(t)


def _prior_specialist_message(state: SupportState) -> str | None:
    """The active specialist's last message to the customer, if the previous turn was a real
    specialist answer (not a canned decline/refuse). ``None`` otherwise."""
    if state.get("intent") not in SPECIALISTS:
        return None
    saw_current_turn = False
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            if not saw_current_turn:
                saw_current_turn = True  # skip the message we're routing now
                continue
            return None  # reached the prior customer message with no specialist reply
        if isinstance(message, AIMessage) and message.content:
            content = str(message.content).strip()
            if content in (OUT_OF_SCOPE_MESSAGE, REFUSAL_MESSAGE):
                return None
            return content
    return None


def _active_specialist_awaiting_reply(state: SupportState) -> str | None:
    """The specialist whose thread the current message continues, if any.

    We're mid-thread with a specialist when the previous turn was that specialist's answer
    and the new customer message is a follow-up — either the specialist *asked something*
    (a ``?`` anywhere in its message, not just at the end) or the customer's reply is plainly
    an *answer* (an email, an ID, "yes"). Both mean: don't re-classify, keep the thread.
    """
    prior = _prior_specialist_message(state)
    if prior is None:
        return None
    if "?" in prior or _looks_like_answer(_latest_user_text(state)):
        return state["intent"]
    return None


def classify(text: str) -> Route:
    """Classify a single message into a :class:`Route` (pure; easy to unit-test live)."""
    return _classifier().invoke(
        {
            "message": text,
            "options": _routing_options(),
            "threshold": settings.router_confidence_threshold,
        }
    )


def supervisor_node(state: SupportState) -> dict:
    """Classify the latest message and write the decision into state.

    A direct request for a human short-circuits classification entirely: we don't ask the
    scope classifier (which, seeing only "connect me with an agent", would call it
    off-topic) — we flag it for the escalation path.
    """
    if requests_human(state):
        return {
            "in_scope": True,
            "escalation_requested": True,
            "escalation_reason": "customer_requested_human",
        }

    text = _latest_user_text(state)
    route = classify(text)

    # Conversation continuity: if a specialist just asked the customer a question, their
    # reply belongs to THAT specialist — even if, judged alone, it looks off-topic (a bare
    # email, an invoice ID, "yes"). Keep the thread with the active specialist unless the
    # customer clearly opens a different, in-scope topic in a non-answer-shaped message.
    active = _active_specialist_awaiting_reply(state)
    if active:
        clear_topic_switch = (
            route.in_scope
            and route.confidence >= settings.router_confidence_threshold
            and route.intent != active
            and not _looks_like_answer(text)
        )
        if not clear_topic_switch:
            return {
                "intent": active,
                "confidence": 1.0,
                "in_scope": True,
                "escalation_requested": False,
            }

    return {
        "intent": route.intent,
        "confidence": route.confidence,
        "in_scope": route.in_scope,
        "escalation_requested": False,
    }


def decline_node(state: SupportState) -> dict:
    """Return the standard reply for an out-of-scope (non-Nimbus) request."""
    return {"messages": [AIMessage(content=OUT_OF_SCOPE_MESSAGE)]}


def route_from_supervisor(state: SupportState) -> str:
    """Pick the next node from the supervisor's decision.

    Precedence:

    1. **Human requested** → ``escalate``. The customer explicitly asked for a person (or
       accepted our offer of one); this beats everything, so such a request can never be
       declined as off-topic.
    2. **Out of scope** → ``decline``. The message has nothing to do with Nimbus, so we
       answer with a standard canned reply instead of spending a human agent on it.
    3. **Low confidence** (but in scope) → ``escalate``. A genuine Nimbus question we
       can't confidently route gets a human-in-the-loop handoff.
    4. Otherwise → the chosen specialist node, whose name equals the intent label.
    """
    if state.get("escalation_requested"):
        return "escalate"
    if not state.get("in_scope", True):
        return "decline"
    if state.get("confidence", 0.0) < settings.router_confidence_threshold:
        return "escalate"
    return state["intent"]
