"""The four support specialists — each the *same* ReAct loop, differently equipped.

The whole point of Phase 4 is that a specialist is not a new kind of thing: it is the
Phase 3 :func:`build_react_agent` loop with (a) a domain-scoped knowledge-base search
tool, (b) whichever mock business tools fit its job, and (c) a tailored system prompt.
We capture those three differences declaratively in :class:`SpecialistSpec` and keep one
registry, :data:`SPECIALISTS`, as the single source of truth — the supervisor builds its
routing choices from the very same registry (see ``supervisor.py``), so the two can never
drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph.react_agent import build_react_agent
from backend.app.llm.prompts import specialist_system_prompt
from backend.app.tools.knowledge_base import make_kb_search_tool
from backend.app.tools.mock_account import (
    check_service_status,
    get_subscription_status,
    lookup_invoice,
)


@dataclass(frozen=True)
class SpecialistSpec:
    """A declarative description of one specialist.

    Attributes:
        key: Stable identifier and KB category (``billing``/``technical``/…). Also the
            label the supervisor classifies into and the graph node name.
        label: Human-friendly domain name.
        routing_hint: One line the supervisor uses to decide when to pick this
            specialist. Keep these mutually distinct.
        focus: What the specialist handles, injected into its system prompt.
        tools_hint: When-to-use guidance for the specialist's tools.
        extra_tools: Mock business tools beyond the domain KB search.
    """

    key: str
    label: str
    routing_hint: str
    focus: str
    tools_hint: str
    extra_tools: list[BaseTool] = field(default_factory=list)

    @property
    def tools(self) -> list[BaseTool]:
        """The specialist's full tool set: scoped KB search + its business tools."""
        return [make_kb_search_tool(self.key, self.label), *self.extra_tools]

    @property
    def system_prompt(self) -> str:
        return specialist_system_prompt(self.label, self.focus, self.tools_hint)


SPECIALISTS: dict[str, SpecialistSpec] = {
    "billing": SpecialistSpec(
        key="billing",
        label="Billing",
        routing_hint=(
            "Invoices, charges, refunds, payment methods, subscription plans and "
            "renewals, failed or disputed payments."
        ),
        focus=(
            "You handle invoices, payments, refunds, and subscription billing questions."
        ),
        tools_hint=(
            "Use search_billing_knowledge_base for billing policies and how-tos. Use "
            "lookup_invoice for a specific invoice ID and get_subscription_status for a "
            "customer's plan — ask for the invoice ID or account email if you don't have "
            "it."
        ),
        extra_tools=[lookup_invoice, get_subscription_status],
    ),
    "technical": SpecialistSpec(
        key="technical",
        label="Technical",
        routing_hint=(
            "Bugs, errors, outages, API usage, integrations, login/loading problems, "
            "'it isn't working' troubleshooting."
        ),
        focus="You handle troubleshooting, errors, API/integration help, and outages.",
        tools_hint=(
            "Use search_technical_knowledge_base for troubleshooting steps and API "
            "reference. Use check_service_status when the customer suspects an outage."
        ),
        extra_tools=[check_service_status],
    ),
    "account": SpecialistSpec(
        key="account",
        label="Account",
        routing_hint=(
            "Profile and workspace settings, passwords and security, SSO, members and "
            "permissions, account access and data."
        ),
        focus=(
            "You handle account management, security, SSO, and workspace/member settings."
        ),
        tools_hint=(
            "Use search_account_knowledge_base for account and security how-tos. Use "
            "get_subscription_status if you need to confirm the customer's plan or "
            "account state by email."
        ),
        extra_tools=[get_subscription_status],
    ),
    "sales": SpecialistSpec(
        key="sales",
        label="Sales",
        routing_hint=(
            "Pre-sale questions: pricing, plan comparisons, features, upgrades, trials, "
            "and what the product can do."
        ),
        focus="You handle pricing, plan comparisons, features, trials, and upgrades.",
        tools_hint=(
            "Use search_sales_knowledge_base for pricing, plan, and feature details. "
            "Recommend the plan that fits the customer's described needs; never invent "
            "prices."
        ),
    ),
}


def build_specialist(
    spec: SpecialistSpec,
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Compile one specialist as a ReAct subgraph named after its key.

    When nested inside the supervisor graph, specialists are compiled *without* their own
    checkpointer — the parent graph's checkpointer persists the whole conversation.
    """
    return build_react_agent(
        tools=spec.tools,
        system_prompt=spec.system_prompt,
        model=model,
        checkpointer=checkpointer,
        name=spec.key,
    )


def build_all_specialists(
    *, checkpointer: BaseCheckpointSaver | None = None
) -> dict[str, CompiledStateGraph]:
    """Compile every specialist, keyed by intent label."""
    return {
        key: build_specialist(spec, checkpointer=checkpointer)
        for key, spec in SPECIALISTS.items()
    }
