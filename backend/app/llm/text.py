"""Text post-processing for model output.

"Thinking" models (e.g. qwen3) wrap their chain-of-thought in ``<think>…</think>`` before
the real answer. We ask the factory to disable that (``reasoning=False``), but not every
Ollama model honors the flag — so we also strip the blocks defensively here. This keeps
internal reasoning out of customer-facing answers (and out of substring-based evals)
regardless of whether the model cooperated.
"""

from __future__ import annotations

import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove complete ``<think>…</think>`` blocks and any stray tags, then trim."""
    if not text:
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def visible_so_far(text: str) -> str:
    """The customer-visible prefix of a *partial* stream (for token streaming).

    Drops finished think blocks and hides an as-yet-unterminated one, without trimming the
    trailing edge — so the result grows monotonically as more tokens arrive and can be
    diffed against what's already been printed.
    """
    cleaned = _THINK_BLOCK.sub("", text)
    open_idx = cleaned.rfind("<think>")
    if open_idx != -1 and "</think>" not in cleaned[open_idx:]:
        cleaned = cleaned[:open_idx]  # still thinking — hide it until it closes
    return cleaned.lstrip()
