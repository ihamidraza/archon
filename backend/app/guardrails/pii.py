"""PII detection and redaction — the first input guardrail.

**Why regex-first?** Microsoft Presidio (in our deps) is the production-grade choice, but
its analyzer needs a spaCy NLP model (~hundreds of MB) that isn't installed by default,
and it blocks on first init. To keep Archon zero-setup and deterministic, we ship a fast
**regex engine** as the default and treat Presidio as an *optional upgrade* (enabled via
``settings`` once a spaCy model is installed). Tests assert against the regex engine, so
they're hermetic and offline.

**What we redact, and what we don't.** A support agent legitimately needs some identifiers
(an email/phone to look up an account), so blanket-redacting everything would break the
billing/account flows. We therefore split detection into two buckets:

* :data:`REDACT_TYPES` — high-risk secrets the agent must *never* need or echo (credit
  cards, SSNs, IBANs, API keys/passwords). These are stripped before the message reaches
  any model and re-scanned on the way out (defense in depth).
* the rest (email, phone, IP) — *detected and logged* but passed through so account
  lookups still work.

The redaction is reversible: :func:`redact` returns a token→original mapping so a human
agent (Phase 5 escalation) could see the real values if needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Recognizers (entity type -> compiled pattern)
# --------------------------------------------------------------------------- #
_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){12,15}\d\b"),
    "API_KEY": re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test)?[-_]?[A-Za-z0-9]{12,}\b"),
    "PHONE": re.compile(
        r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"
    ),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

# High-risk entities that are stripped before any model sees them.
REDACT_TYPES: frozenset[str] = frozenset({"CREDIT_CARD", "SSN", "IBAN", "API_KEY"})


@dataclass(frozen=True)
class PiiSpan:
    """One detected PII occurrence."""

    entity_type: str
    text: str
    start: int
    end: int


def _luhn_ok(digits: str) -> bool:
    """Validate a candidate card number with the Luhn checksum (cuts false positives)."""
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 16:
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def detect(text: str) -> list[PiiSpan]:
    """Find all PII spans in ``text``, ordered by position.

    Overlapping matches are resolved by preferring the earliest, then the longest, so a
    16-digit card isn't also reported as a phone number.
    """
    spans: list[PiiSpan] = []
    for entity_type, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            if entity_type == "CREDIT_CARD" and not _luhn_ok(m.group()):
                continue
            spans.append(PiiSpan(entity_type, m.group(), m.start(), m.end()))

    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    # Drop spans that overlap an already-accepted (earlier/longer) span.
    accepted: list[PiiSpan] = []
    covered_until = -1
    for span in spans:
        if span.start >= covered_until:
            accepted.append(span)
            covered_until = span.end
    return accepted


def redact(
    text: str, *, types: frozenset[str] = REDACT_TYPES
) -> tuple[str, dict[str, str], list[PiiSpan]]:
    """Replace high-risk PII in ``text`` with stable tokens.

    Args:
        text: The raw input.
        types: Which entity types to actually redact (others are detected only).

    Returns:
        ``(redacted_text, token_map, all_detected_spans)`` where ``token_map`` maps each
        placeholder like ``<CREDIT_CARD_1>`` back to the original value.
    """
    detected = detect(text)
    token_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0

    for span in detected:
        if span.entity_type not in types:
            continue
        counters[span.entity_type] = counters.get(span.entity_type, 0) + 1
        token = f"<{span.entity_type}_{counters[span.entity_type]}>"
        token_map[token] = span.text
        pieces.append(text[cursor : span.start])
        pieces.append(token)
        cursor = span.end

    pieces.append(text[cursor:])
    return "".join(pieces), token_map, detected


def contains_high_risk_pii(text: str) -> bool:
    """True if ``text`` contains any entity in :data:`REDACT_TYPES` (output-leak scan)."""
    return any(span.entity_type in REDACT_TYPES for span in detect(text))
