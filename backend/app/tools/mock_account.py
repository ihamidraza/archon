"""Mock business-system tools (subscriptions, invoices, service status).

In a real deployment these would call billing/CRM/status APIs. Here they return
deterministic canned data so the agent can demonstrate tool-calling end to end without
external dependencies or cost. The data is intentionally tiny and obvious so tests and
demos are predictable.
"""

from __future__ import annotations

from langchain_core.tools import tool

# --- tiny fake datastores -------------------------------------------------- #
_SUBSCRIPTIONS = {
    "sam@example.com": {"plan": "Pro", "status": "active", "renews": "2026-07-01"},
    "alex@example.com": {"plan": "Starter", "status": "past_due", "renews": "2026-06-15"},
}

_INVOICES = {
    "INV-1001": {"amount": "$99.00", "status": "paid", "date": "2026-06-01"},
    "INV-1002": {"amount": "$99.00", "status": "refunded", "date": "2026-05-01"},
}


@tool
def get_subscription_status(email: str) -> str:
    """Look up a customer's current plan and subscription status by account email.

    Args:
        email: The customer's account email address.
    """
    sub = _SUBSCRIPTIONS.get(email.strip().lower())
    if not sub:
        return f"No subscription found for {email}. Confirm the account email."
    return (
        f"Account {email}: {sub['plan']} plan, status '{sub['status']}', "
        f"renews {sub['renews']}."
    )


@tool
def lookup_invoice(invoice_id: str) -> str:
    """Look up the amount, status, and date of an invoice by its ID (e.g. INV-1001).

    Args:
        invoice_id: The invoice identifier.
    """
    inv = _INVOICES.get(invoice_id.strip().upper())
    if not inv:
        return f"No invoice found with ID {invoice_id}."
    return f"Invoice {invoice_id}: {inv['amount']}, status '{inv['status']}', dated {inv['date']}."


@tool
def check_service_status() -> str:
    """Check whether Nimbus services are currently operational. Takes no arguments."""
    return "All Nimbus services are operational. No active incidents."
