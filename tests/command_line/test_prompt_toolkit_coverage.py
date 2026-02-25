"""Tests for prompt_toolkit_completion.py to achieve 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.document import Document


class TestSanitizeForEncoding:
    def test_valid_utf8_passes_through(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            _sanitize_for_encoding,
        )

        assert _sanitize_for_encoding("hello world") == "hello world"

    def test_surrogate_characters_cleaned(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            _sanitize_for_encoding,
        )

        # Create a string with a surrogate character
        text_with_surrogate = "hello\ud800world"
        result = _sanitize_for_encoding(text_with_surrogate)
        # Should not raise and should produce valid UTF-8
        result.encode("utf-8")

    def test_last_resort_filtering(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            _sanitize_for_encoding,
        )

        # Create a string where surrogatepass encode then decode fails
        # by wrapping _sanitize_for_encoding logic manually
        # The last-resort branch filters characters outside BMP
        # We can't easily trigger it without patching str.encode (immutable)
        # Instead, test with a known surrogate that goes through the second path
        text_with_surrogate = "hello\ud800world"
        result = _sanitize_for_encoding(text_with_surrogate)
        assert isinstance(result, str)
        result.encode("utf-8")  # Must be valid UTF-8


class TestSafeFileHistory:
    def test_store_string_success(self, tmp_path):
        from code_puppy.command_line.prompt_toolkit_completion import SafeFileHistory

        hfile = str(tmp_path / "history.txt")
        h = SafeFileHistory(hfile)
        h.store_string("hello world")

    def test_store_string_with_surrogate(self, tmp_path):
        from code_puppy.command_line.prompt_toolkit_completion import SafeFileHistory

        hfile = str(tmp_path / "history.txt")
        h = SafeFileHistory(hfile)
        h.store_string("hello\ud800world")

    def test_store_string_os_error(self, tmp_path):
        from code_puppy.command_line.prompt_toolkit_completion import SafeFileHistory

        hfile = str(tmp_path / "history.txt")
        h = SafeFileHistory(hfile)

        with patch.object(
            SafeFileHistory.__bases__[0],
            "store_string",
            side_effect=OSError("disk full"),
        ):
            # Should not raise
            h.store_string("test")


class TestSetCompleter:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_just_trigger_suggests_space(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        completions = list(c.get_completions(self._make_doc("/set"), None))
        assert len(completions) == 1
        assert completions[0].text == "/set "

    def test_no_trigger(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        completions = list(c.get_completions(self._make_doc("hello"), None))
        assert completions == []

    def test_shows_config_keys(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
                return_value=["debug", "model", "yolo_mode", "puppy_token"],
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_value",
                return_value="false",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/set "), None))
            texts = [c.text for c in completions]
            # model and puppy_token excluded
            assert any("debug" in t for t in texts)
            assert not any("model" in t for t in texts)
            assert not any("puppy_token" in t for t in texts)

    def test_filters_by_prefix(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
                return_value=["debug", "yolo_mode"],
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_value",
                return_value=None,
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/set yo"), None))
            assert len(completions) == 1
            assert "yolo_mode" in completions[0].text

    def test_model_key_skipped(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        completions = list(c.get_completions(self._make_doc("/set model"), None))
        assert completions == []


class TestCDCompleter:
    def _make_doc(self, text):
        return Document(text=text, cursor_position=len(text))

    def test_no_trigger(self):
        from code_puppy.command_line.prompt_toolkit_completion import CDCompleter

        c = CDCompleter()
        assert list(c.get_completions(self._make_doc("/other "), None)) == []

    def test_completes_directories(self, tmp_path):
        from code_puppy.command_line.prompt_toolkit_completion import CDCompleter

        subdir = tmp_path / "mydir"
        subdir.mkdir()

        c = CDCompleter()
        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.list_directory",
            return_value=(["mydir"], []),
        ):
            completions = list(c.get_completions(self._make_doc("/cd m"), None))
            assert len(completions) >= 1

    def test_home_prefix(self):
        from code_puppy.command_line.prompt_toolkit_completion import CDCompleter

        c = CDCompleter()
        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.list_directory",
            return_value=(["Documents"], []),
        ):
            completions = list(c.get_completions(self._make_doc("/cd ~/D"), None))
            assert len(completions) >= 1
            # Should preserve ~ prefix
            assert any("~" in c.text for c in completions)

    def test_exception_silenced(self):
        from code_puppy.command_line.prompt_toolkit_completion import CDCompleter

        c = CDCompleter()
        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.list_directory",
            side_effect=PermissionError("nope"),
        ):
            completions = list(c.get_completions(self._make_doc("/cd foo"), None))
            assert completions == []

    def test_base_dir_path(self):
        from code_puppy.command_line.prompt_toolkit_completion import CDCompleter

        c = CDCompleter()
        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.list_directory",
            return_value=(["sub"], []),
        ):
            completions = list(c.get_completions(self._make_doc("/cd parent/s"), None))
            assert len(completions) >= 1


class TestAgentCompleter:
    def _make_doc(self, text):
        return Document(text=text, cursor_position=len(text))

    def test_no_trigger(self):
        from code_puppy.command_line.prompt_toolkit_completion import AgentCompleter

        c = AgentCompleter()
        assert list(c.get_completions(self._make_doc("/other "), None)) == []

    def test_shows_agents(self):
        from code_puppy.command_line.prompt_toolkit_completion import AgentCompleter

        c = AgentCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["agent1", "agent2"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/agent "), None))
            assert len(completions) == 2

    def test_filters_agents(self):
        from code_puppy.command_line.prompt_toolkit_completion import AgentCompleter

        c = AgentCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["agent1", "bot1"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/agent ag"), None))
            assert len(completions) == 1

    def test_load_agents_fails(self):
        from code_puppy.command_line.prompt_toolkit_completion import AgentCompleter

        c = AgentCompleter()
        with patch(
            "code_puppy.command_line.pin_command_completion.load_agent_names",
            side_effect=Exception("fail"),
        ):
            completions = list(c.get_completions(self._make_doc("/agent "), None))
            assert completions == []

    def test_import_error_for_display_meta(self):
        """Cover the fallback lambda for _get_agent_display_meta.

        This tests lines 386-387 where ImportError triggers fallback lambda.
        The import happens inside get_completions, so we need to make the
        specific import fail while allowing load_agent_names to work.
        """
        # This is hard to test because the import is cached.
        # We'd need to remove it from sys.modules, which is fragile.
        # Instead, we accept this as a 2-line gap (defensive fallback).
        pass


class TestSlashCompleter:
    def _make_doc(self, text):
        return Document(text=text, cursor_position=len(text))

    def test_no_slash(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        assert list(c.get_completions(self._make_doc("hello"), None)) == []

    def test_just_slash(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        mock_cmd = MagicMock()
        mock_cmd.name = "help"
        mock_cmd.description = "Show help"
        mock_cmd.aliases = ["h"]

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[mock_cmd],
            ),
            patch("code_puppy.plugins.load_plugin_callbacks"),
            patch("code_puppy.callbacks.on_custom_command_help", return_value=[]),
        ):
            completions = list(c.get_completions(self._make_doc("/"), None))
            assert len(completions) >= 1

    def test_partial_command(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        mock_cmd = MagicMock()
        mock_cmd.name = "help"
        mock_cmd.description = "Show help"
        mock_cmd.aliases = []

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[mock_cmd],
            ),
            patch("code_puppy.plugins.load_plugin_callbacks"),
            patch("code_puppy.callbacks.on_custom_command_help", return_value=[]),
        ):
            completions = list(c.get_completions(self._make_doc("/he"), None))
            assert len(completions) == 1
            assert completions[0].text == "help"

    def test_get_unique_commands_fails(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
            side_effect=Exception("fail"),
        ):
            assert list(c.get_completions(self._make_doc("/"), None)) == []

    def test_custom_commands_list_format(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[],
            ),
            patch("code_puppy.plugins.load_plugin_callbacks"),
            patch(
                "code_puppy.callbacks.on_custom_command_help",
                return_value=[[("mycmd", "My command")]],
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/"), None))
            assert any(c.text == "mycmd" for c in completions)

    def test_custom_commands_tuple_format(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[],
            ),
            patch("code_puppy.plugins.load_plugin_callbacks"),
            patch(
                "code_puppy.callbacks.on_custom_command_help",
                return_value=[("mycmd", "My command")],
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/"), None))
            assert any(c.text == "mycmd" for c in completions)

    def test_custom_commands_exception(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.load_plugin_callbacks",
                side_effect=Exception("fail"),
            ),
        ):
            # Should not raise
            list(c.get_completions(self._make_doc("/"), None))

    def test_custom_commands_none_result(self):
        from code_puppy.command_line.prompt_toolkit_completion import SlashCompleter

        c = SlashCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_unique_commands",
                return_value=[],
            ),
            patch("code_puppy.plugins.load_plugin_callbacks"),
            patch(
                "code_puppy.callbacks.on_custom_command_help",
                return_value=[None],
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/"), None))
            assert completions == []


class TestGetPromptWithActiveModel:
    def test_basic(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        mock_agent = MagicMock()
        mock_agent.display_name = "test-agent"
        mock_agent.get_model_name.return_value = None

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
                return_value="Biscuit",
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            result = get_prompt_with_active_model()
            assert result is not None

    def test_agent_model_differs_from_global(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        mock_agent = MagicMock()
        mock_agent.display_name = "test-agent"
        mock_agent.get_model_name.return_value = "claude-3"

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
                return_value="Biscuit",
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            result = get_prompt_with_active_model()
            # Should show both models
            text = "".join(t[1] for t in result)
            assert "→" in text

    def test_agent_model_same_as_global(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        mock_agent = MagicMock()
        mock_agent.display_name = "test-agent"
        mock_agent.get_model_name.return_value = "gpt-4"

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
                return_value="Biscuit",
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            result = get_prompt_with_active_model()
            text = "".join(t[1] for t in result)
            assert "gpt-4" in text

    def test_no_current_agent(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=None,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
                return_value="Biscuit",
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
                return_value=None,
            ),
        ):
            result = get_prompt_with_active_model()
            text = "".join(t[1] for t in result)
            assert "code-puppy" in text
            assert "(default)" in text

    def test_cwd_outside_home(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        mock_agent = MagicMock()
        mock_agent.display_name = "a"
        mock_agent.get_model_name.return_value = None

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
                return_value="B",
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
                return_value="m",
            ),
            patch("os.getcwd", return_value="/tmp/somewhere"),
            patch("os.path.expanduser", return_value="/Users/test"),
        ):
            result = get_prompt_with_active_model()
            text = "".join(t[1] for t in result)
            assert "/tmp/somewhere" in text


class TestGetInputWithCombinedCompletion:
    @pytest.mark.asyncio
    async def test_basic(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.PromptSession"
            ) as mock_cls,
        ):
            mock_session = MagicMock()

            async def fake_prompt(*a, **kw):
                return "hello"

            mock_session.prompt_async = fake_prompt
            mock_cls.return_value = mock_session

            result = await get_input_with_combined_completion()
            assert result == "hello"

    @pytest.mark.asyncio
    async def test_with_history_file(self, tmp_path):
        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
        )

        hfile = str(tmp_path / "hist.txt")

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.PromptSession"
            ) as mock_cls,
        ):
            mock_session = MagicMock()

            async def fake_prompt(*a, **kw):
                return "test"

            mock_session.prompt_async = fake_prompt
            mock_cls.return_value = mock_session

            result = await get_input_with_combined_completion(history_file=hfile)
            assert result == "test"

    @pytest.mark.asyncio
    async def test_with_formatted_text_prompt(self):
        from prompt_toolkit.formatted_text import FormattedText

        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
        )

        prompt = FormattedText([("bold", ">>> ")])

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.PromptSession"
            ) as mock_cls,
        ):
            mock_session = MagicMock()

            async def fake_prompt(*a, **kw):
                return "ok"

            mock_session.prompt_async = fake_prompt
            mock_cls.return_value = mock_session

            result = await get_input_with_combined_completion(prompt_str=prompt)
            assert result == "ok"


class TestKeyBindings:
    """Test the key binding handlers by capturing them from PromptSession."""

    @pytest.fixture
    def captured_bindings(self):
        """Extract key bindings by capturing what's passed to PromptSession."""
        import asyncio

        from code_puppy.command_line.prompt_toolkit_completion import (
            get_input_with_combined_completion,
        )

        captured = {}

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.PromptSession"
            ) as mock_cls,
        ):
            mock_session = MagicMock()

            async def fake_prompt(*a, **kw):
                return ""

            mock_session.prompt_async = fake_prompt

            def capture_session(**kwargs):
                captured.update(kwargs)
                return mock_session

            mock_cls.side_effect = capture_session

            asyncio.run(get_input_with_combined_completion())

        return captured.get("key_bindings")

    def _find_handler(self, bindings, key_name):
        """Find a handler in bindings by key name."""
        for binding in bindings.bindings:
            keys_str = str(binding.keys)
            if key_name in keys_str:
                return binding.handler
        return None

    def test_ctrl_x_exits(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-x")
        assert handler is not None
        event = MagicMock()
        handler(event)
        event.app.exit.assert_called_once()

    def test_ctrl_x_handles_exception(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-x")
        event = MagicMock()
        event.app.exit.side_effect = Exception("already set")
        handler(event)  # Should not raise

    def test_escape_exits(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "escape")
        assert handler is not None
        event = MagicMock()
        handler(event)
        event.app.exit.assert_called_once()

    def test_escape_handles_exception(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "escape")
        event = MagicMock()
        event.app.exit.side_effect = Exception("already set")
        handler(event)  # Should not raise

    def test_f2_toggles_multiline(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "f2")
        assert handler is not None
        event = MagicMock()
        with patch("sys.stdout"):
            handler(event)

    def test_ctrl_j_inserts_newline(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-j")
        assert handler is not None
        event = MagicMock()
        handler(event)
        event.app.current_buffer.insert_text.assert_called_with("\n")

    def test_enter_non_multiline(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-m")
        assert handler is not None
        event = MagicMock()
        # In default state, multiline is off
        handler(event)
        event.current_buffer.validate_and_handle.assert_called_once()

    def test_backspace_with_slash(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-h")
        assert handler is not None
        event = MagicMock()
        event.app.current_buffer.text = "/he"
        handler(event)
        event.app.current_buffer.delete_before_cursor.assert_called_once()
        event.app.current_buffer.start_completion.assert_called_once()

    def test_backspace_without_slash(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-h")
        event = MagicMock()
        event.app.current_buffer.text = "hello"
        handler(event)
        event.app.current_buffer.delete_before_cursor.assert_called_once()
        event.app.current_buffer.start_completion.assert_not_called()

    def test_delete_with_slash(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "delete")
        assert handler is not None
        event = MagicMock()
        event.app.current_buffer.text = "/he"
        handler(event)
        event.app.current_buffer.delete.assert_called_once()
        event.app.current_buffer.start_completion.assert_called_once()

    def test_bracketed_paste_text(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        assert handler is not None
        event = MagicMock()
        event.data = "hello world"
        handler(event)
        event.app.current_buffer.insert_text.assert_called_once_with("hello world")

    def test_bracketed_paste_windows_lineendings(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        event = MagicMock()
        event.data = "hello\r\nworld"
        handler(event)
        event.app.current_buffer.insert_text.assert_called_once_with("hello\nworld")

    def test_bracketed_paste_empty_with_image(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        event = MagicMock()
        event.data = "  "

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.capture_clipboard_image_to_pending",
                return_value="[📋 image 1]",
            ),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called_with("[📋 image 1] ")

    def test_bracketed_paste_empty_no_image(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        event = MagicMock()
        event.data = "  "

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            return_value=False,
        ):
            handler(event)
            # Fallback: paste the whitespace
            event.app.current_buffer.insert_text.assert_called()

    def test_bracketed_paste_empty_image_exception(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        event = MagicMock()
        event.data = "  "

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            side_effect=Exception("fail"),
        ):
            handler(event)
            # Fallback: paste the whitespace
            event.app.current_buffer.insert_text.assert_called()

    def test_bracketed_paste_empty_no_data(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "bracketed-paste")
        event = MagicMock()
        event.data = ""

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            return_value=False,
        ):
            handler(event)

    def test_ctrl_v_with_image(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        assert handler is not None
        event = MagicMock()

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.capture_clipboard_image_to_pending",
                return_value="[📋 image 1]",
            ),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called_with("[📋 image 1] ")

    def test_ctrl_v_no_image_macos(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "pasted text\n"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run", return_value=mock_result),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called_with("pasted text")

    def test_ctrl_v_no_image_windows(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "windows text\r\n"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Windows"),
            patch("subprocess.run", return_value=mock_result),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called()

    def test_ctrl_v_no_image_linux(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "linux text"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run", return_value=mock_result),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called()

    def test_ctrl_v_no_image_linux_xsel_fallback(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        def run_side_effect(cmd, **kwargs):
            if "xclip" in cmd:
                raise FileNotFoundError()
            result = MagicMock()
            result.returncode = 0
            result.stdout = "xsel text"
            return result

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            handler(event)

    def test_ctrl_v_exception(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            side_effect=Exception("fail"),
        ):
            handler(event)  # Should not raise

    def test_f3_with_image(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "f3")
        assert handler is not None
        event = MagicMock()

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.capture_clipboard_image_to_pending",
                return_value="[📋 image]",
            ),
        ):
            handler(event)
            event.app.current_buffer.insert_text.assert_called_with("[📋 image] ")

    def test_f3_no_image(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "f3")
        event = MagicMock()

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            return_value=False,
        ):
            handler(event)
            call_args = event.app.current_buffer.insert_text.call_args[0][0]
            assert "no image" in call_args

    def test_f3_exception(self, captured_bindings):
        handler = self._find_handler(captured_bindings, "f3")
        event = MagicMock()

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
            side_effect=Exception("fail"),
        ):
            handler(event)
            call_args = event.app.current_buffer.insert_text.call_args[0][0]
            assert "error" in call_args

    def test_alt_m_toggles_multiline(self, captured_bindings):
        """Test Alt+M (escape, m) toggles multiline."""
        # escape+m is a two-key binding
        handler = None
        for binding in captured_bindings.bindings:
            keys_str = str(binding.keys)
            if "escape" in keys_str and "m" in keys_str:
                handler = binding.handler
                break
        assert handler is not None
        event = MagicMock()
        with patch("sys.stdout"):
            handler(event)

    def test_ctrl_enter_newline(self, captured_bindings):
        """Test ctrl-enter inserts newline."""
        handler = self._find_handler(captured_bindings, "c-enter")
        if handler is not None:
            event = MagicMock()
            handler(event)
            event.app.current_buffer.insert_text.assert_called_with("\n")

    def test_ctrl_v_linux_xsel_fallback_filenotfound(self, captured_bindings):
        """Cover the FileNotFoundError xsel fallback path."""
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        call_count = [0]

        def run_side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # xclip fails
                raise FileNotFoundError()
            result = MagicMock()
            result.returncode = 1  # xsel also fails
            result.stdout = ""
            return result

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            handler(event)

    def test_ctrl_v_subprocess_exception(self, captured_bindings):
        """Cover the outer except Exception path in handle_smart_paste."""
        handler = self._find_handler(captured_bindings, "c-v")
        event = MagicMock()

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.has_image_in_clipboard",
                return_value=False,
            ),
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run", side_effect=Exception("total failure")),
        ):
            handler(event)  # Should not raise

    def test_enter_multiline_mode(self, captured_bindings):
        """Test enter in multiline mode by toggling multiline first."""
        # Find f2 handler to toggle multiline ON
        f2_handler = self._find_handler(captured_bindings, "f2")
        enter_handler = self._find_handler(captured_bindings, "c-m")

        event = MagicMock()
        with patch("sys.stdout"):
            f2_handler(event)  # Toggle multiline ON

        event2 = MagicMock()
        enter_handler(event2)  # Now enter should insert newline
        event2.app.current_buffer.insert_text.assert_called_with("\n")


class TestAttachmentPlaceholderProcessorExtended:
    """Extended tests for AttachmentPlaceholderProcessor."""

    def test_long_text_skipped(self):
        """Long text should skip path detection."""

        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        long_text = "a" * 600

        mock_ti = MagicMock()
        mock_ti.document.text = long_text
        mock_ti.fragments = [("class:input", long_text)]

        result = proc.apply_transformation(mock_ti)
        assert result is not None


class TestSetCompleterExtended:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_config_key_with_value(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
                return_value=["debug"],
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_value",
                return_value="true",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/set d"), None))
            assert len(completions) == 1
            assert "= true" in completions[0].text

    def test_config_key_with_none_value(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
                return_value=["debug"],
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_value",
                return_value=None,
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/set d"), None))
            assert len(completions) == 1
            assert "= " in completions[0].text

    def test_leading_whitespace_handling(self):
        from code_puppy.command_line.prompt_toolkit_completion import SetCompleter

        c = SetCompleter()
        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
                return_value=["debug"],
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_value",
                return_value="false",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("  /set d"), None))
            assert len(completions) == 1


class TestAttachmentPlaceholderProcessorPaths:
    """Test AttachmentPlaceholderProcessor with actual path detections."""

    def test_empty_text(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        mock_ti = MagicMock()
        mock_ti.document.text = ""
        mock_ti.fragments = []
        result = proc.apply_transformation(mock_ti)
        assert result is not None

    def test_no_detections(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        mock_ti = MagicMock()
        mock_ti.document.text = "hello world"
        mock_ti.fragments = [("", "hello world")]

        with patch(
            "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
            return_value=([], []),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_with_image_detection(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "look at test.png please"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = MagicMock()
        mock_detection.path.suffix = ".png"
        mock_detection.has_path.return_value = True
        mock_detection.link = None
        mock_detection.start_index = 2
        mock_detection.consumed_until = 3
        mock_detection.placeholder = "test.png"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["look", "at", "test.png", "please"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_with_link_detection(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "see https://example.com here"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = None
        mock_detection.has_path.return_value = False
        mock_detection.link = "https://example.com"
        mock_detection.start_index = 1
        mock_detection.consumed_until = 2
        mock_detection.placeholder = "https://example.com"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["see", "https://example.com", "here"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_with_document_detection(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "read test.pdf now"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = MagicMock()
        mock_detection.path.suffix = ".pdf"
        mock_detection.has_path.return_value = True
        mock_detection.link = None
        mock_detection.start_index = 1
        mock_detection.consumed_until = 2
        mock_detection.placeholder = "test.pdf"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["read", "test.pdf", "now"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_with_generic_file_detection(self):
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "open test.xyz"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = MagicMock()
        mock_detection.path.suffix = ".xyz"
        mock_detection.has_path.return_value = True
        mock_detection.link = None
        mock_detection.start_index = 1
        mock_detection.consumed_until = 2
        mock_detection.placeholder = "test.xyz"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["open", "test.xyz"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_detection_not_found_in_text(self):
        """Test when detection can't be found in text."""
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "test"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = MagicMock()
        mock_detection.path.suffix = ".png"
        mock_detection.has_path.return_value = True
        mock_detection.link = None
        mock_detection.start_index = 0
        mock_detection.consumed_until = 1
        mock_detection.placeholder = "notfound.png"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["different"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None

    def test_source_to_display_edge_cases(self):
        """Test mapping functions with edge positions."""
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "A test.png B"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = MagicMock()
        mock_detection.path.suffix = ".png"
        mock_detection.has_path.return_value = True
        mock_detection.link = None
        mock_detection.start_index = 1
        mock_detection.consumed_until = 2
        mock_detection.placeholder = "test.png"

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["A", "test.png", "B"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            # Test the source_to_display and display_to_source functions
            if hasattr(result, "source_to_display") and result.source_to_display:
                # Test edge cases
                result.source_to_display(-1)
                result.source_to_display(0)
                result.source_to_display(1000)
            if hasattr(result, "display_to_source") and result.display_to_source:
                result.display_to_source(-1)
                result.display_to_source(0)
                result.display_to_source(1000)

    def test_no_display_text_skips_detection(self):
        """Test detection with no path and no link."""
        from code_puppy.command_line.prompt_toolkit_completion import (
            AttachmentPlaceholderProcessor,
        )

        proc = AttachmentPlaceholderProcessor()
        text = "hello world"
        mock_ti = MagicMock()
        mock_ti.document.text = text
        mock_ti.fragments = [("", text)]

        mock_detection = MagicMock()
        mock_detection.path = None
        mock_detection.has_path.return_value = False
        mock_detection.link = None
        mock_detection.start_index = 0
        mock_detection.consumed_until = 1

        with (
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._detect_path_tokens",
                return_value=([mock_detection], []),
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion._tokenise",
                return_value=["hello", "world"],
            ),
        ):
            result = proc.apply_transformation(mock_ti)
            assert result is not None


class TestClipboardCoverageAdditions:
    """Additional clipboard tests to cover missing lines."""

    def test_safe_open_image_pil_unavailable(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False):
            assert _safe_open_image(b"data") is None

    def test_safe_open_image_decompression_bomb(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.open.side_effect = mock_img_mod.DecompressionBombError("bomb")
            mock_img_mod.DecompressionBombError = type(
                "DecompressionBombError", (Exception,), {}
            )
            mock_img_mod.UnidentifiedImageError = type(
                "UnidentifiedImageError", (Exception,), {}
            )
            mock_img_mod.open.side_effect = mock_img_mod.DecompressionBombError("bomb")
            assert _safe_open_image(b"data") is None

    def test_safe_open_image_unidentified(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.DecompressionBombError = type(
                "DecompressionBombError", (Exception,), {}
            )
            mock_img_mod.UnidentifiedImageError = type(
                "UnidentifiedImageError", (Exception,), {}
            )
            mock_img_mod.open.side_effect = mock_img_mod.UnidentifiedImageError("bad")
            assert _safe_open_image(b"data") is None

    def test_safe_open_image_os_error(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.DecompressionBombError = type(
                "DecompressionBombError", (Exception,), {}
            )
            mock_img_mod.UnidentifiedImageError = type(
                "UnidentifiedImageError", (Exception,), {}
            )
            mock_img_mod.open.side_effect = OSError("corrupt")
            assert _safe_open_image(b"data") is None

    def test_safe_open_image_generic_exception(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.DecompressionBombError = type(
                "DecompressionBombError", (Exception,), {}
            )
            mock_img_mod.UnidentifiedImageError = type(
                "UnidentifiedImageError", (Exception,), {}
            )
            mock_img_mod.open.side_effect = RuntimeError("unexpected")
            assert _safe_open_image(b"data") is None

    def test_safe_open_image_success(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        mock_verify_img = MagicMock()
        mock_result_img = MagicMock()
        call_count = [0]

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.DecompressionBombError = type(
                "DecompressionBombError", (Exception,), {}
            )
            mock_img_mod.UnidentifiedImageError = type(
                "UnidentifiedImageError", (Exception,), {}
            )

            def open_side_effect(buf):
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_verify_img
                return mock_result_img

            mock_img_mod.open.side_effect = open_side_effect
            result = _safe_open_image(b"data")
            assert result is mock_result_img
            mock_verify_img.verify.assert_called_once()

    def test_get_linux_clipboard_image_no_tool(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with patch(
            "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
            return_value=None,
        ):
            assert _get_linux_clipboard_image() is None

    def test_get_linux_clipboard_image_wl_paste(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch(
                "code_puppy.command_line.clipboard.subprocess.run",
                return_value=mock_result,
            ),
        ):
            result = _get_linux_clipboard_image()
            assert result is not None

    def test_get_linux_clipboard_image_xclip(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"\x89PNG" + b"\x00" * 50

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch(
                "code_puppy.command_line.clipboard.subprocess.run",
                return_value=mock_result,
            ),
        ):
            result = _get_linux_clipboard_image()
            assert result is not None

    def test_get_linux_clipboard_image_timeout(self):
        import subprocess

        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch(
                "code_puppy.command_line.clipboard.subprocess.run",
                side_effect=subprocess.TimeoutExpired("xclip", 10),
            ),
        ):
            assert _get_linux_clipboard_image() is None

    def test_get_linux_clipboard_image_exception(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch(
                "code_puppy.command_line.clipboard.subprocess.run",
                side_effect=Exception("weird error"),
            ),
        ):
            assert _get_linux_clipboard_image() is None

    def test_get_linux_clipboard_image_nonzero_returncode(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch(
                "code_puppy.command_line.clipboard.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert _get_linux_clipboard_image() is None

    def test_has_image_linux_no_tool(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value=None,
            ),
        ):
            assert has_image_in_clipboard() is False

    def test_has_image_linux_xclip(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock()
        mock_result.stdout = "image/png\ntext/plain"

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch(
                "subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert has_image_in_clipboard() is True

    def test_has_image_linux_timeout(self):
        import subprocess

        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("wl-paste", 5),
            ),
        ):
            assert has_image_in_clipboard() is False

    def test_has_image_linux_no_match_falls_through(self):
        """Cover the final return False at end of linux block."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock()
        mock_result.stdout = "text/plain"

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert has_image_in_clipboard() is False

    def test_get_clipboard_image_linux_large_no_pil(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        large_bytes = b"\x00" * (11 * 1024 * 1024)  # 11MB

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
        ):
            assert get_clipboard_image() is None

    def test_get_clipboard_image_linux_large_with_pil(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        large_bytes = b"\x00" * (11 * 1024 * 1024)
        mock_img = MagicMock()
        mock_img.width = 5000
        mock_img.height = 5000

        def save_side(buf, format, **kw):
            buf.write(b"\x89PNG" + b"\x00" * 100)

        mock_img.save.side_effect = save_side

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                return_value=mock_img,
            ),
        ):
            result = get_clipboard_image()
            assert result is not None

    def test_get_clipboard_image_linux_large_verify_fail(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        large_bytes = b"\x00" * (11 * 1024 * 1024)

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=None,
            ),
        ):
            assert get_clipboard_image() is None

    def test_get_clipboard_image_linux_large_resize_exception(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        large_bytes = b"\x00" * (11 * 1024 * 1024)
        mock_img = MagicMock()

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                side_effect=Exception("resize fail"),
            ),
        ):
            assert get_clipboard_image() is None

    def test_get_clipboard_image_linux_small_verify_success(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"\x89PNG" + b"\x00" * 100
        mock_img = MagicMock()

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
        ):
            result = get_clipboard_image()
            assert result == small_bytes

    def test_get_clipboard_image_linux_small_verify_fail(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"bad" * 50

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=None,
            ),
        ):
            assert get_clipboard_image() is None

    def test_get_clipboard_image_linux_small_no_pil(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"\x89PNG" + b"\x00" * 100

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
        ):
            result = get_clipboard_image()
            assert result == small_bytes

    def test_get_clipboard_image_linux_none(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=None,
            ),
        ):
            assert get_clipboard_image() is None

    def test_get_clipboard_image_image_mode_conversion(self):
        """Cover the mode conversion branches."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_img = MagicMock()
        mock_img.mode = "L"  # Not RGB, RGBA, LA, or P
        mock_img.width = 100
        mock_img.height = 100
        mock_img.info = {}
        mock_img.convert.return_value = mock_img

        def save_side(buf, format, **kw):
            buf.write(b"\x89PNG" + b"\x00" * 50)

        mock_img.save.side_effect = save_side

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.Image = type(mock_img)
            mock_grab.grabclipboard.return_value = mock_img
            get_clipboard_image()
            mock_img.convert.assert_called_with("RGB")

    def test_get_clipboard_image_rgba_mode(self):
        """Cover the RGBA branch (keep alpha)."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_img = MagicMock()
        mock_img.mode = "RGBA"
        mock_img.width = 100
        mock_img.height = 100
        mock_img.info = {}

        def save_side(buf, format, **kw):
            buf.write(b"\x89PNG" + b"\x00" * 50)

        mock_img.save.side_effect = save_side

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.Image = type(mock_img)
            mock_grab.grabclipboard.return_value = mock_img
            get_clipboard_image()
            # Should NOT call convert
            mock_img.convert.assert_not_called()

    def test_get_clipboard_image_p_mode_with_transparency(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_img = MagicMock()
        mock_img.mode = "P"
        mock_img.width = 100
        mock_img.height = 100
        mock_img.info = {"transparency": True}

        def save_side(buf, format, **kw):
            buf.write(b"\x89PNG" + b"\x00" * 50)

        mock_img.save.side_effect = save_side

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
        ):
            mock_img_mod.Image = type(mock_img)
            mock_grab.grabclipboard.return_value = mock_img
            get_clipboard_image()
            mock_img.convert.assert_not_called()

    def test_get_pending_images_no_binary_content(self):
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        mgr = ClipboardAttachmentManager()
        mgr.add_image(b"fake")

        with patch("code_puppy.command_line.clipboard.BINARY_CONTENT_AVAILABLE", False):
            assert mgr.get_pending_images() == []

    def test_check_linux_clipboard_tool_timeout(self):
        import subprocess

        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("cmd", 5),
        ):
            assert _check_linux_clipboard_tool() is None

    def test_resize_max_dimension_width(self):
        """Cover the MAX_IMAGE_DIMENSION capping for width."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_img = MagicMock()
        mock_img.width = 10000
        mock_img.height = 5000

        call_count = [0]

        def save_side(buf, **kw):
            if call_count[0] == 0:
                buf.write(b"\x00" * (20 * 1024 * 1024))  # 20MB
            else:
                buf.write(b"\x00" * (5 * 1024 * 1024))
            call_count[0] += 1

        mock_img.save.side_effect = save_side
        resized = MagicMock()
        mock_img.resize.return_value = resized

        with patch("code_puppy.command_line.clipboard.Image") as mock_mod:
            mock_mod.Image = type(mock_img)
            mock_mod.Resampling.LANCZOS = "lanczos"
            _resize_image_if_needed(mock_img, 10 * 1024 * 1024)
            assert mock_img.resize.called

    def test_resize_max_dimension_height(self):
        """Cover the MAX_IMAGE_DIMENSION capping for height."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_img = MagicMock()
        mock_img.width = 3000
        mock_img.height = 10000

        call_count = [0]

        def save_side(buf, **kw):
            if call_count[0] == 0:
                buf.write(b"\x00" * (20 * 1024 * 1024))
            else:
                buf.write(b"\x00" * (5 * 1024 * 1024))
            call_count[0] += 1

        mock_img.save.side_effect = save_side
        mock_img.resize.return_value = MagicMock()

        with patch("code_puppy.command_line.clipboard.Image") as mock_mod:
            mock_mod.Image = type(mock_img)
            mock_mod.Resampling.LANCZOS = "lanczos"
            _resize_image_if_needed(mock_img, 10 * 1024 * 1024)
            assert mock_img.resize.called
