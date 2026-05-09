"""
Base spinner implementation to be extended for different UI modes.
"""

from abc import ABC, abstractmethod
from threading import Lock
from typing import List

from code_puppy.config import DEFAULT_PUPPY_EMOJI, get_puppy_emoji, get_puppy_name


def _build_spinner_frames(emoji: str) -> List[str]:
    """Build the bouncing-puppy frame list for a given emoji.

    Single source of truth so the static FRAMES backward-compat attribute and
    the live per-frame render in current_frame can't drift apart.
    """
    return [
        f"({emoji}    ) ",
        f"( {emoji}   ) ",
        f"(  {emoji}  ) ",
        f"(   {emoji} ) ",
        f"(    {emoji}) ",
        f"(   {emoji} ) ",
        f"(  {emoji}  ) ",
        f"( {emoji}   ) ",
        f"({emoji}    ) ",
    ]


class SpinnerBase(ABC):
    """Abstract base class for spinner implementations."""

    # Frozen-at-import default-emoji frames. Kept as a class attribute for
    # backward compatibility (tests and any external code that references
    # SpinnerBase.FRAMES). The actual animation pulls live frames via
    # current_frame so the user's configured puppy_emoji takes effect
    # without a restart.
    FRAMES = _build_spinner_frames(DEFAULT_PUPPY_EMOJI)
    puppy_name = get_puppy_name().title()

    # Default message when processing
    THINKING_MESSAGE = f"{puppy_name} is thinking... "

    # Message when waiting for user input
    WAITING_MESSAGE = f"{puppy_name} is waiting... "

    # Current message - starts with thinking by default
    MESSAGE = THINKING_MESSAGE

    _context_info: str = ""
    _context_lock: Lock = Lock()

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
        """Get the current frame, rendered with the user's live puppy_emoji."""
        return _build_spinner_frames(get_puppy_emoji())[self._frame_index]

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

    @staticmethod
    def format_context_info(total_tokens: int, capacity: int, proportion: float) -> str:
        """Create a concise context summary for spinner display."""
        if capacity <= 0:
            return ""
        proportion_pct = proportion * 100
        return f"Tokens: {total_tokens:,}/{capacity:,} ({proportion_pct:.1f}% used)"
