"""Phase 0: the 3-layer UI mode resolver.

Precedence (highest first): /ui session override > CODE_PUPPY_UI env >
puppy.cfg ui_mode > default 'interactive'.

Canonical values are 'interactive' (classic console) and 'tui' (Textual).
The legacy names 'classic'/'textual' are still accepted as aliases.
"""

import code_puppy.config as config


def _reset_session():
    config.set_session_ui_mode(None)


def test_default_is_interactive(monkeypatch):
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(config, "get_value", lambda key: None)
    assert config.get_ui_mode() == "interactive"


def test_config_layer(monkeypatch):
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(
        config, "get_value", lambda key: "tui" if key == "ui_mode" else None
    )
    assert config.get_ui_mode() == "tui"


def test_env_overrides_config(monkeypatch):
    _reset_session()
    monkeypatch.setenv("CODE_PUPPY_UI", "interactive")
    monkeypatch.setattr(config, "get_value", lambda key: "tui")
    assert config.get_ui_mode() == "interactive"


def test_session_overrides_everything(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_UI", "interactive")
    monkeypatch.setattr(config, "get_value", lambda key: "interactive")
    config.set_session_ui_mode("tui")
    try:
        assert config.get_ui_mode() == "tui"
    finally:
        _reset_session()


def test_invalid_values_are_ignored(monkeypatch):
    _reset_session()
    monkeypatch.setenv("CODE_PUPPY_UI", "banana")
    monkeypatch.setattr(config, "get_value", lambda key: None)
    assert config.get_ui_mode() == "interactive"


def test_legacy_aliases_are_accepted(monkeypatch):
    """Pre-rename configs/env keep working: classic->interactive, textual->tui."""
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(
        config, "get_value", lambda key: "textual" if key == "ui_mode" else None
    )
    assert config.get_ui_mode() == "tui"
    monkeypatch.setattr(
        config, "get_value", lambda key: "classic" if key == "ui_mode" else None
    )
    assert config.get_ui_mode() == "interactive"


def test_is_tui_mode_helper(monkeypatch):
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(config, "get_value", lambda key: None)
    assert config.is_tui_mode() is False
    config.set_session_ui_mode("tui")
    try:
        assert config.is_tui_mode() is True
    finally:
        _reset_session()


def test_set_session_ui_mode_normalizes_and_clears():
    # Legacy alias normalizes to the canonical value.
    assert config.set_session_ui_mode("TEXTUAL") == "tui"
    assert config.set_session_ui_mode("interactive") == "interactive"
    assert config.set_session_ui_mode("nope") is None
    assert config.set_session_ui_mode(None) is None


def test_set_ui_mode_persists_canonical(monkeypatch):
    written = {}
    monkeypatch.setattr(config, "set_config_value", lambda k, v: written.update({k: v}))
    # Legacy alias is upgraded to the canonical value on persist.
    assert config.set_ui_mode("textual") is True
    assert written == {"ui_mode": "tui"}
    assert config.set_ui_mode("interactive") is True
    assert written == {"ui_mode": "interactive"}
    assert config.set_ui_mode("banana") is False


def test_ui_mode_in_config_keys():
    assert "ui_mode" in config.get_config_keys()
