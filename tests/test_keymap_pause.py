"""Tests for the pause-agent-key portion of code_puppy.keymap (Phase 3)."""

from __future__ import annotations

import pytest

from code_puppy import keymap


# NOTE: keymap functions import ``get_value`` and ``should_use_alternate_cancel_key``
# lazily inside the functions, so we patch at the source modules.


@pytest.fixture(autouse=True)
def _no_uvx_override(monkeypatch):
    """Make sure the Windows+uvx alt-key path doesn't accidentally fire."""
    monkeypatch.setattr(
        "code_puppy.uvx_detection.should_use_alternate_cancel_key",
        lambda: False,
    )


# =============================================================================
# get_pause_agent_key
# =============================================================================


def test_get_pause_agent_key_returns_default_when_not_configured(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: None)
    assert keymap.get_pause_agent_key() == keymap.DEFAULT_PAUSE_AGENT_KEY
    assert keymap.get_pause_agent_key() == "ctrl+t"


def test_get_pause_agent_key_returns_default_when_blank(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "   ")
    assert keymap.get_pause_agent_key() == keymap.DEFAULT_PAUSE_AGENT_KEY


def test_get_pause_agent_key_returns_configured_value(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+p")
    assert keymap.get_pause_agent_key() == "ctrl+p"


def test_get_pause_agent_key_lowercases_and_strips(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "  CTRL+Y  ")
    assert keymap.get_pause_agent_key() == "ctrl+y"


def test_get_pause_agent_key_uvx_override(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.uvx_detection.should_use_alternate_cancel_key", lambda: True
    )
    # Even if config says otherwise, uvx alt path wins.
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+t")
    assert keymap.get_pause_agent_key() == "ctrl+p"


# =============================================================================
# validate_pause_agent_key
# =============================================================================


def test_validate_pause_agent_key_accepts_valid(monkeypatch):
    for valid in keymap.VALID_PAUSE_KEYS:
        monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, _v=valid: _v)
        keymap.validate_pause_agent_key()  # Must not raise


def test_validate_pause_agent_key_rejects_invalid(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+z")
    with pytest.raises(keymap.KeymapError) as exc:
        keymap.validate_pause_agent_key()
    assert "pause_agent_key" in str(exc.value)


# =============================================================================
# get_pause_agent_char_code
# =============================================================================


def test_get_pause_agent_char_code_ctrl_t(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+t")
    assert keymap.get_pause_agent_char_code() == "\x14"


def test_get_pause_agent_char_code_ctrl_p(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+p")
    assert keymap.get_pause_agent_char_code() == "\x10"


def test_get_pause_agent_char_code_ctrl_o(monkeypatch):
    """ctrl+o is a tmux-safe option added in the pause-key expansion."""
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+o")
    assert keymap.get_pause_agent_char_code() == "\x0f"


def test_get_pause_agent_char_code_ctrl_g(monkeypatch):
    """ctrl+g is another tmux-safe option."""
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+g")
    assert keymap.get_pause_agent_char_code() == "\x07"


# =============================================================================
# get_pause_agent_display_name
# =============================================================================


def test_get_pause_agent_display_name_ctrl_t(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+t")
    assert keymap.get_pause_agent_display_name() == "Ctrl+T"


def test_get_pause_agent_display_name_ctrl_y(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+y")
    assert keymap.get_pause_agent_display_name() == "Ctrl+Y"


def test_get_pause_agent_display_name_ctrl_o(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, **_k: "ctrl+o")
    assert keymap.get_pause_agent_display_name() == "Ctrl+O"


def test_validate_pause_agent_key_rejects_dangerous_keys(monkeypatch):
    """Keys that send signals or collide with terminal control must be rejected."""
    for bad in ("ctrl+c", "ctrl+d", "ctrl+z", "ctrl+s", "ctrl+q", "escape"):
        monkeypatch.setattr("code_puppy.config.get_value", lambda *_a, _v=bad: _v)
        with pytest.raises(keymap.KeymapError):
            keymap.validate_pause_agent_key()
