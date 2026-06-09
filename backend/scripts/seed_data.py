"""Generate the synthetic knowledge base for *Nimbus*, a fictional SaaS company.

The content is hand-authored (not LLM-generated) so it is deterministic, coherent,
and safe to assert against in tests. Each document is tagged with a ``category`` that
maps to a support specialist (billing / technical / account / sales / general), which
later lets each specialist filter retrieval to its own domain.

Run it:  uv run python -m backend.scripts.seed_data   (or it runs automatically as
part of `make ingest`).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.settings import settings

# Categories that line up with the Phase 4 routing specialists.
CATEGORIES = ("billing", "technical", "account", "sales", "general")


@dataclass(frozen=True)
class KBDoc:
    filename: str
    category: str
    title: str
    body: str

    @property
    def markdown(self) -> str:
        return f"# {self.title}\n\n{self.body.strip()}\n"


KNOWLEDGE_BASE: list[KBDoc] = [
    # ---------------------------------------------------------------- billing
    KBDoc(
        "billing-subscriptions.md",
        "billing",
        "Subscriptions & Invoices",
        """
Nimbus subscriptions are billed monthly or annually to the payment method on file.
Your billing cycle starts on the day you upgrade to a paid plan.

## Viewing invoices
All invoices are available under **Settings → Billing → Invoices**. Each invoice can be
downloaded as a PDF and includes your VAT/tax ID if one is set on the account.

## Updating your payment method
Go to **Settings → Billing → Payment method** to add or replace a card. Nimbus accepts
all major credit and debit cards. The new card is charged on your next cycle.

## Failed payments
If a charge fails, Nimbus retries automatically after 3 and 7 days. After 14 days of
non-payment the workspace is downgraded to the Free plan; your data is preserved for
60 days. Update your card and click **Retry payment** to restore service immediately.
""",
    ),
    KBDoc(
        "billing-refunds.md",
        "billing",
        "Refunds & Duplicate Charges",
        """
## Refund policy
Monthly plans are refundable within 7 days of a charge. Annual plans are refundable on a
pro-rated basis within 30 days of purchase. Refunds are issued to the original payment
method and take 5–10 business days to appear.

## Duplicate or double charges
If you were charged twice in the same billing cycle, one charge is almost always a
temporary card authorization that drops off within 5 business days. If two *settled*
charges remain after 5 days, contact support with both transaction IDs and we will refund
the duplicate.

## Requesting a refund
Email billing@nimbus.example or use the in-app chat. Include the invoice number. Refund
requests are reviewed within one business day.
""",
    ),
    # -------------------------------------------------------------- technical
    KBDoc(
        "technical-troubleshooting.md",
        "technical",
        "Troubleshooting Common Issues",
        """
## Resetting your password
Click **Forgot password** on the login page and enter your account email. You will
receive a reset link valid for 60 minutes. If the email does not arrive, check your spam
folder and confirm you are using the address you signed up with.

## Two-factor authentication (2FA)
Enable 2FA under **Settings → Security**. Scan the QR code with an authenticator app
(Google Authenticator, 1Password, Authy). Store your backup codes safely — if you lose
your device, a backup code is the only way to sign in without contacting support.

## "500 Internal Server Error" on export
A 500 error when exporting usually means the export exceeded the size limit. Exports are
capped at 100,000 rows on the Starter plan and 1,000,000 rows on Pro. Narrow your date
range or filter the dataset, then retry. If the error persists on a small export, it is a
service issue — check status.nimbus.example.

## Dashboards not loading
Hard-refresh the page (Cmd/Ctrl+Shift+R). If a dashboard still fails to load, it may
reference a deleted data source; open it in edit mode to reconnect the source.
""",
    ),
    KBDoc(
        "technical-api-reference.md",
        "technical",
        "API Reference & Rate Limits",
        """
The Nimbus REST API lets you read data and manage resources programmatically.

## Authentication
All requests require a bearer token: `Authorization: Bearer <API_KEY>`. Create API keys
under **Settings → Developer → API keys**. Keys inherit the permissions of the workspace
role that created them.

## Base URL & versioning
The base URL is `https://api.nimbus.example/v1`. Breaking changes ship under a new version
prefix; the previous version is supported for 12 months.

## Rate limits
- Starter plan: 60 requests/minute
- Pro plan: 600 requests/minute
Exceeding the limit returns HTTP 429 with a `Retry-After` header. Implement exponential
backoff and honor `Retry-After`.

## Common endpoints
- `GET /v1/datasets` — list datasets
- `POST /v1/queries` — run a query
- `GET /v1/exports/{id}` — check export status
""",
    ),
    # ---------------------------------------------------------------- account
    KBDoc(
        "account-management.md",
        "account",
        "Account & Team Management",
        """
