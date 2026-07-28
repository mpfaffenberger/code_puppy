from __future__ import annotations

import pytest

from code_puppy.plugins.computer_use.backend_types import ComputerUseError
from code_puppy.plugins.computer_use.geometry import CaptureGeometry, Rect
from code_puppy.plugins.computer_use.policy import PolicyStore
from code_puppy.plugins.computer_use.safety import require_safe_state
from code_puppy.plugins.computer_use.state import state_store


def test_policy_requires_first_use_consent_then_persists_choice(tmp_path):
    path = tmp_path / "policy.json"
    policy = PolicyStore(path)
    with pytest.raises(ComputerUseError, match="one-time permission"):
        policy.require_enabled()

    policy.set_enabled(True)
    policy.require("com.example.Editor")
    assert path.stat().st_mode & 0o777 == 0o600
    PolicyStore(path).require("com.example.Editor")

    policy.set_enabled(False)
    with pytest.raises(ComputerUseError, match="disabled in settings"):
        policy.require("com.example.Editor")


def test_policy_supports_persisted_app_denials(tmp_path):
    path = tmp_path / "policy.json"
    policy = PolicyStore(path)
    policy.set_enabled(True)

    policy.deny("com.example.Editor")
    with pytest.raises(ComputerUseError, match="denied"):
        policy.require("com.example.Editor")
    assert path.stat().st_mode & 0o777 == 0o600

    policy.allow("com.example.Editor")
    PolicyStore(path).require("com.example.Editor")


def test_policy_pause_and_security_processes(tmp_path):
    policy = PolicyStore(tmp_path / "policy.json")
    policy.set_enabled(True)
    policy.set_paused(True)
    with pytest.raises(ComputerUseError, match="emergency stop"):
        policy.require("com.example.Other")

    with pytest.raises(ComputerUseError, match="never allowed"):
        policy.allow("com.apple.loginwindow")


def test_safe_state_is_not_interrupted_by_user_input(monkeypatch):
    state_store.clear()
    state = state_store.create(
        application="Editor",
        bundle_id="com.example.Editor",
        pid=1,
        window_id=2,
        window_title="Document",
        geometry=CaptureGeometry(Rect(0, 0, 100, 100), 200, 200, 2),
        screenshot_path="/tmp/editor.png",
        elements={},
    )
    monkeypatch.setattr(
        "code_puppy.plugins.computer_use.safety.policy_store.require",
        lambda bundle_id: None,
    )
    assert require_safe_state(state.revision, consume=True) is state
    assert state.consumed
