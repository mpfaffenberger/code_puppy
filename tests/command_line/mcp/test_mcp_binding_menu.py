"""Semantic rendering tests for the MCP binding menus."""

from unittest.mock import patch

from code_puppy.command_line.mcp_binding_menu import _render_menu, _render_preview

MODULE = "code_puppy.command_line.mcp_binding_menu"


def test_binding_menu_uses_semantic_selection_and_status_roles():
    bindings = {"alpha": {"auto_start": True}}

    with patch(f"{MODULE}.get_bound_servers", return_value=bindings):
        lines = _render_menu("code-puppy", [("alpha", "stdio", "running")], 0)

    styles = {style for style, _text in lines if style}
    assert {
        "class:tui.selected",
        "class:tui.success",
        "class:tui.warning",
        "class:tui.help-key",
    } <= styles
    assert not any("fg:" in style or "ansi" in style for style in styles)


def test_binding_preview_uses_semantic_detail_roles():
    bindings = {"alpha": {"auto_start": True}}

    with patch(f"{MODULE}.get_bound_servers", return_value=bindings):
        lines = _render_preview("code-puppy", [("alpha", "stdio", "running")], 0)

    styles = {style for style, _text in lines if style}
    assert {
        "class:tui.title",
        "class:tui.label",
        "class:tui.body",
        "class:tui.success",
        "class:tui.warning",
    } <= styles
    assert not any("fg:" in style or "ansi" in style for style in styles)
