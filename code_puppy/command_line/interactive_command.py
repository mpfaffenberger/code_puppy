"""Helpers for long-running interactive commands that need cooperative cancel."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BackgroundInteractiveCommand:
    """Background command work that should keep the composer alive."""

    run: Callable[[threading.Event], object | None]
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def request_cancel(self) -> None:
        """Signal the background command to stop cooperatively."""
        self.cancel_event.set()
