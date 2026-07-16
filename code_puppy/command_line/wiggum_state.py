"""Backward-compatible shim for the Wiggum plugin state.

Wiggum is a plugin now. This module stays only so older imports/tests don't
faceplant like a puppy on hardwood.
"""

from __future__ import annotations

from code_puppy.plugins.wiggum.state import WiggumState, get_state


def get_wiggum_state() -> WiggumState:
    """Get the global Wiggum plugin state."""
    return get_state()


def is_wiggum_active() -> bool:
    """Check if Wiggum mode is currently active."""
    return get_state().active


def get_wiggum_prompt() -> str | None:
    """Get the current Wiggum prompt, if active."""
    state = get_state()
    return state.prompt if state.active else None


def start_wiggum(prompt: str) -> None:
    """Start Wiggum mode with the given prompt."""
    get_state().start(prompt, mode="wiggum")


def stop_wiggum() -> None:
    """Stop Wiggum mode."""
    get_state().stop()


def increment_wiggum_count() -> int:
    """Increment Wiggum loop count and return the new value."""
    return get_state().increment()


def get_wiggum_count() -> int:
    """Get the current Wiggum loop count."""
    return get_state().loop_count