## Updating your profile
Change your name, email, and notification preferences under **Settings → Profile**.
Changing your email sends a confirmation link to the new address; the change takes effect
once confirmed.

## Inviting teammates
Workspace admins can invite members under **Settings → Members → Invite**. Each invite
consumes one seat. Roles are **Admin**, **Editor**, and **Viewer**.

## Seats and roles
- **Admin** — full access, including billing and member management.
- **Editor** — can create and edit dashboards and datasets.
- **Viewer** — read-only access to shared dashboards.
Removing a member frees their seat immediately; you are not charged for empty seats.

## Closing an account
To delete a workspace, an admin goes to **Settings → Workspace → Delete workspace**. This
is irreversible and purges all data after a 30-day grace period.
""",
    ),
    KBDoc(
        "account-security-sso.md",
        "account",
        "Security & Single Sign-On (SSO)",
        """
## Single Sign-On
SSO via SAML 2.0 and Google Workspace is available on the Enterprise plan. Admins
configure SSO under **Settings → Security → SSO**. Once enforced, members sign in through
your identity provider and local passwords are disabled.

## Session management
Active sessions are listed under **Settings → Security → Sessions**. You can revoke any
session remotely. Sessions expire after 30 days of inactivity.

## Data protection
Nimbus encrypts data in transit (TLS 1.2+) and at rest (AES-256). Audit logs of admin
actions are available to Enterprise workspaces under **Settings → Security → Audit log**.
""",
    ),
    # ------------------------------------------------------------------ sales
    KBDoc(
        "sales-pricing-plans.md",
        "sales",
        "Pricing & Plans",
        """
Nimbus offers four plans. Prices are per workspace, billed in USD.

## Plans
- **Free** — 1 editor, 3 dashboards, 100k-row exports. $0.
- **Starter** — $29/month (or $290/year). 5 editors, unlimited dashboards, 60 API req/min.
- **Pro** — $99/month (or $990/year). 20 editors, 1M-row exports, 600 API req/min.
- **Enterprise** — custom pricing. SSO, audit logs, SLA, dedicated support.

## Discounts
Annual billing saves roughly two months versus monthly. Registered nonprofits and
accredited educational institutions receive 50% off Starter and Pro. Contact
sales@nimbus.example to apply.

## Upgrading or downgrading
Change plans anytime under **Settings → Billing → Plan**. Upgrades are prorated and take
effect immediately; downgrades take effect at the end of the current cycle.
""",
    ),
    KBDoc(
        "sales-features-overview.md",
        "sales",
        "Product Features Overview",
        """
Nimbus is a cloud analytics platform for teams that want dashboards without managing
infrastructure.

## What you can do
- Connect data sources (Postgres, MySQL, CSV upload, and the REST API).
- Build interactive dashboards with charts, filters, and scheduled refreshes.
- Share dashboards publicly or with specific members.
- Export results to CSV or via the API.

## Why teams choose Nimbus
- No setup: connect a source and build a dashboard in minutes.
- Collaboration: comments, shared folders, and role-based access.
- Scales from a free hobby project to an Enterprise deployment with SSO and SLAs.

## Trials
Every paid plan includes a 14-day free trial with no card required. Trials include full
Pro features so you can evaluate the product end to end.
""",
    ),
    # ---------------------------------------------------------------- general
    KBDoc(
        "general-faq.md",
        "general",
        "Frequently Asked Questions",
        """
## What is Nimbus?
Nimbus is a cloud analytics platform for building and sharing dashboards from your data.

## Which browsers are supported?
The latest two versions of Chrome, Firefox, Safari, and Edge.

## Where can I check service status?
Live status and incident history are at status.nimbus.example.

## How do I contact a human?
Use the in-app chat or email support@nimbus.example. Enterprise customers have a dedicated
support channel with an SLA. If the AI assistant cannot resolve your issue, ask to be
escalated to a human agent.

## Where is my data stored?
Data is hosted in the region you choose at signup (US or EU) and never leaves that region.
""",
    ),
]


def seed(*, force: bool = False) -> list[str]:
    """Write the knowledge-base markdown files to ``settings.kb_path``.

    Args:
        force: Overwrite existing files. When ``False`` (default) existing files are
            left untouched, so the seed step is safe to run repeatedly.

    Returns:
        The list of file paths written (or that already existed).
    """
    kb_dir = settings.kb_path
    kb_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for doc in KNOWLEDGE_BASE:
        path = kb_dir / doc.filename
        if force or not path.exists():
            path.write_text(doc.markdown, encoding="utf-8")
        written.append(str(path))
    return written


if __name__ == "__main__":
    paths = seed(force=True)
    print(f"Seeded {len(paths)} knowledge-base documents into {settings.kb_path}:")
    for p in paths:
        print(f"  - {p}")
