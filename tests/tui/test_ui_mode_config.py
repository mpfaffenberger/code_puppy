"""is_tui_mode() / set_tui_mode() — simple bool set once at startup."""

import code_puppy.config as config


def test_default_is_false():
    """Fresh import: not in TUI mode."""
    config.set_tui_mode(False)
    assert config.is_tui_mode() is False


def test_set_tui_mode_true():
    config.set_tui_mode(True)
    try:
        assert config.is_tui_mode() is True
    finally:
        config.set_tui_mode(False)


def test_set_tui_mode_false():
    config.set_tui_mode(True)
    config.set_tui_mode(False)
    assert config.is_tui_mode() is False


def test_set_tui_mode_coerces_to_bool():
    config.set_tui_mode(1)
    try:
        assert config.is_tui_mode() is True
    finally:
        config.set_tui_mode(False)
