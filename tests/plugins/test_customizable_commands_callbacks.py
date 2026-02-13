"""Comprehensive tests for customizable_commands callbacks.

Tests cover markdown command loading, unique name generation,
custom help callbacks, and command execution.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from code_puppy.plugins.customizable_commands.register_callbacks import (
    MarkdownCommandResult,
    _command_descriptions,
    _custom_commands,
    _custom_help,
    _generate_unique_command_name,
    _handle_custom_command,
    _load_markdown_commands,
)


class TestMarkdownCommandResult:
    """Test MarkdownCommandResult class."""

    def test_init_stores_content(self):
        """Test that __init__ stores the content."""
        result = MarkdownCommandResult("Hello world")
        assert result.content == "Hello world"

    def test_init_with_empty_content(self):
        """Test initialization with empty content."""
        result = MarkdownCommandResult("")
        assert result.content == ""

    def test_init_with_multiline_content(self):
        """Test initialization with multiline content."""
        content = "Line 1\nLine 2\nLine 3"
        result = MarkdownCommandResult(content)
        assert result.content == content

    def test_str_returns_content(self):
        """Test that __str__ returns the content."""
        result = MarkdownCommandResult("Test content")
        assert str(result) == "Test content"

    def test_str_with_empty_content(self):
        """Test __str__ with empty content."""
        result = MarkdownCommandResult("")
        assert str(result) == ""

    def test_repr_shows_character_count(self):
        """Test that __repr__ shows character count."""
        result = MarkdownCommandResult("Hello")
        assert repr(result) == "MarkdownCommandResult(5 chars)"

    def test_repr_with_long_content(self):
        """Test __repr__ with longer content."""
        content = "A" * 100
        result = MarkdownCommandResult(content)
        assert repr(result) == "MarkdownCommandResult(100 chars)"

    def test_repr_with_empty_content(self):
        """Test __repr__ with empty content."""
        result = MarkdownCommandResult("")
        assert repr(result) == "MarkdownCommandResult(0 chars)"


class TestGenerateUniqueCommandName:
    """Test _generate_unique_command_name function."""

    def test_unique_name_returns_base(self):
        """Test that unique names return the base name."""
        # Clear the cache first
        _custom_commands.clear()
        result = _generate_unique_command_name("my_command")
        assert result == "my_command"

    def test_duplicate_name_gets_suffix_2(self):
        """Test that first duplicate gets suffix 2."""
        _custom_commands.clear()
        _custom_commands["test"] = "content"
        result = _generate_unique_command_name("test")
        assert result == "test2"

    def test_multiple_duplicates_increment_suffix(self):
        """Test that multiple duplicates increment the suffix."""
        _custom_commands.clear()
        _custom_commands["cmd"] = "content"
        _custom_commands["cmd2"] = "content"
        _custom_commands["cmd3"] = "content"
        result = _generate_unique_command_name("cmd")
        assert result == "cmd4"

    def test_suffix_skips_existing(self):
        """Test that suffix skips existing names."""
        _custom_commands.clear()
        _custom_commands["base"] = "content"
        _custom_commands["base2"] = "content"
        # base3 is available
        _custom_commands["base4"] = "content"
        result = _generate_unique_command_name("base")
        assert result == "base3"


class TestLoadMarkdownCommands:
    """Test _load_markdown_commands function."""

    def test_clears_existing_commands(self):
        """Test that loading clears existing commands."""
        _custom_commands["old_command"] = "old content"
        _command_descriptions["old_command"] = "old description"

        with patch.object(Path, "exists", return_value=False):
            _load_markdown_commands()

        assert "old_command" not in _custom_commands
        assert "old_command" not in _command_descriptions

    def test_handles_missing_directories(self):
        """Test that missing directories are skipped gracefully."""
        with patch.object(Path, "exists", return_value=False):
            _load_markdown_commands()  # Should not raise

        # Commands should be empty
        assert len(_custom_commands) == 0

    def test_loads_md_files_from_claude_commands(self):
        """Test loading .md files from .claude/commands directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .claude/commands directory
            cmd_dir = Path(tmpdir) / ".claude" / "commands"
            cmd_dir.mkdir(parents=True)

            # Create a test markdown file
            test_file = cmd_dir / "test_command.md"
            test_file.write_text("This is the description\n\nMore content here")

            # Patch the command directories to use our temp dir
            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                _load_markdown_commands()

            assert "test_command" in _custom_commands
            assert "This is the description" in _command_descriptions["test_command"]

    def test_loads_prompt_md_files_from_github_prompts(self):
        """Test loading .prompt.md files from .github/prompts directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .github/prompts directory
            prompts_dir = Path(tmpdir) / ".github" / "prompts"
            prompts_dir.mkdir(parents=True)

            # Create a test prompt file
            test_file = prompts_dir / "my_prompt.prompt.md"
            test_file.write_text("Prompt description\n\nPrompt content")

            # Patch to use .github/prompts pattern
            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [".github/prompts"],
            ):
                with patch.object(Path, "expanduser", return_value=prompts_dir):
                    with patch.object(Path, "exists", return_value=True):
                        with patch.object(
                            Path,
                            "glob",
                            return_value=[test_file],
                        ):
                            _load_markdown_commands()

            assert "my_prompt" in _custom_commands

    def test_skips_empty_files(self):
        """Test that empty files are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)

            # Create an empty file
            empty_file = cmd_dir / "empty.md"
            empty_file.write_text("   \n   ")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                _load_markdown_commands()

            assert "empty" not in _custom_commands

    def test_extracts_description_from_first_non_heading_line(self):
        """Test description extraction skips heading lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)

            # Create file with heading first
            test_file = cmd_dir / "with_heading.md"
            test_file.write_text("# Heading\nActual description\nMore content")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                _load_markdown_commands()

            assert "with_heading" in _custom_commands
            assert "Actual description" in _command_descriptions["with_heading"]

    def test_truncates_long_descriptions(self):
        """Test that long descriptions are truncated at 50 chars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)

            # Create file with very long first line
            long_desc = "A" * 100
            test_file = cmd_dir / "long_desc.md"
            test_file.write_text(long_desc)

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                _load_markdown_commands()

            assert "long_desc" in _custom_commands
            desc = _command_descriptions["long_desc"]
            assert len(desc) == 53  # 50 chars + "..."
            assert desc.endswith("...")

    def test_handles_file_read_error(self):
        """Test that file read errors are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)

            # Create a file that we can make unreadable
            test_file = cmd_dir / "error_test.md"
            test_file.write_text("Content")

            # Mock read_text to raise an error for this specific test
            original_read_text = Path.read_text

            def mock_read_text(self, *args, **kwargs):
                if "error_test.md" in str(self):
                    raise IOError("Simulated read error")
                return original_read_text(self, *args, **kwargs)

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                with patch.object(Path, "read_text", mock_read_text):
                    with patch(
                        "code_puppy.plugins.customizable_commands.register_callbacks.emit_error"
                    ) as mock_emit:
                        _load_markdown_commands()

            # Should have emitted an error
            mock_emit.assert_called()
            # Command should not be loaded
            assert "error_test" not in _custom_commands

    def test_later_directory_overrides_earlier(self):
        """Test that later directories override earlier ones (project > global)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two directories with same-named files
            # Simulates global (dir1) and project (dir2)
            dir1 = Path(tmpdir) / "global"
            dir2 = Path(tmpdir) / "project"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "dupe.md").write_text("Global content")
            (dir2 / "dupe.md").write_text("Project content")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(dir1), str(dir2)],
            ):
                _load_markdown_commands()

            # Later directory (project) should override earlier (global)
            assert "dupe" in _custom_commands
            assert _custom_commands["dupe"] == "Project content"
            # Should NOT have a dupe2 - we override, not suffix
            assert "dupe2" not in _custom_commands

    def test_uses_filename_for_description_fallback(self):
        """Test that filename is used as description when all lines are headings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)

            # Create file with only headings
            test_file = cmd_dir / "only_headings.md"
            test_file.write_text("# Heading 1\n## Heading 2")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                _load_markdown_commands()

            assert "only_headings" in _custom_commands
            # Description should be derived from filename
            desc = _command_descriptions["only_headings"]
            assert "Only" in desc or "Headings" in desc


class TestCustomHelp:
    """Test _custom_help callback function."""

    def test_returns_list_of_tuples(self):
        """Test that custom help returns list of tuples."""
        _custom_commands.clear()
        _command_descriptions.clear()

        with patch.object(Path, "exists", return_value=False):
            result = _custom_help()

        assert isinstance(result, list)
        assert all(isinstance(item, tuple) for item in result)

    def test_returns_sorted_entries(self):
        """Test that help entries are sorted by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)
            (cmd_dir / "zebra.md").write_text("Zebra command")
            (cmd_dir / "alpha.md").write_text("Alpha command")
            (cmd_dir / "middle.md").write_text("Middle command")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                result = _custom_help()

            names = [entry[0] for entry in result]
            assert names == sorted(names)

    def test_help_entry_format(self):
        """Test the format of help entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = Path(tmpdir)
            (cmd_dir / "test.md").write_text("Test description here")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(cmd_dir)],
            ):
                result = _custom_help()

            # Find the test entry
            test_entry = next((e for e in result if e[0] == "test"), None)
            assert test_entry is not None
            assert len(test_entry) == 2
            assert "Execute markdown command" in test_entry[1]

    def test_reloads_commands_on_each_call(self):
        """Test that _custom_help reloads commands each time."""
        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks._load_markdown_commands"
        ) as mock_load:
            mock_load.return_value = None
            _custom_help()
            _custom_help()

        assert mock_load.call_count == 2


class TestHandleCustomCommand:
    """Test _handle_custom_command function."""

    def test_returns_none_for_empty_name(self):
        """Test that empty command name returns None."""
        result = _handle_custom_command("/", "")
        assert result is None

    def test_returns_none_for_none_name(self):
        """Test that None command name returns None."""
        result = _handle_custom_command("/", None)
        assert result is None

    def test_returns_none_for_unknown_command(self):
        """Test that unknown command returns None."""
        _custom_commands.clear()
        result = _handle_custom_command("/unknown", "unknown")
        assert result is None

    def test_loads_commands_if_empty(self):
        """Test that commands are loaded if cache is empty."""
        _custom_commands.clear()

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks._load_markdown_commands"
        ) as mock_load:
            _handle_custom_command("/test", "test")

        mock_load.assert_called_once()

    def test_returns_markdown_result_for_valid_command(self):
        """Test that valid command returns MarkdownCommandResult."""
        _custom_commands.clear()
        _custom_commands["mytest"] = "Test content"

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks.emit_info"
        ):
            result = _handle_custom_command("/mytest", "mytest")

        assert isinstance(result, MarkdownCommandResult)
        assert result.content == "Test content"

    def test_appends_arguments_to_prompt(self):
        """Test that additional arguments are appended to the prompt."""
        _custom_commands.clear()
        _custom_commands["cmd"] = "Base content"

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks.emit_info"
        ):
            result = _handle_custom_command("/cmd extra args here", "cmd")

        assert isinstance(result, MarkdownCommandResult)
        assert "Base content" in result.content
        assert "Additional context: extra args here" in result.content

    def test_no_args_returns_content_only(self):
        """Test that command without args returns just the content."""
        _custom_commands.clear()
        _custom_commands["simple"] = "Just the content"

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks.emit_info"
        ):
            result = _handle_custom_command("/simple", "simple")

        assert result.content == "Just the content"

    def test_emits_info_message(self):
        """Test that info message is emitted for valid commands."""
        _custom_commands.clear()
        _custom_commands["info_test"] = "Content"

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks.emit_info"
        ) as mock_emit:
            _handle_custom_command("/info_test", "info_test")

        mock_emit.assert_called_once()
        assert "info_test" in mock_emit.call_args[0][0]
        assert "📝" in mock_emit.call_args[0][0]

    def test_handles_whitespace_in_args(self):
        """Test handling of extra whitespace in arguments."""
        _custom_commands.clear()
        _custom_commands["ws"] = "Content"

        with patch(
            "code_puppy.plugins.customizable_commands.register_callbacks.emit_info"
        ):
            result = _handle_custom_command("/ws   arg1  arg2  ", "ws")

        # Arguments should include the extra whitespace
        assert "arg1  arg2" in result.content


class TestCallbackRegistration:
    """Test that callbacks are properly registered."""

    def test_custom_help_callback_registered(self):
        """Test that custom_command_help callback is registered."""
        from code_puppy.callbacks import get_callbacks

        callbacks = get_callbacks("custom_command_help")
        # _custom_help should be registered
        assert any(
            cb is _custom_help or getattr(cb, "__wrapped__", None) is _custom_help
            for cb in callbacks
        )

    def test_custom_command_callback_registered(self):
        """Test that custom_command callback is registered."""
        from code_puppy.callbacks import get_callbacks

        callbacks = get_callbacks("custom_command")
        # _handle_custom_command should be registered
        assert any(
            cb is _handle_custom_command
            or getattr(cb, "__wrapped__", None) is _handle_custom_command
            for cb in callbacks
        )


class TestModuleExports:
    """Test module exports."""

    def test_markdown_command_result_in_all(self):
        """Test that MarkdownCommandResult is exported in __all__."""
        from code_puppy.plugins.customizable_commands import register_callbacks

        assert "MarkdownCommandResult" in register_callbacks.__all__


class TestGlobalCommands:
    """Test global commands functionality."""

    def test_global_directory_in_command_directories(self):
        """Test that global directory is included in _COMMAND_DIRECTORIES."""
        from code_puppy.plugins.customizable_commands.register_callbacks import (
            _COMMAND_DIRECTORIES,
        )

        assert "~/.code-puppy/commands" in _COMMAND_DIRECTORIES
        # Global should be first (lowest priority, gets overridden by project)
        assert _COMMAND_DIRECTORIES[0] == "~/.code-puppy/commands"

    def test_global_commands_work_with_expanduser(self):
        """Test that global path with ~ expands correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake global commands directory
            global_dir = Path(tmpdir) / "global"
            global_dir.mkdir()
            (global_dir / "global_cmd.md").write_text("Global command content")

            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(global_dir)],
            ):
                _load_markdown_commands()

            assert "global_cmd" in _custom_commands
            assert _custom_commands["global_cmd"] == "Global command content"

    def test_project_overrides_global_same_name(self):
        """Test that project command overrides global with same name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "global"
            project_dir = Path(tmpdir) / "project"
            global_dir.mkdir()
            project_dir.mkdir()

            # Same command name in both
            (global_dir / "deploy.md").write_text("Global deploy")
            (project_dir / "deploy.md").write_text("Project-specific deploy")

            # Global first, project second (project wins)
            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                [str(global_dir), str(project_dir)],
            ):
                _load_markdown_commands()

            assert "deploy" in _custom_commands
            assert _custom_commands["deploy"] == "Project-specific deploy"

    def test_missing_global_directory_skipped(self):
        """Test that missing global directory doesn't cause errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.md").write_text("Test content")

            # Non-existent global dir, existing project dir
            with patch(
                "code_puppy.plugins.customizable_commands.register_callbacks._COMMAND_DIRECTORIES",
                ["/nonexistent/path/commands", str(project_dir)],
            ):
                _load_markdown_commands()  # Should not raise

            assert "test" in _custom_commands


class TestCommandsLoadedAtImport:
    """Test that commands are loaded at module import time."""

    def test_commands_dict_exists(self):
        """Test that _custom_commands dict exists after import."""
        from code_puppy.plugins.customizable_commands import register_callbacks

        assert hasattr(register_callbacks, "_custom_commands")
        assert isinstance(register_callbacks._custom_commands, dict)

    def test_descriptions_dict_exists(self):
        """Test that _command_descriptions dict exists after import."""
        from code_puppy.plugins.customizable_commands import register_callbacks

        assert hasattr(register_callbacks, "_command_descriptions")
        assert isinstance(register_callbacks._command_descriptions, dict)
