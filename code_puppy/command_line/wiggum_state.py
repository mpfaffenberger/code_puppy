"""Wiggum loop state management.

This module tracks the state for the /wiggum command, which causes
the agent to automatically re-run the same prompt after completing,
like Chief Wiggum chasing donuts in circles. 🍩

Usage:
    /wiggum <prompt>  - Start looping with the given prompt
    Ctrl+C            - Stop the wiggum loop
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class WiggumState:
    """State container for wiggum loop mode."""

    active: bool = False
    prompt: Optional[str] = None
    loop_count: int = 0

    def start(self, prompt: str) -> None:
        """Start wiggum mode with the given prompt."""
        self.active = True
        self.prompt = prompt
        self.loop_count = 0

    def stop(self) -> None:
        """Stop wiggum mode."""
        self.active = False
        self.prompt = None
        self.loop_count = 0

    def increment(self) -> int:
        """Increment and return the loop count."""
        self.loop_count += 1
        return self.loop_count


# Global singleton for wiggum state
_wiggum_state = WiggumState()


def get_wiggum_state() -> WiggumState:
    """Get the global wiggum state."""
    return _wiggum_state


def is_wiggum_active() -> bool:
    """Check if wiggum mode is currently active."""
    return _wiggum_state.active


def get_wiggum_prompt() -> Optional[str]:
    """Get the current wiggum prompt, if active."""
    return _wiggum_state.prompt if _wiggum_state.active else None


def start_wiggum(prompt: str) -> None:
    """Start wiggum mode with the given prompt."""
    _wiggum_state.start(prompt)


def stop_wiggum() -> None:
    """Stop wiggum mode."""
    _wiggum_state.stop()


def increment_wiggum_count() -> int:
    """Increment wiggum loop count and return the new value."""
    return _wiggum_state.increment()


def get_wiggum_count() -> int:
    """Get the current wiggum loop count."""
    return _wiggum_state.loop_count
