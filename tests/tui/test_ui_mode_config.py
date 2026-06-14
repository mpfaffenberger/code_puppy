"""Phase 0: the 3-layer UI mode resolver.

Precedence (highest first): /ui session override > CODE_PUPPY_UI env >
puppy.cfg ui_mode > default 'classic'.
"""

import code_puppy.config as config


def _reset_session():
    config.set_session_ui_mode(None)


def test_default_is_classic(monkeypatch):
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(config, "get_value", lambda key: None)
    assert config.get_ui_mode() == "classic"


def test_config_layer(monkeypatch):
    _reset_session()
    monkeypatch.delenv("CODE_PUPPY_UI", raising=False)
    monkeypatch.setattr(
        config, "get_value", lambda key: "textual" if key == "ui_mode" else None
    )
    assert config.get_ui_mode() == "textual"


def test_env_overrides_config(monkeypatch):
    _reset_session()
    monkeypatch.setenv("CODE_PUPPY_UI", "classic")
    monkeypatch.setattr(config, "get_value", lambda key: "textual")
    assert config.get_ui_mode() == "classic"


def test_session_overrides_everything(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_UI", "classic")
    monkeypatch.setattr(config, "get_value", lambda key: "classic")
    config.set_session_ui_mode("textual")
    try:
        assert config.get_ui_mode() == "textual"
    finally:
        _reset_session()


def test_invalid_values_are_ignored(monkeypatch):
    _reset_session()
    monkeypatch.setenv("CODE_PUPPY_UI", "banana")
    monkeypatch.setattr(config, "get_value", lambda key: None)
    assert config.get_ui_mode() == "classic"


def test_set_session_ui_mode_normalizes_and_clears():
    assert config.set_session_ui_mode("TEXTUAL") == "textual"
    assert config.set_session_ui_mode("nope") is None
    assert config.set_session_ui_mode(None) is None


def test_set_ui_mode_rejects_invalid(monkeypatch):
    written = {}
    monkeypatch.setattr(config, "set_config_value", lambda k, v: written.update({k: v}))
    assert config.set_ui_mode("textual") is True
    assert written == {"ui_mode": "textual"}
    assert config.set_ui_mode("banana") is False


def test_ui_mode_in_config_keys():
    assert "ui_mode" in config.get_config_keys()
