"""Behavioral tests for the termflow-based MCP binding menus."""

from io import StringIO
from unittest.mock import patch

from code_puppy.command_line.mcp_binding_menu import (
    _binding_label,
    _render_details,
    build_binding_menu,
)

MODULE = "code_puppy.command_line.mcp_binding_menu"

SERVERS = [("alpha", "stdio", "running"), ("beta", "sse", "stopped")]


def _drive(keys, bindings):
    """Run the binding menu headlessly with a scripted key sequence."""
    script = iter(keys)
    out = StringIO()
    with patch(f"{MODULE}.get_bound_servers", return_value=bindings):
        menu = build_binding_menu(
            "code-puppy",
            SERVERS,
            key_source=lambda: next(script),
            output=out,
            size=lambda: (100, 30),
            alt_screen=False,
        )
        result = menu.run()
    return result, out.getvalue()


def test_binding_label_shows_checkbox_and_auto_marker():
    bindings = {"alpha": {"auto_start": True}}
    with patch(f"{MODULE}.get_bound_servers", return_value=bindings):
        assert _binding_label("code-puppy", "alpha") == "[x] alpha \u26a1auto"
        assert _binding_label("code-puppy", "beta") == "[ ] beta"


def test_details_pane_reflects_binding_state():
    bindings = {"alpha": {"auto_start": True}}
    with patch(f"{MODULE}.get_bound_servers", return_value=bindings):
        details = _render_details("code-puppy", SERVERS, "alpha")
    assert "alpha" in details
    assert "stdio" in details
    assert "running" in details
    assert "Bound:" in details and "yes" in details
    assert "Auto-start:" in details


def test_space_toggles_binding():
    with patch(f"{MODULE}.toggle_binding") as mock_toggle:
        result, _ = _drive([" ", "enter"], bindings={})
    mock_toggle.assert_called_once_with("code-puppy", "alpha")
    assert not result.cancelled


def test_a_binds_then_enables_auto_start_when_unbound():
    with (
        patch(f"{MODULE}.toggle_auto_start", return_value=None) as mock_auto,
        patch(f"{MODULE}.set_binding") as mock_set,
    ):
        _drive(["down", "a", "enter"], bindings={})
    mock_auto.assert_called_once_with("code-puppy", "beta")
    mock_set.assert_called_once_with("code-puppy", "beta", auto_start=True)


def test_q_exits_like_enter():
    result, _ = _drive(["q"], bindings={})
    assert not result.cancelled


def test_escape_exits():
    result, _ = _drive(["escape"], bindings={})
    assert result.cancelled
