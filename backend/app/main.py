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

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.api.limiter import limiter
from backend.app.api.routes import router
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.observability import configure_tracing
from backend.app.core.settings import settings
from backend.app.graph.build import build_support_graph
from backend.app.graph.memory import get_async_checkpointer

logger = get_logger("archon.api")


class AccessLogMiddleware:
    """Pure-ASGI access logger (method · path · status · duration).

    Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` on purpose: that base class
    consumes the response body before re-emitting it, which **buffers SSE streams** (tokens
    arrive all at once instead of incrementally). Here we only wrap ``send`` to capture the
    status code, so streamed chunks pass straight through to the client untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "request method=%s path=%s status=%s dur_ms=%.1f",
                scope.get("method"),
                scope.get("path"),
                status_code,
                elapsed_ms,
            )


def create_app(*, checkpoint_path: str | None = None) -> FastAPI:
    """Build the FastAPI app.

    Args:
        checkpoint_path: SQLite path for conversation memory; defaults to the configured
            file. Pass ``":memory:"`` for an ephemeral store (tests).
    """
    path = checkpoint_path or str(settings.checkpoint_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        traced = configure_tracing()
        logger.info("startup tracing=%s checkpoint=%s", traced, path)
        async with get_async_checkpointer(path) as saver:
            app.state.graph = build_support_graph(checkpointer=saver)
            yield
        logger.info("shutdown")

    app = FastAPI(
        title="Archon Support API",
        version="0.8.0",
        summary="Guarded, supervised customer-support agent over HTTP (SSE streaming).",
        lifespan=lifespan,
    )

    # Rate limiting (slowapi): share the limiter on app.state + register its 429 handler.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Last-resort handler for non-HTTP errors: log with traceback, return clean JSON.
        logger.exception("unhandled error path=%s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    # Access logging (inner) wrapped by CORS (outer). Both are pure ASGI, so SSE streams
    # pass through chunk-by-chunk without buffering.
    app.add_middleware(AccessLogMiddleware)
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
