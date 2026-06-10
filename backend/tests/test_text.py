"""Unit tests for reasoning-token stripping (offline)."""

from __future__ import annotations

from backend.app.llm.text import strip_reasoning, visible_so_far


def test_strip_removes_complete_think_block():
    assert strip_reasoning("<think>plan the answer</think>Hello!") == "Hello!"


def test_strip_handles_multiline_and_whitespace():
    text = "<think>\nlots of\nreasoning\n</think>\n\nThe refund window is 7 days."
    assert strip_reasoning(text) == "The refund window is 7 days."


def test_strip_passthrough_when_no_think():
    assert strip_reasoning("Just a normal answer.") == "Just a normal answer."


def test_strip_removes_stray_tags():
    assert "<think>" not in strip_reasoning("<think>oops answer")


def test_visible_so_far_hides_open_think_then_reveals_answer():
    # While the think block is open, nothing is visible yet.
    assert visible_so_far("<think>still reasoning") == ""
    # Once it closes, only the answer is visible — and it grows monotonically.
    partial = "<think>reasoning</think>Hello"
    full = "<think>reasoning</think>Hello there!"
    assert visible_so_far(partial) == "Hello"
    assert visible_so_far(full).startswith(visible_so_far(partial))
