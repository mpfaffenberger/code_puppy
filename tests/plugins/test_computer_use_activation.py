from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_puppy.plugins.computer_use.activation import (
    activate_application,
    activate_state,
)
from code_puppy.plugins.computer_use.backend_types import ComputerUseError
from code_puppy.plugins.computer_use.geometry import CaptureGeometry, Rect
from code_puppy.plugins.computer_use.state import AppState


class Application:
    def __init__(self, pid=7, terminated=False, activates=True):
        self.pid = pid
        self.is_terminated = terminated
        self.activates = activates
        self.options = None

    def processIdentifier(self):
        return self.pid

    def isTerminated(self):
        return self.is_terminated

    def activateWithOptions_(self, options):
        self.options = options
        return self.activates


def state(pid=7):
    return AppState(
        revision="revision",
        application="Spotify",
        bundle_id="com.spotify.client",
        pid=pid,
        window_id=42,
        window_title="Spotify Premium",
        geometry=CaptureGeometry(Rect(0, 0, 100, 100), 200, 200, 2),
        screenshot_path="/tmp/spotify.png",
        elements={},
    )


def test_activation_brings_state_process_to_front(monkeypatch):
    app = Application()
    workspace = SimpleNamespace(
        runningApplications=lambda: [app],
        frontmostApplication=lambda: app,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.activation._workspace",
        lambda: workspace,
    )

    activate_state(state())
    assert app.options == 3


def test_activation_can_target_pid_before_state_exists(monkeypatch):
    app = Application()
    workspace = SimpleNamespace(
        runningApplications=lambda: [app],
        frontmostApplication=lambda: app,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.activation._workspace",
        lambda: workspace,
    )

    activate_application(7, "Spotify")
    assert app.options == 3


def test_activation_rejects_missing_target(monkeypatch):
    workspace = SimpleNamespace(
        runningApplications=lambda: [],
        frontmostApplication=lambda: None,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.activation._workspace",
        lambda: workspace,
    )
    with pytest.raises(ComputerUseError, match="no longer running"):
        activate_state(state())
