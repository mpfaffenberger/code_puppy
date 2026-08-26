"""Tests to achieve 100% coverage for all command_line modules.

Covers remaining uncovered lines across:
- clipboard.py (import fallbacks)
- load_context_completion.py (exception path)
- file_path_completion.py (path display logic)
- prompt_toolkit_completion.py (unicode fallback, __main__, keybindings)
- command_handler.py (MarkdownCommandResult import fallback)
- pin_command_completion.py (empty partial_model branch)
- config_commands.py (various branches)
- add_model_menu.py (keybinding handlers)
- model_settings_menu.py (keybinding handlers)
- autosave_menu.py (keybinding handlers)
- agent_menu.py (keybinding handlers, action flows)
- uc_menu.py (helpers, highlight, delete)
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch


def test_clipboard_binary_content_import_failure():
    """Cover lines 37-39: BinaryContent ImportError fallback."""
    mod_name = "code_puppy.command_line.clipboard"
    saved = sys.modules.pop(mod_name, None)
    try:
        with patch.dict(sys.modules, {"pydantic_ai": None}):
            mod = importlib.import_module(mod_name)
            assert mod.BINARY_CONTENT_AVAILABLE is False
            assert mod.BinaryContent is None
    finally:
        sys.modules.pop(mod_name, None)
        if saved:
            sys.modules[mod_name] = saved
        else:
            saved = importlib.import_module(mod_name)
        # See note above: keep the package attribute in sync too.
        import code_puppy.command_line as _pkg

        _pkg.clipboard = saved


def test_clipboard_pil_import_failure():
    """Cover lines 27-30: PIL ImportError fallback."""
    mod_name = "code_puppy.command_line.clipboard"
    saved = sys.modules.pop(mod_name, None)
    try:
        with patch.dict(
            sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageGrab": None}
        ):
            mod = importlib.import_module(mod_name)
            assert mod.PIL_AVAILABLE is False
            assert mod.Image is None
            assert mod.ImageGrab is None
    finally:
        sys.modules.pop(mod_name, None)
        if saved:
            sys.modules[mod_name] = saved
        else:
            saved = importlib.import_module(mod_name)
        # ALSO restore the package attribute: ``import a.b`` rebinds it every import,
        # so string-target monkeypatches would otherwise hit the throwaway module.
        import code_puppy.command_line as _pkg

        _pkg.clipboard = saved


def test_command_handler_markdown_import_failure():
    """Cover lines 241-242: MarkdownCommandResult ImportError fallback."""
    from code_puppy.command_line.command_handler import handle_command

    mock_context = MagicMock()
    mock_context.current_agent = MagicMock()

    # Patch callbacks at the source module level
    with patch(
        "code_puppy.callbacks.on_custom_command", return_value=["some result"]
    ) as _mock_cb:
        with patch.dict(
            sys.modules,
            {
                "code_puppy_core_plugins.customizable_commands": None,
                "code_puppy_core_plugins.customizable_commands.register_callbacks": None,
            },
        ):
            result = handle_command("/unknowncmd_xyz")
            assert result is not None


def test_config_commands_set_no_key():
    """Cover config_commands line 258: /set with no arguments."""
    from code_puppy.command_line.config_commands import handle_set_command

    # "/set =value" -> key="" (empty after split on =) -> "You must supply a key."
    result = handle_set_command("/set =value")
    assert result is True


def test_config_pin_json_agent_reload_failure():
    """Cover lines 395-396: reload failure after pin."""

    from code_puppy.command_line.config_commands import handle_pin_model_command

    mock_agent = MagicMock()
    mock_agent.name = "myagent"
    mock_agent.reload_code_generation_agent.side_effect = Exception("fail")

    with (
        patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=["gpt-4"],
        ),
        patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            return_value={"myagent": "/path"},
        ),
        patch(
            "code_puppy.agents.agent_manager.get_agent_descriptions", return_value={}
        ),
        patch("code_puppy.messaging.emit_info"),
        patch("code_puppy.messaging.emit_success"),
        patch("code_puppy.messaging.emit_warning") as _mock_warn,
        patch("code_puppy.agents.get_current_agent", return_value=mock_agent),
        patch("builtins.open", mock_open(read_data="{}")),
        patch("json.load", return_value={}),
        patch("json.dump"),
    ):
        result = handle_pin_model_command("/pin_model myagent gpt-4")
        assert result is True


def test_config_pin_list_json_agents_with_pinned():
    """Cover lines 450, 495-497: show JSON agents with pinned models."""

    from code_puppy.command_line.config_commands import handle_pin_model_command

    _agent_config = {"model": "gpt-4"}

    with (
        patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=["gpt-4"],
        ),
        patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            return_value={"myagent": "/path/agent.json"},
        ),
        patch(
            "code_puppy.agents.agent_manager.get_agent_descriptions", return_value={}
        ),
        patch("code_puppy.messaging.emit_info") as _mock_info,
        patch("code_puppy.messaging.emit_warning"),
    ):
        result = handle_pin_model_command("/pin_model")
        assert result is True


def test_core_commands_shlex_fallback():
    """Cover core_commands lines 62-64: shlex.split ValueError."""
    from code_puppy.command_line.core_commands import handle_cd_command

    # Unbalanced quotes will cause shlex.split to fail, triggering fallback
    with patch("code_puppy.command_line.core_commands.emit_error"):
        result = handle_cd_command("/cd 'unclosed")
        assert result is True


def test_file_path_completion_permission_error():
    """Cover lines 72-73: exception handling."""
    from termflow.tui.completion import Document

    from code_puppy.command_line.file_path_completion import FilePathCompleter

    completer = FilePathCompleter()
    doc = Document("@somefile", cursor_position=len("@somefile"))
    event = MagicMock()

    with patch(
        "code_puppy.command_line.file_path_completion.glob.glob",
        side_effect=PermissionError("denied"),
    ):
        results = list(completer.get_completions(doc, event))
        assert results == []


def test_load_context_completion_exception():
    """Cover lines 50-52: exception path in get_completions."""
    from code_puppy.command_line.load_context_completion import LoadContextCompleter

    completer = LoadContextCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "/load_context test"
    doc.cursor_position = len(doc.text_before_cursor)
    complete_event = MagicMock()

    # Make Path(...).exists() raise to trigger the except Exception branch
    with patch("code_puppy.command_line.load_context_completion.Path") as mock_path:
        mock_path.return_value.__truediv__ = MagicMock(
            side_effect=PermissionError("denied")
        )
        results = list(completer.get_completions(doc, complete_event))
        assert results == []


def test_sanitize_for_encoding_unicode_error():
    """Cover lines 81-83: UnicodeEncodeError fallback in _sanitize_for_encoding."""
    from code_puppy.command_line.completers import (
        _sanitize_for_encoding,
    )

    # Create text with surrogate characters that cause encode errors
    text_with_surrogates = "hello\ud800world"
    result = _sanitize_for_encoding(text_with_surrogates)
    assert "hello" in result
    assert "world" in result


def test_uc_menu_delete_tool():
    """Cover lines 154-166: _delete_tool."""
    import os
    import tempfile

    from code_puppy.command_line.uc_menu import _delete_tool
    from code_puppy_core_plugins.universal_constructor.models import (
        ToolMeta,
        UCToolInfo,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tool_file = os.path.join(tmpdir, "sub", "test_tool.py")
        os.makedirs(os.path.dirname(tool_file))
        with open(tool_file, "w") as f:
            f.write("pass\n")

        tool = UCToolInfo(
            meta=ToolMeta(
                name="test",
                namespace="ns",
                description="d",
                enabled=True,
                version="1.0",
            ),
            signature="test()",
            source_path=tool_file,
            function_name="test",
            docstring="test",
        )

        with (
            patch(
                "code_puppy_core_plugins.universal_constructor.USER_UC_DIR",
                Path(tmpdir),
            ),
            patch("code_puppy.command_line.uc_menu.emit_success"),
        ):
            result = _delete_tool(tool)
            assert result is True
            assert not os.path.exists(tool_file)


def test_uc_menu_delete_tool_exception():
    """Cover _delete_tool exception handling."""
    from code_puppy.command_line.uc_menu import _delete_tool
    from code_puppy_core_plugins.universal_constructor.models import (
        ToolMeta,
        UCToolInfo,
    )

    tool = UCToolInfo(
        meta=ToolMeta(
            name="test", namespace="ns", description="d", enabled=True, version="1.0"
        ),
        signature="test()",
        source_path="/some/file.py",
        function_name="test",
        docstring="test",
    )
    with (
        patch("code_puppy.command_line.uc_menu.Path") as mock_path,
        patch("code_puppy.command_line.uc_menu.emit_error"),
    ):
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.unlink.side_effect = Exception("perm denied")
        result = _delete_tool(tool)
        assert result is False


def test_uc_menu_highlight_source_lines():
    """Highlighting flows through the theme-aware termflow highlighter."""
    from code_puppy.command_line.uc_menu import highlight_source_lines

    lines = highlight_source_lines(["def hello(x):", "    return x + 1", ""])
    assert len(lines) == 3
    assert "hello" in lines[0]


def test_uc_menu_tool_details_with_author():
    from code_puppy.command_line.uc_menu import tool_details
    from code_puppy_core_plugins.universal_constructor.models import (
        ToolMeta,
        UCToolInfo,
    )

    tool = UCToolInfo(
        meta=ToolMeta(
            name="test",
            namespace="ns",
            description="A tool that does something useful for testing purposes and has a long description that wraps",
            enabled=True,
            version="1.0",
            author="Test Author",
        ),
        signature="test(x: int, y: str) -> dict",
        source_path="/fake/test.py",
        function_name="test",
        docstring="Detailed docstring here with info about the function.",
    )
    details = tool_details(tool)
    assert "Test Author" in details
    assert "ENABLED" in details

    assert "No tool selected" in tool_details(None)


def test_uc_menu_toggle_tool_meta_not_found():
    """Cover lines 115-116: TOOL_META not found in file."""
    import tempfile

    from code_puppy.command_line.uc_menu import _toggle_tool_enabled
    from code_puppy_core_plugins.universal_constructor.models import (
        ToolMeta,
        UCToolInfo,
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# no TOOL_META here\ndef my_tool(): pass\n")
        f.flush()
        tool = UCToolInfo(
            meta=ToolMeta(
                name="test",
                namespace="ns",
                description="d",
                enabled=True,
                version="1.0",
            ),
            signature="test()",
            source_path=f.name,
            function_name="test",
            docstring="test",
        )
        with patch("code_puppy.command_line.uc_menu.emit_error"):
            result = _toggle_tool_enabled(tool)
            assert result is False
    import os

    os.unlink(f.name)
