"""
Base spinner implementation to be extended for different UI modes.
"""

from abc import ABC, abstractmethod
from threading import Lock

from code_puppy.config import get_mist_name


class SpinnerBase(ABC):
    """Abstract base class for spinner implementations."""

    # Shared spinner frames: the classic braille "dots" spinner (the de-facto
    # modern TUI indicator, and what the sub-agent panel already uses). Crisp,
    # well-supported, and visually consistent across the app — unlike the tiny
    # square glyphs, which rendered faint.
    FRAMES = [
        "⠋",
        "⠙",
        "⠹",
        "⠸",
        "⠼",
        "⠴",
        "⠦",
        "⠧",
        "⠇",
        "⠏",
    ]
    mist_name = get_mist_name()

    # Default message when processing
    THINKING_MESSAGE = f"{mist_name} is thinking... "

    # Message when waiting for user input
    WAITING_MESSAGE = f"{mist_name} is waiting... "

    # Current message - starts with thinking by default
    MESSAGE = THINKING_MESSAGE

    _context_info: str = ""
    _context_lock: Lock = Lock()

    # Current activity (e.g. "Running: npm test") shown in place of the
    # generic thinking message while a tool is executing, so a long tool
    # call reads as live progress rather than a frozen "thinking…".
    _activity: str = ""
    _activity_lock: Lock = Lock()

    def __init__(self):
        """Initialize the spinner."""
        self._is_spinning = False
        self._frame_index = 0

    @abstractmethod
    def start(self):
        """Start the spinner animation."""
        self._is_spinning = True
        self._frame_index = 0

    @abstractmethod
    def stop(self):
        """Stop the spinner animation."""
        self._is_spinning = False

    @abstractmethod
    def update_frame(self):
        """Update to the next frame."""
        if self._is_spinning:
            self._frame_index = (self._frame_index + 1) % len(self.FRAMES)

    @property
    def current_frame(self):
        """Get the current frame."""
        return self.FRAMES[self._frame_index]

    @property
    def is_spinning(self):
        """Check if the spinner is currently spinning."""
        return self._is_spinning

    @classmethod
    def set_context_info(cls, info: str) -> None:
        """Set shared context information displayed beside the spinner."""
        with cls._context_lock:
            cls._context_info = info

    @classmethod
    def clear_context_info(cls) -> None:
        """Clear any context information displayed beside the spinner."""
        cls.set_context_info("")

    @classmethod
    def get_context_info(cls) -> str:
        """Return the current spinner context information."""
        with cls._context_lock:
            return cls._context_info

    @classmethod
    def set_activity(cls, activity: str) -> None:
        """Set the current activity label shown beside the spinner."""
        with cls._activity_lock:
            cls._activity = activity or ""

    @classmethod
    def clear_activity(cls) -> None:
        """Clear the activity label, reverting to the thinking message."""
        cls.set_activity("")

    @classmethod
    def get_activity(cls) -> str:
        """Return the current activity label (empty when just thinking)."""
        with cls._activity_lock:
            return cls._activity

    @staticmethod
    def format_context_info(total_tokens: int, capacity: int, proportion: float) -> str:
        """Create a concise context summary for spinner display."""
        if capacity <= 0:
            return ""
        proportion_pct = proportion * 100
        return f"Tokens: {total_tokens:,}/{capacity:,} ({proportion_pct:.1f}% used)"
