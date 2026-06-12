"""An in-memory index of conversations paused awaiting a human agent.

The checkpointer (``backend/app/graph/memory.py``) is the durable source of truth for every
conversation's *state*; this registry is only a lightweight *liveness index* of "which
threads are paused, and for which department" so the agent consoles can list a queue without
a way to enumerate threads from the checkpointer.

Because it is just an index, it can safely be in-memory and self-healing: ``GET /agent/queue``
verifies each entry against the graph state and drops anything no longer paused, so a stale
entry is harmless. Entries are added when ``/chat`` or ``/resume`` detects a pending
interrupt and removed when a thread resolves (see ``backend/app/api/routes.py``).

CAVEAT — single process only: this dict (like :data:`pubsub` and the slowapi ``limiter``)
lives in one process. With ``uvicorn --workers >1`` each worker would see a partial queue;
the durable fix is a shared store (e.g. a SQLite table). The app runs single-process today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# The four specialist teams a customer can be routed to (mirrors the supervisor's Intent).
DEPARTMENTS = ("billing", "technical", "account", "sales")

# Bucket for escalations whose intent is missing/unrecognised — visible to every department.
GENERAL = "general"

Status = Literal["waiting", "resolved"]


def normalize_department(intent: str | None) -> str:
    """Map a routing ``intent`` to a department, falling back to :data:`GENERAL`."""
    return intent if intent in DEPARTMENTS else GENERAL


@dataclass
class EscalationEntry:
    """One paused conversation awaiting a human reply."""

    thread_id: str
    department: str
    customer_message: str
    reason: str
    created_at: datetime
    status: Status = "waiting"


class EscalationRegistry:
    """In-memory map of ``thread_id`` → :class:`EscalationEntry` (single-process)."""

    def __init__(self) -> None:
        self._entries: dict[str, EscalationEntry] = {}

    def add(
        self, *, thread_id: str, department: str, customer_message: str, reason: str
    ) -> EscalationEntry:
        """Upsert a waiting entry. Idempotent: re-escalating a thread keeps its original
        ``created_at`` so its place in the queue is stable."""
        existing = self._entries.get(thread_id)
        created_at = existing.created_at if existing else datetime.now(UTC)
        entry = EscalationEntry(
            thread_id=thread_id,
            department=department,
            customer_message=customer_message,
            reason=reason,
            created_at=created_at,
            status="waiting",
        )
        self._entries[thread_id] = entry
        return entry

    def remove(self, thread_id: str) -> None:
        """Drop a thread from the queue. No-op if it was never registered."""
        self._entries.pop(thread_id, None)

    def get(self, thread_id: str) -> EscalationEntry | None:
        return self._entries.get(thread_id)

    def list_for(self, department: str | None) -> list[EscalationEntry]:
        """Entries for ``department`` (plus :data:`GENERAL`, which every team sees), or all
        waiting entries when ``department`` is ``None``. Sorted oldest-first."""
        entries = self._entries.values()
        if department is not None:
            entries = [
                e for e in entries if e.department == department or e.department == GENERAL
            ]
        return sorted(entries, key=lambda e: e.created_at)


# Shared singleton, imported by the API routes (mirrors the slowapi ``limiter`` pattern).
registry = EscalationRegistry()
