"""Shared fixtures for TUI tests.

Disable first-run onboarding by default so the on_mount hook never pops a
modal during unrelated tests (it would steal focus/keys and break them).
Onboarding-specific tests monkeypatch ``should_show_onboarding`` directly.
"""

import pytest


@pytest.fixture(autouse=True)
def _skip_tutorial(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_SKIP_TUTORIAL", "1")
