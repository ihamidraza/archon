"""Conversation memory via LangGraph's SQLite checkpointer.

A *checkpointer* snapshots graph state after every step, keyed by a ``thread_id`` you
pass at invoke time. That's what gives the agent memory: re-invoking with the same
``thread_id`` resumes the saved message history, and it's also the mechanism that makes
human-in-the-loop pauses (Phase 5) possible — the graph can stop and later resume exactly
where it left off.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.app.core.settings import settings


def get_checkpointer(db_path: str | None = None) -> SqliteSaver:
    """Return a ready-to-use SQLite checkpointer.

    Args:
        db_path: SQLite file path, or ``":memory:"`` for an ephemeral store (tests).
            Defaults to ``settings.checkpoint_path``.
    """
    path = db_path or str(settings.checkpoint_path)
    if path != ":memory:":
        settings.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the API server (Phase 8) touches the connection from
    # multiple worker threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()  # idempotent: creates checkpoint tables on first use
    return saver


@asynccontextmanager
async def get_async_checkpointer(db_path: str | None = None) -> AsyncIterator[AsyncSqliteSaver]:
    """Async checkpointer for the FastAPI service (Phase 8).

    The API runs on an event loop, so it needs the ``aiosqlite``-backed
    :class:`AsyncSqliteSaver` rather than the blocking sync saver. Used as an async context
    manager so the connection is opened for the app's lifetime and closed on shutdown::

        async with get_async_checkpointer() as saver:
            graph = build_support_graph(checkpointer=saver)

    Args:
        db_path: SQLite path, or ``":memory:"`` for an ephemeral store (tests). Defaults to
            ``settings.checkpoint_path``.
    """
    path = db_path or str(settings.checkpoint_path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        await saver.setup()
        yield saver
