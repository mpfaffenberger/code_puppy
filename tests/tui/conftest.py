"""Shared fixtures for TUI tests.

Disable first-run onboarding by default so the on_mount hook never pops a
modal during unrelated tests (it would steal focus/keys and break them).
Onboarding-specific tests monkeypatch ``should_show_onboarding`` directly.
"""

import pytest


@pytest.fixture(autouse=True)
def _skip_tutorial(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_SKIP_TUTORIAL", "1")


@pytest.fixture(autouse=True)
def _no_ambient_turn_end_plugins(monkeypatch):
    """Start every TUI test with no ``interactive_turn_end`` callbacks.

    Core plugins imported by earlier tests (e.g. auto_continue, which asks a
    classifier model whether to continue) stay registered for the rest of the
    session. In CI, where a real model is configured, that turns every mocked
    turn into a slow network call and the turn-loop tests time out. Tests
    that need a turn-end hook register their own.
    """
    from code_puppy import callbacks

    monkeypatch.setitem(callbacks._callbacks, "interactive_turn_end", [])
