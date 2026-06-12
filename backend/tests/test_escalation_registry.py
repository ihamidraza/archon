"""Unit tests for the escalation queue index and the live-stream pub/sub.

Both are plain in-memory primitives (no model, no I/O), so they're fully testable offline.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.app.api.escalation_registry import (
    GENERAL,
    EscalationRegistry,
    normalize_department,
)
from backend.app.api.pubsub import ThreadPubSub
from backend.app.api.schemas import TokenEvent


# --------------------------------------------------------------------------- #
# normalize_department
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("intent", ["billing", "technical", "account", "sales"])
def test_known_intents_pass_through(intent):
    assert normalize_department(intent) == intent


@pytest.mark.parametrize("intent", [None, "", "unknown", "general"])
def test_unknown_intent_falls_back_to_general(intent):
    assert normalize_department(intent) == GENERAL


# --------------------------------------------------------------------------- #
# EscalationRegistry
# --------------------------------------------------------------------------- #
def _add(reg, thread_id, department="billing", msg="hi", reason="low_confidence_routing"):
    return reg.add(thread_id=thread_id, department=department, customer_message=msg, reason=reason)


def test_add_get_remove_roundtrip():
    reg = EscalationRegistry()
    entry = _add(reg, "t1")
    assert reg.get("t1") is entry
    assert entry.status == "waiting"
    reg.remove("t1")
    assert reg.get("t1") is None


def test_remove_is_noop_when_absent():
    reg = EscalationRegistry()
    reg.remove("nope")  # must not raise


def test_add_is_idempotent_and_preserves_created_at():
    reg = EscalationRegistry()
    first = _add(reg, "t1", msg="first")
    again = _add(reg, "t1", msg="updated")
    assert again.created_at == first.created_at  # queue position is stable
    assert again.customer_message == "updated"


def test_list_for_department_includes_general():
    reg = EscalationRegistry()
    _add(reg, "b1", department="billing")
    _add(reg, "t1", department="technical")
    _add(reg, "g1", department=GENERAL)

    billing = {e.thread_id for e in reg.list_for("billing")}
    assert billing == {"b1", "g1"}  # own department + general, never technical


def test_list_for_none_returns_all_sorted_by_created_at():
    reg = EscalationRegistry()
    _add(reg, "a")
    _add(reg, "b")
    ids = [e.thread_id for e in reg.list_for(None)]
    assert ids == ["a", "b"]


# --------------------------------------------------------------------------- #
# ThreadPubSub
# --------------------------------------------------------------------------- #
def test_publish_reaches_all_subscribers():
    async def scenario():
        ps = ThreadPubSub()
        async with ps.subscribe("t1") as q1, ps.subscribe("t1") as q2:
            await ps.publish("t1", TokenEvent(content="hello"))
            a = await asyncio.wait_for(q1.get(), timeout=1)
            b = await asyncio.wait_for(q2.get(), timeout=1)
        assert a.content == b.content == "hello"

    asyncio.run(scenario())


def test_publish_with_no_subscribers_is_noop():
    async def scenario():
        ps = ThreadPubSub()
        await ps.publish("t1", TokenEvent(content="x"))  # must not raise

    asyncio.run(scenario())


def test_subscriber_is_isolated_by_thread_and_cleaned_up():
    async def scenario():
        ps = ThreadPubSub()
        async with ps.subscribe("t1") as q1:
            await ps.publish("t2", TokenEvent(content="other-thread"))
            assert q1.empty()  # publish to t2 must not leak into t1's subscriber
        assert "t1" not in ps._subs  # context exit removes the (now empty) thread entry

    asyncio.run(scenario())
