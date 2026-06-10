"""Prompt-injection and jailbreak detection — the second input guardrail.

A support bot is a prime target for "ignore your instructions and …" attacks. We catch the
common cases with fast, deterministic **heuristics** (no model call): phrases that try to
override the system prompt, extract it, or switch the assistant into an unrestricted
persona. Heuristics are cheap, explainable, and easy to unit-test; the trade-off is they
only catch known patterns, which is why injection routes to a *refusal* (not a human) and
the model still operates under a hardened system prompt as a second layer.

(A model-based classifier on the fast tier could be layered on top for novel attacks; we
keep the deterministic layer here so the guardrail is testable offline and adds no
latency.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns that strongly suggest an attempt to override or exfiltrate instructions, or to
# jailbreak the assistant into ignoring its policies. Kept readable and conservative to
# avoid flagging legitimate support questions.
_RAW_PATTERNS: list[tuple[str, str]] = [
    ("override", r"\bignore\s+(?:all |the |your )?(?:previous|prior|above)\b"),
    ("override", r"\bdisregard\b.*\b(?:previous|prior|above|instructions)\b"),
    ("override", r"\bforget\s+(?:everything|all|your)\b.*\b(?:instruction|rule|prompt)"),
    ("exfiltrate", r"\b(?:reveal|show|repeat|print|tell me)\b.*\bsystem prompt\b"),
    ("exfiltrate", r"\b(?:reveal|show|repeat|tell me)\b.*\byour (?:instructions|prompt)\b"),
    ("exfiltrate", r"\bwhat (?:are|were) your (?:original )?(?:instructions|system prompt)\b"),
    ("jailbreak", r"\b(?:developer|dev|debug|god)\s+mode\b"),
    ("jailbreak", r"\bDAN\b|\bdo anything now\b"),
    ("jailbreak", r"\byou are (?:now )?(?:an? )?(?:unrestricted|unfiltered|jailbroken)\b"),
    ("role_override", r"\b(?:pretend|act as if|from now on)\b.*\bno (?:rules|restrictions)\b"),
]

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (category, re.compile(pattern, re.I)) for category, pattern in _RAW_PATTERNS
]


@dataclass(frozen=True)
class InjectionResult:
    """Outcome of the injection scan."""

    flagged: bool
    categories: list[str]
    matched: list[str]

    def __bool__(self) -> bool:
        return self.flagged


def detect_injection(text: str) -> InjectionResult:
    """Scan ``text`` for prompt-injection / jailbreak attempts."""
    categories: list[str] = []
    matched: list[str] = []
    for category, pattern in _INJECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            if category not in categories:
                categories.append(category)
            matched.append(m.group(0))
    return InjectionResult(flagged=bool(matched), categories=categories, matched=matched)
