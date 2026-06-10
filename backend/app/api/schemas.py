"""Request/response models for the HTTP API.

The streaming endpoints return Server-Sent Events (not JSON bodies), so the response shapes
here describe the **SSE event payloads** — each ``data:`` line is one of these serialized to
JSON with a ``type`` discriminator. Keeping them as typed models documents the wire protocol
the frontend (Phase 9) consumes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.core.settings import settings

_MAX = settings.api_max_message_chars


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    """A customer message, optionally continuing an existing conversation thread."""

    message: str = Field(min_length=1, max_length=_MAX, description="The customer's message.")
    thread_id: str | None = Field(
        default=None, description="Conversation id; omit to start a new thread."
    )


class ResumeRequest(BaseModel):
    """A human agent's reply that resumes a thread paused for escalation."""

    thread_id: str = Field(description="The thread that is paused on an interrupt.")
    message: str = Field(min_length=1, max_length=_MAX, description="The human agent's reply.")


class FeedbackRequest(BaseModel):
    """Feedback on a traced run (LangSmith)."""

    run_id: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    comment: str | None = Field(default=None, max_length=2000)
    key: str = Field(default="user_score", max_length=64)


# --------------------------------------------------------------------------- #
# SSE event payloads (each serialized as one `data:` line)
# --------------------------------------------------------------------------- #
class SessionEvent(BaseModel):
    type: Literal["session"] = "session"
    thread_id: str


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    content: str


class InterruptEvent(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    thread_id: str
    reason: str
    customer_message: str = ""


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    thread_id: str
    intent: str | None = None
    blocked: bool = False
    escalated: bool = False
    run_id: str | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    detail: str


# --------------------------------------------------------------------------- #
# Plain JSON responses
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    ollama: bool
    tracing: bool


class FeedbackResponse(BaseModel):
    recorded: bool
