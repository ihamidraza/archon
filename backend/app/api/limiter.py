"""Shared rate limiter (slowapi) for the API.

Defined in its own module so route decorators and the app factory import the *same*
``Limiter`` instance. Keyed by client IP; the per-route limit comes from settings.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.core.settings import settings

limiter = Limiter(key_func=get_remote_address)

# Limit string applied to the streaming endpoints, e.g. "30/minute".
CHAT_RATE_LIMIT = settings.api_rate_limit
