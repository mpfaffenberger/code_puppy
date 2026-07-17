"""Tests for the ``compact_steps`` config getters and helpers."""

import pytest

from code_puppy import config


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch):
    """Each test starts with a clean slate — no inherited config values."""
    for key in (
        "compact_steps",
        "compact_steps_max_visible",
        "compact_steps_summary",
    ):
        monkeypatch.delenv(key, raising=False)
    # Patch get_value so isolated from real config file state.
    store: dict[str, str] = {}

    def fake_get_value(name, *args, **kwargs):
        return store.get(name)

    def fake_set_value(name, value, *args, **kwargs):
        store[name] = str(value)

    monkeypatch.setattr(config, "get_value", fake_get_value)
    monkeypatch.setattr(config, "set_config_value", fake_set_value)
    return store


def test_compact_steps_defaults_on(_reset_config_state):
    # Option B (IN_PLACE_STATUS_PLAN.md §3b) is the recommended path and
    # now the default — opt-out via ``/set compact_steps false``.
    assert config.get_compact_steps() is True


def test_compact_steps_round_trip(_reset_config_state):
    config.set_compact_steps(True)
    assert config.get_compact_steps() is True
    config.set_compact_steps(False)
    assert config.get_compact_steps() is False


def test_compact_steps_accepts_truthy_strings(_reset_config_state):
    for truthy in ("1", "true", "yes", "on", "TRUE", "Yes"):
        _reset_config_state["compact_steps"] = truthy
        assert config.get_compact_steps() is True


def test_compact_steps_accepts_falsy_strings(_reset_config_state):
    for falsy in ("0", "false", "no", "off", "FALSE", ""):
        _reset_config_state["compact_steps"] = falsy
        assert config.get_compact_steps() is False


def test_compact_steps_max_visible_default(_reset_config_state):
    assert config.get_compact_steps_max_visible() == 5


def test_compact_steps_max_visible_bounded(_reset_config_state):
    _reset_config_state["compact_steps_max_visible"] = "999"
    # Caps at 50 to keep the live region from monopolizing the viewport.
    assert config.get_compact_steps_max_visible() == 50
    _reset_config_state["compact_steps_max_visible"] = "-3"
    assert config.get_compact_steps_max_visible() == 0


def test_compact_steps_max_visible_invalid_falls_back(_reset_config_state):
    _reset_config_state["compact_steps_max_visible"] = "not-an-int"
    assert config.get_compact_steps_max_visible() == 5


def test_compact_steps_summary_default_on(_reset_config_state):
    # The ▸ N steps summary is on by default — opt-out, not opt-in.
    assert config.get_compact_steps_summary() is True


def test_compact_steps_summary_round_trip(_reset_config_state):
    config.set_compact_steps_summary(False)
    assert config.get_compact_steps_summary() is False
    config.set_compact_steps_summary(True)
    assert config.get_compact_steps_summary() is True
