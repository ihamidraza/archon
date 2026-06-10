"""FastAPI application factory for the Archon support service.

Wires the LangGraph pipeline into an HTTP API:

* the compiled graph is built **once** in the app lifespan with an async checkpointer, so
  every request shares one durable conversation store;
* CORS is opened to the Next.js dev origin (Phase 9);
* the streaming endpoints are rate-limited (slowapi).

Run it with ``make run`` (``uvicorn backend.app.main:app --reload``). Interactive docs are
served at ``/docs``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.api.limiter import limiter
from backend.app.api.routes import router
from backend.app.core.observability import configure_tracing
from backend.app.core.settings import settings
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_async_checkpointer


def create_app(*, checkpoint_path: str | None = None) -> FastAPI:
    """Build the FastAPI app.

    Args:
        checkpoint_path: SQLite path for conversation memory; defaults to the configured
            file. Pass ``":memory:"`` for an ephemeral store (tests).
    """
    path = checkpoint_path or str(settings.checkpoint_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_tracing()
        async with get_async_checkpointer(path) as saver:
            app.state.graph = build_support_graph(checkpointer=saver)
            yield

    app = FastAPI(
        title="Archon Support API",
        version="0.8.0",
        summary="Guarded, supervised customer-support agent over HTTP (SSE streaming).",
        lifespan=lifespan,
    )

    # Rate limiting (slowapi): share the limiter on app.state + register its 429 handler.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/")
    async def root() -> dict:
        return {"name": "Archon Support API", "docs": "/docs", "health": "/health"}

    return app


app = create_app()
