"""
Base spinner implementation to be extended for different UI modes.
"""

from abc import ABC, abstractmethod

from code_puppy.config import get_puppy_name


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

    # Default message when processing
    THINKING_MESSAGE = f"{puppy_name} is thinking... "

    # Message when waiting for user input
    WAITING_MESSAGE = f"{puppy_name} is waiting... "

    # Current message - starts with thinking by default
    MESSAGE = THINKING_MESSAGE

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
