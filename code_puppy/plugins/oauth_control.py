"""Shared cooperative-cancel helpers for OAuth callback waits."""

from __future__ import annotations

import threading
import time
from typing import Callable, Literal


WaitResult = Literal["completed", "timeout", "cancelled"]


def wait_for_event_or_cancel(
    event: threading.Event,
    *,
    timeout: float,
    cancel_event: threading.Event | None,
    poll_interval: float = 0.1,
) -> WaitResult:
    """Wait for an event while also honoring cooperative cancellation."""
    deadline = time.monotonic() + timeout
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled"
        if event.wait(timeout=min(poll_interval, max(0.0, deadline - time.monotonic()))):
            return "completed"
        if time.monotonic() >= deadline:
            return "timeout"


def wait_for_predicate_or_cancel(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    cancel_event: threading.Event | None,
    poll_interval: float = 0.25,
) -> WaitResult:
    """Poll a predicate while also honoring cooperative cancellation."""
    deadline = time.monotonic() + timeout
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled"
        if predicate():
            return "completed"
        if time.monotonic() >= deadline:
            return "timeout"
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
