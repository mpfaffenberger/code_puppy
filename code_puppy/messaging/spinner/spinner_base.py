"""
Base spinner implementation to be extended for different UI modes.
"""

from abc import ABC, abstractmethod
from threading import Lock

from code_puppy.config import get_mist_name


class SpinnerBase(ABC):
    """Abstract base class for spinner implementations."""

    # Selectable braille spinner presets (crisp, well-supported). The 3–4 cell
    # ones read with more presence than a single glyph. Pick one with
    # ``/set spinner_style=<name>``; defaults to "sparkle".
    # Frames adapted from github.com/Eronred/expo-agent-spinners.
    SPINNER_PRESETS: dict = {
        "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "sparkle": ["⡡⠊⢔⠡", "⠊⡰⡡⡘", "⢔⢅⠈⢢", "⡁⢂⠆⡍", "⢔⠨⢑⢐", "⠨⡑⡠⠊"],
        "wave": [
            "⠁⠂⠄⡀",
            "⠂⠄⡀⢀",
            "⠄⡀⢀⠠",
            "⡀⢀⠠⠐",
            "⢀⠠⠐⠈",
            "⠠⠐⠈⠁",
            "⠐⠈⠁⠂",
            "⠈⠁⠂⠄",
        ],
        "pulse": ["⠀⠶⠀", "⠰⣿⠆", "⢾⣉⡷", "⣏⠀⣹", "⡁⠀⢈"],
        # A circular light filling and emptying — a calm "agent is alive"
        # heartbeat (well-supported geometric circles, render crisply).
        "breathe": ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"],
        "heart": ["♡", "♥", "❤", "♥"],
        "snake": [
            "⣁⡀",
            "⣉⠀",
            "⡉⠁",
            "⠉⠉",
            "⠈⠙",
            "⠀⠛",
            "⠐⠚",
            "⠒⠒",
            "⠖⠂",
            "⠶⠀",
            "⠦⠄",
            "⠤⠤",
            "⠠⢤",
            "⠀⣤",
            "⢀⣠",
            "⣀⣀",
        ],
        "bounce": ["⠁", "⠂", "⠄", "⡀", "⠄", "⠂"],
    }
    _DEFAULT_SPINNER = "sparkle"

    # Back-compat alias; the live frames are resolved per-spinner from config.
    FRAMES = SPINNER_PRESETS[_DEFAULT_SPINNER]
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

    # When ``compact_steps`` is on, the spinner delegates its "current step"
    # to the StepLedger so the same live region also shows the rolling
    # list of completed rows. The flag is class-level so toggling config
    # doesn't require per-instance plumbing.
    _ledger_active: bool = False
    _ledger_active_lock: Lock = Lock()

    def __init__(self):
        """Initialize the spinner."""
        self._is_spinning = False
        self._frame_index = 0
        # Resolve frames once per spinner (a new spinner is created each agent
        # turn), so /set spinner_style takes effect on the next turn without a
        # config read on every animation frame.
        self._frames = type(self).get_frames()

    @classmethod
    def get_frames(cls) -> list:
        """Return the configured spinner frames (falls back to the default)."""
        try:
            from code_puppy.config import get_value

            style = str(get_value("spinner_style") or cls._DEFAULT_SPINNER)
            style = style.strip().lower()
        except Exception:
            style = cls._DEFAULT_SPINNER
        return cls.SPINNER_PRESETS.get(style, cls.SPINNER_PRESETS[cls._DEFAULT_SPINNER])

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
            self._frame_index = (self._frame_index + 1) % len(self._frames)

    @property
    def current_frame(self):
        """Get the current frame."""
        return self._frames[self._frame_index % len(self._frames)]

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

    # The current task list, rendered into the live footer so repeated
    # update_task_list calls update *in place* instead of stacking copies in
    # scrollback (each emit_info copy was the bug). Set by the update_task_list
    # tool; cleared at turn end.
    _task_list: str = ""
    _task_list_lock: Lock = Lock()

    @classmethod
    def set_task_list(cls, rendered: str) -> None:
        with cls._task_list_lock:
            cls._task_list = rendered or ""

    @classmethod
    def clear_task_list(cls) -> None:
        cls.set_task_list("")

    @classmethod
    def get_task_list(cls) -> str:
        with cls._task_list_lock:
            return cls._task_list

    @classmethod
    def get_activity(cls) -> str:
        """Return the current activity label (empty when just thinking)."""
        # When the ledger owns the live step, defer to it so the spinner
        # shows the same label the user sees in the rolling log.
        with cls._ledger_active_lock:
            ledger_on = cls._ledger_active
        if ledger_on:
            try:
                from code_puppy.messaging.step_ledger import get_ledger

                active = get_ledger().active
                if active is not None:
                    return (
                        f"Running: {active.label}"
                        if active.kind == "tool"
                        else active.label
                    )
            except Exception:
                pass
        with cls._activity_lock:
            return cls._activity

    @classmethod
    def set_ledger_active(cls, enabled: bool) -> None:
        """Toggle whether the live region reads its "current step" from the
        ``StepLedger`` instead of the plain ``_activity`` string.
        """
        with cls._ledger_active_lock:
            cls._ledger_active = bool(enabled)

    @classmethod
    def is_ledger_active(cls) -> bool:
        with cls._ledger_active_lock:
            return cls._ledger_active

    @staticmethod
    def format_context_info(total_tokens: int, capacity: int, proportion: float) -> str:
        """Create a concise context summary for spinner display."""
        if capacity <= 0:
            return ""
        proportion_pct = proportion * 100
        return f"Tokens: {total_tokens:,}/{capacity:,} ({proportion_pct:.1f}% used)"
