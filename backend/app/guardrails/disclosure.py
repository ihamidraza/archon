"""Internal-disclosure sanitizer — a deterministic net for leaked system internals.

The system prompt tells the model never to mention *how* it finds answers, but a small
local model still slips and writes things like "my knowledge base doesn't have that" or
"the retrieved documents don't mention it". Those phrases leak that there's a RAG pipeline
behind the assistant — internal plumbing a customer should never see.

This is the disclosure-side complement to the PII scrub in the output guardrail: cheap,
deterministic, explainable substitutions that rewrite the leaking *phrase* into neutral
customer-facing language instead of nuking an otherwise good answer. We keep it
conservative — only unambiguous "how I work" tells — so we don't mangle legitimate words
(a customer really can have "documents" or read "our documentation").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (compiled pattern, replacement). Order matters: more specific phrasings first so a broad
# fallback doesn't pre-empt a clean rewrite. Replacements aim for natural, neutral wording.
_RAW_SUBSTITUTIONS: list[tuple[str, str]] = [
    # "my/the/our knowledge base (doesn't|does not) (have|contain|…) ..."
    (
        r"\b(?:my|the|our)\s+knowledge\s*base\s+does(?:n['’]t| not)\s+"
        r"(?:have|contain|include|mention|cover)\b",
        "I don't have",
    ),
    (r"\b(?:my|the|our)\s+knowledge\s*base\s+has\s+no\b", "I don't have"),
    (r"\baccording to (?:my|the|our) knowledge\s*base\b", "from what I have"),
    (r"\b(?:my|the|our)\s+knowledge\s*base\b", "the information I have"),
    (r"\bknowledge\s*base\b", "available information"),
    # Retrieved-document / context tells.
    (r"\bthe (?:retrieved|provided|available|search(?:ed)?)\s+documents?\b",
     "the information I have"),
    (r"\bthe documents?\s+(?:I|we)\s+(?:have|retrieved|found|searched|was given|were given)\b",
     "the information I have"),
    (r"\b(?:the|my)\s+(?:retrieved|provided)\s+context\b", "the information I have"),
    (r"\bthe context (?:provided|I was given|i have|available)\b",
     "the information I have"),
    (r"\bbased on (?:the|my) (?:retrieved|provided|available) (?:context|documents?)\b",
     "based on the information I have"),
    (r"\b(?:the )?search results?\b", "the information I have"),
    (r"\bmy training (?:data|set)?\b", "the information I have"),
    # Bare RAG/vector jargon a customer should never see.
    (r"\bvector (?:store|database|db|search|index)\b", "system"),
    (r"\bembeddings?\b", "records"),
    (r"\bretrieval (?:system|pipeline|step)\b", "system"),
    (r"\bRAG\b", "system"),
]

_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.I), repl) for pattern, repl in _RAW_SUBSTITUTIONS
]


@dataclass(frozen=True)
class DisclosureResult:
    """Outcome of the disclosure scrub."""

    text: str
    leaked: bool

    def __bool__(self) -> bool:
        """Truthy when something was scrubbed."""
        return self.leaked


def sanitize_disclosure(text: str) -> DisclosureResult:
    """Rewrite phrases that leak internal mechanics into neutral language.

    Returns the (possibly) rewritten text and whether any leak was found, so callers can
    log/trace the event. Leaves clean answers byte-for-byte untouched.
    """
    cleaned = text
    leaked = False
    for pattern, repl in _SUBSTITUTIONS:
        cleaned, n = pattern.subn(repl, cleaned)
        if n:
            leaked = True
    # Collapse any double spaces a deletion-style replacement may have introduced.
    if leaked:
        cleaned = re.sub(r"  +", " ", cleaned).replace(" .", ".").replace(" ,", ",")
    return DisclosureResult(text=cleaned, leaked=leaked)
