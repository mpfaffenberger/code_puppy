"""Revisioned computer-use state shared by snapshots and actions."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .backend_types import ComputerUseError
from .geometry import CaptureGeometry


@dataclass
class AppState:
    revision: str
    application: str
    bundle_id: str
    pid: int
    window_id: int
    window_title: str
    geometry: CaptureGeometry
    screenshot_path: str
    elements: dict[int, Any] = field(repr=False)
    created_at: float = field(default_factory=time.monotonic)
    consumed: bool = False

    def public_metadata(self) -> dict[str, Any]:
        return {
            "state_revision": self.revision,
            "application": self.application,
            "bundle_id": self.bundle_id,
            "pid": self.pid,
            "window_id": self.window_id,
            "window_title": self.window_title,
            "screenshot_path": self.screenshot_path,
            **self.geometry.as_dict(),
        }


class StateStore:
    def __init__(self, max_age_seconds: float = 120.0) -> None:
        self._state: AppState | None = None
        self._lock = threading.RLock()
        self.max_age_seconds = max_age_seconds

    def create(self, **kwargs: Any) -> AppState:
        state = AppState(revision=uuid.uuid4().hex, **kwargs)
        with self._lock:
            self._state = state
        return state

    def require(self, revision: str, *, consume: bool = False) -> AppState:
        if not revision:
            raise ComputerUseError(
                "state_revision is required. Call computer_get_app_state first."
            )
        with self._lock:
            state = self._state
            if state is None or state.revision != revision:
                raise ComputerUseError(
                    "Stale or unknown state_revision. Call computer_get_app_state again."
                )
            if time.monotonic() - state.created_at > self.max_age_seconds:
                raise ComputerUseError(
                    "The app state expired. Call computer_get_app_state again."
                )
            if state.consumed:
                raise ComputerUseError(
                    "The app state changed after an action. Fetch fresh app state."
                )
            if consume:
                state.consumed = True
            return state

    def current(self) -> AppState | None:
        with self._lock:
            return self._state

    def clear(self) -> None:
        with self._lock:
            self._state = None


state_store = StateStore()
