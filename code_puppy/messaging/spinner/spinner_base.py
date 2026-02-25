"""
Base spinner implementation to be extended for different UI modes.
"""

from abc import ABC, abstractmethod
from threading import Lock

from code_puppy.config import get_puppy_name
from code_puppy.loading_messages import get_spinner_messages


class SpinnerBase(ABC):
    """Abstract base class for spinner implementations."""

    # Shared spinner frames across implementations
    FRAMES = [
        "(🐶    ) ",
        "( 🐶   ) ",
        "(  🐶  ) ",
        "(   🐶 ) ",
        "(    🐶) ",
        "(   🐶 ) ",
        "(  🐶  ) ",
        "( 🐶   ) ",
        "(🐶    ) ",
    ]
    puppy_name = get_puppy_name().title()

    # Default message when processing (kept for backward compat)
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
        # Shuffled deck of messages — each start() draws the next card.
        # No message repeats until the whole deck is exhausted.
        self._message_deck = get_spinner_messages()
        self._message_index = 0

    @abstractmethod
    def start(self):
        """Start the spinner animation.

        Each start() picks the next message from the shuffled deck.
        The message stays locked in for the entire spin cycle.
        """
        self._is_spinning = True
        self._frame_index = 0
        self._advance_message()

    @abstractmethod
    def stop(self):
        """Stop the spinner animation."""
        self._is_spinning = False

    @abstractmethod
    def update_frame(self):
        """Update to the next animation frame (puppy bounce only)."""
        if self._is_spinning:
            self._frame_index = (self._frame_index + 1) % len(self.FRAMES)

    def _advance_message(self) -> None:
        """Draw the next message from the deck, re-shuffling when exhausted."""
        self._message_index += 1
        if self._message_index >= len(self._message_deck):
            self._message_deck = get_spinner_messages()
            self._message_index = 0

    @property
    def current_thinking_message(self) -> str:
        """Get the current rotating thinking message."""
        prefix = f"{self.puppy_name} is "
        msg = self._message_deck[self._message_index]
        return f"{prefix}{msg} "

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

    @staticmethod
    def format_context_info(total_tokens: int, capacity: int, proportion: float) -> str:
        """Create a concise context summary for spinner display."""
        if capacity <= 0:
            return ""
        proportion_pct = proportion * 100
        return f"Tokens: {total_tokens:,}/{capacity:,} ({proportion_pct:.1f}% used)"
