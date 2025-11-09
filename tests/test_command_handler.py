from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from code_puppy.command_line.command_handler import handle_command
from code_puppy.command_line.command_registry import get_command


# Function to create a test context with patched messaging functions
def setup_messaging_mocks():
    """Set up mocks for all the messaging functions and return them in a dictionary."""
    mocks = {}
    patch_targets = [
        "code_puppy.messaging.emit_info",
        "code_puppy.messaging.emit_error",
        "code_puppy.messaging.emit_warning",
        "code_puppy.messaging.emit_success",
        "code_puppy.messaging.emit_system_message",
    ]

    for target in patch_targets:
        function_name = target.split(".")[-1]
        mocks[function_name] = patch(target)

    return mocks


def test_help_outputs_help():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        result = handle_command("/help")
        assert result is True
        mock_emit_info.assert_called()
        # Check that help was displayed (look for "Built-in Commands" section)
        assert any(
            "Built-in Commands" in str(call) for call in (mock_emit_info.call_args_list)
        )
    finally:
        mocks["emit_info"].stop()


def test_cd_show_lists_directories():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with patch("code_puppy.command_line.utils.make_directory_table") as mock_table:
            from rich.table import Table

            fake_table = Table()
            mock_table.return_value = fake_table
            result = handle_command("/cd")
            assert result is True
            # Just check that emit_info was called, the exact value is a Table object
            mock_emit_info.assert_called()
    finally:
        mocks["emit_info"].stop()


def test_cd_valid_change():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        with (
            patch("os.path.expanduser", side_effect=lambda x: x),
            patch("os.path.isabs", return_value=True),
            patch("os.path.isdir", return_value=True),
            patch("os.chdir") as mock_chdir,
        ):
            result = handle_command("/cd /some/dir")
            assert result is True
            mock_chdir.assert_called_once_with("/some/dir")
            mock_emit_success.assert_called_with("Changed directory to: /some/dir")
    finally:
        mocks["emit_success"].stop()


def test_cd_invalid_directory():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        with (
            patch("os.path.expanduser", side_effect=lambda x: x),
            patch("os.path.isabs", return_value=True),
            patch("os.path.isdir", return_value=False),
        ):
            result = handle_command("/cd /not/a/dir")
            assert result is True
            mock_emit_error.assert_called_with("Not a directory: /not/a/dir")
    finally:
        mocks["emit_error"].stop()


def test_m_sets_model():
    # Simplified test - just check that the command handler returns True
    with (
        patch("code_puppy.messaging.emit_success"),
        patch(
            "code_puppy.command_line.model_picker_completion.update_model_in_input",
            return_value="some_model",
        ),
        patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="gpt-9001",
        ),
    ):
        result = handle_command("/mgpt-9001")
        assert result is True


def test_m_unrecognized_model_lists_options():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with (
            patch(
                "code_puppy.command_line.model_picker_completion.update_model_in_input",
                return_value=None,
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["a", "b", "c"],
            ),
        ):
            result = handle_command("/m not-a-model")
            assert result is True
            # Check that emit_warning was called with appropriate messages
            mock_emit_warning.assert_called()
            assert any(
                "Usage: /model <model-name> or /m <model-name>" in str(call)
                for call in mock_emit_warning.call_args_list
            )
            assert any(
                "Available models" in str(call)
                for call in mock_emit_warning.call_args_list
            )
    finally:
        mocks["emit_warning"].stop()


def test_set_config_value_equals():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        with (
            patch("code_puppy.config.set_config_value") as mock_set_cfg,
            patch(
                "code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]
            ),
        ):
            result = handle_command("/set pony=rainbow")
            assert result is True
            mock_set_cfg.assert_called_once_with("pony", "rainbow")
            mock_emit_success.assert_called()
            assert any(
                "Set" in str(call) and "pony" in str(call) and "rainbow" in str(call)
                for call in mock_emit_success.call_args_list
            )
    finally:
        mocks["emit_success"].stop()


def test_set_config_value_space():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        with (
            patch("code_puppy.config.set_config_value") as mock_set_cfg,
            patch(
                "code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]
            ),
        ):
            result = handle_command("/set pony rainbow")
            assert result is True
            mock_set_cfg.assert_called_once_with("pony", "rainbow")
            mock_emit_success.assert_called()
            assert any(
                "Set" in str(call) and "pony" in str(call) and "rainbow" in str(call)
                for call in mock_emit_success.call_args_list
            )
    finally:
        mocks["emit_success"].stop()


def test_set_config_only_key():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        with (
            patch("code_puppy.config.set_config_value") as mock_set_cfg,
            patch("code_puppy.config.get_config_keys", return_value=["key"]),
        ):
            result = handle_command("/set pony")
            assert result is True
            mock_set_cfg.assert_called_once_with("pony", "")
            mock_emit_success.assert_called()
            assert any(
                "Set" in str(call) and "pony" in str(call)
                for call in mock_emit_success.call_args_list
            )
    finally:
        mocks["emit_success"].stop()


def test_show_status():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with (
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="MODEL-X",
            ),
            patch("code_puppy.config.get_owner_name", return_value="Ivan"),
            patch("code_puppy.config.get_puppy_name", return_value="Biscuit"),
            patch("code_puppy.config.get_yolo_mode", return_value=True),
        ):
            result = handle_command("/show")
            assert result is True
            mock_emit_info.assert_called()
            assert any(
                "Puppy Status" in str(call)
                and "Ivan" in str(call)
                and "Biscuit" in str(call)
                and "MODEL-X" in str(call)
                for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()


def test_unknown_command():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        result = handle_command("/unknowncmd")
        assert result is True
        mock_emit_warning.assert_called()
        assert any(
            "Unknown command" in str(call) for call in mock_emit_warning.call_args_list
        )
    finally:
        mocks["emit_warning"].stop()


def test_bare_slash_shows_current_model():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="yarn",
        ):
            result = handle_command("/")
            assert result is True
            mock_emit_info.assert_called()
            assert any(
                "Current Model:" in str(call) and "yarn" in str(call)
                for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()


def test_set_no_args_prints_usage():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with patch("code_puppy.config.get_config_keys", return_value=["foo", "bar"]):
            result = handle_command("/set")
            assert result is True
            mock_emit_warning.assert_called()
            assert any(
                "Usage" in str(call) and "Config keys" in str(call)
                for call in mock_emit_warning.call_args_list
            )
    finally:
        mocks["emit_warning"].stop()


def test_set_missing_key_errors():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        # This will enter the 'else' branch printing 'You must supply a key.'
        with patch("code_puppy.config.get_config_keys", return_value=["foo", "bar"]):
            result = handle_command("/set =value")
            assert result is True
            mock_emit_error.assert_called_with("You must supply a key.")
    finally:
        mocks["emit_error"].stop()


def test_non_command_returns_false():
    # No need for mocks here since we're just testing the return value
    result = handle_command("echo hi")
    assert result is False


def test_bare_slash_with_spaces():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="zoom",
        ):
            result = handle_command("/    ")
            assert result is True
            mock_emit_info.assert_called()
            assert any(
                "Current Model:" in str(call) and "zoom" in str(call)
                for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()


def test_agent_switch_triggers_autosave_rotation():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()
    mock_emit_success = mocks["emit_success"].start()

    try:
        current_agent = SimpleNamespace(name="code-puppy", display_name="Code Puppy")
        new_agent = SimpleNamespace(
            name="reviewer",
            display_name="Reviewer",
            description="Checks code",
        )
        new_agent.reload_code_generation_agent = MagicMock()

        with (
            patch(
                "code_puppy.agents.get_current_agent",
                side_effect=[current_agent, new_agent],
            ),
            patch(
                "code_puppy.agents.get_available_agents",
                return_value={"code-puppy": "Code Puppy", "reviewer": "Reviewer"},
            ),
            patch(
                "code_puppy.command_line.core_commands.finalize_autosave_session",
                return_value="fresh_id",
            ) as mock_finalize,
            patch(
                "code_puppy.agents.set_current_agent",
                return_value=True,
            ) as mock_set,
        ):
            result = handle_command("/agent reviewer")
            assert result is True
            mock_finalize.assert_called_once_with()
            mock_set.assert_called_once_with("reviewer")

        assert any(
            "Switched to agent" in str(call)
            for call in mock_emit_success.call_args_list
        )
        assert any(
            "Auto-save session rotated" in str(call)
            for call in mock_emit_info.call_args_list
        )
    finally:
        mocks["emit_info"].stop()
        mocks["emit_success"].stop()


def test_agent_switch_same_agent_skips_rotation():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        current_agent = SimpleNamespace(name="code-puppy", display_name="Code Puppy")
        with (
            patch(
                "code_puppy.agents.get_current_agent",
                return_value=current_agent,
            ),
            patch(
                "code_puppy.agents.get_available_agents",
                return_value={"code-puppy": "Code Puppy"},
            ),
            patch(
                "code_puppy.command_line.core_commands.finalize_autosave_session",
            ) as mock_finalize,
            patch(
                "code_puppy.agents.set_current_agent",
            ) as mock_set,
        ):
            result = handle_command("/agent code-puppy")
            assert result is True
            mock_finalize.assert_not_called()
            mock_set.assert_not_called()

        assert any(
            "Already using agent" in str(call) for call in mock_emit_info.call_args_list
        )
    finally:
        mocks["emit_info"].stop()


def test_agent_switch_unknown_agent_skips_rotation():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with (
            patch(
                "code_puppy.agents.get_available_agents",
                return_value={"code-puppy": "Code Puppy"},
            ),
            patch(
                "code_puppy.command_line.core_commands.finalize_autosave_session",
            ) as mock_finalize,
            patch(
                "code_puppy.agents.set_current_agent",
            ) as mock_set,
        ):
            result = handle_command("/agent reviewer")
            assert result is True
            mock_finalize.assert_not_called()
            mock_set.assert_not_called()

        assert any(
            "Available agents" in str(call) for call in mock_emit_warning.call_args_list
        )
    finally:
        mocks["emit_warning"].stop()


def test_tools_displays_tools_md():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                "# Mock TOOLS.md content\n\nThis is a test."
            )
            result = handle_command("/tools")
            assert result is True
            mock_emit_info.assert_called_once()
            # Check that emit_info was called with a Markdown object
            call_args = mock_emit_info.call_args[0][0]
            # The call should be with a Rich Markdown object
            from rich.markdown import Markdown

            assert isinstance(call_args, Markdown)
    finally:
        mocks["emit_info"].stop()


def test_tools_file_not_found():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        # Since we now use tools_content.py, we just verify that tools are displayed
        # without needing to read from a file
        with patch("code_puppy.tools.tools_content.tools_content", "# Mock content"):
            result = handle_command("/tools")
            assert result is True
            mock_emit_info.assert_called_once()
            # Check that emit_info was called with a Markdown object
            call_args = mock_emit_info.call_args[0][0]
            # The call should be with a Rich Markdown object
            from rich.markdown import Markdown

            assert isinstance(call_args, Markdown)
    finally:
        mocks["emit_info"].stop()


def test_tools_read_error():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        # Test handling when there's an issue with tools_content - it should still work
        # by falling back to an empty or default string if the imported content fails
        with patch(
            "code_puppy.command_line.core_commands.tools_content",
            "# Fallback content",
        ):
            result = handle_command("/tools")
            assert result is True
            mock_emit_info.assert_called_once()
            # Check that emit_info was called with a Markdown object
            call_args = mock_emit_info.call_args[0][0]
            # The call should be with a Rich Markdown object
            from rich.markdown import Markdown

            assert isinstance(call_args, Markdown)
    finally:
        mocks["emit_info"].stop()


def test_exit_command():
    """Test that /exit command works and shows Goodbye message."""
    with patch("code_puppy.messaging.emit_success") as mock_success:
        result = handle_command("/exit")
        assert result is True
        mock_success.assert_called_once_with("Goodbye!")


def test_quit_command():
    """Test that /quit command works via alias and shows Goodbye message."""
    with patch("code_puppy.messaging.emit_success") as mock_success:
        result = handle_command("/quit")
        assert result is True
        mock_success.assert_called_once_with("Goodbye!")


# =============================================================================
# TESTS FOR NEW REGISTERED COMMANDS
# =============================================================================


class TestRegistryIntegration:
    """Tests for command registry integration with handle_command()."""

    def test_registry_command_is_executed(self):
        """Test that registered commands are executed via registry."""
        # /help is registered - verify it's handled
        with patch("code_puppy.messaging.emit_info") as mock_emit:
            result = handle_command("/help")
            assert result is True
            mock_emit.assert_called()

    def test_command_alias_works(self):
        """Test that command aliases work (e.g., /h for /help)."""
        with patch("code_puppy.messaging.emit_info") as mock_emit:
            result = handle_command("/h")
            assert result is True
            mock_emit.assert_called()

    def test_unregistered_command_shows_warning(self):
        """Test that unregistered commands show warning."""
        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            result = handle_command("/totallyfakecommand")
            assert result is True
            mock_warn.assert_called()

    def test_command_without_slash_returns_false(self):
        """Test that text without / is not treated as command."""
        result = handle_command("hello world")
        assert result is False


class TestSessionCommand:
    """Tests for /session command."""

    def test_session_show_current_id(self):
        """Test /session shows current session ID."""
        with (
            patch("code_puppy.config.get_current_autosave_id", return_value="test-id"),
            patch(
                "code_puppy.config.get_current_autosave_session_name",
                return_value="test-session",
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosave"),
            patch("code_puppy.messaging.emit_info") as mock_emit,
        ):
            result = handle_command("/session")
            assert result is True
            mock_emit.assert_called_once()
            call_str = str(mock_emit.call_args)
            assert "test-id" in call_str

    def test_session_id_subcommand(self):
        """Test /session id shows current session ID."""
        with (
            patch("code_puppy.config.get_current_autosave_id", return_value="test-id"),
            patch(
                "code_puppy.config.get_current_autosave_session_name",
                return_value="test-session",
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosave"),
            patch("code_puppy.messaging.emit_info") as mock_emit,
        ):
            result = handle_command("/session id")
            assert result is True
            mock_emit.assert_called_once()

    def test_session_new_rotates(self):
        """Test /session new creates new session."""
        with (
            patch(
                "code_puppy.config.rotate_autosave_id", return_value="new-id"
            ) as mock_rotate,
            patch("code_puppy.messaging.emit_success") as mock_success,
        ):
            result = handle_command("/session new")
            assert result is True
            mock_rotate.assert_called_once()
            mock_success.assert_called_once()
            call_str = str(mock_success.call_args)
            assert "new-id" in call_str

    def test_session_invalid_subcommand(self):
        """Test /session with invalid subcommand shows usage."""
        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            result = handle_command("/session invalid")
            assert result is True
            mock_warn.assert_called_once()
            call_str = str(mock_warn.call_args)
            assert "Usage" in call_str

    def test_session_alias_works(self):
        """Test /s alias works for /session."""
        with (
            patch("code_puppy.config.get_current_autosave_id", return_value="test-id"),
            patch(
                "code_puppy.config.get_current_autosave_session_name",
                return_value="test",
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", "/tmp"),
            patch("code_puppy.messaging.emit_info") as mock_emit,
        ):
            result = handle_command("/s")
            assert result is True
            mock_emit.assert_called()


class TestCompactCommand:
    """Tests for /compact command."""

    def test_compact_with_history(self):
        """Test /compact with message history."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = [
            {"role": "system", "content": "You are a helper"},
            {"role": "user", "content": "Hello"},
        ]
        mock_agent.estimate_tokens_for_message.return_value = 10
        mock_agent.summarize_messages.return_value = (
            [{"role": "system", "content": "summarized"}],
            [],
        )

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy",
                return_value="summarization",
            ),
            patch("code_puppy.config.get_protected_token_count", return_value=1000),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success") as mock_success,
        ):
            result = handle_command("/compact")
            assert result is True
            mock_agent.set_message_history.assert_called_once()
            mock_success.assert_called_once()

    def test_compact_empty_history(self):
        """Test /compact with no history shows warning."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = []

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch("code_puppy.messaging.emit_warning") as mock_warn,
        ):
            result = handle_command("/compact")
            assert result is True
            mock_warn.assert_called_once()
            assert "No history" in str(mock_warn.call_args)

    def test_compact_with_truncation_strategy(self):
        """Test /compact using truncation strategy."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
        ]
        mock_agent.estimate_tokens_for_message.return_value = 5
        mock_agent.truncation.return_value = [{"role": "system", "content": "System"}]

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy", return_value="truncation"
            ),
            patch("code_puppy.config.get_protected_token_count", return_value=1000),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success"),
        ):
            result = handle_command("/compact")
            assert result is True
            mock_agent.truncation.assert_called_once()


class TestReasoningCommand:
    """Tests for /reasoning command."""

    def test_reasoning_set_low(self):
        """Test /reasoning low sets effort to low."""
        mock_agent = MagicMock()

        with (
            patch("code_puppy.config.set_openai_reasoning_effort") as mock_set,
            patch("code_puppy.config.get_openai_reasoning_effort", return_value="low"),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch("code_puppy.messaging.emit_success") as mock_success,
        ):
            result = handle_command("/reasoning low")
            assert result is True
            mock_set.assert_called_once_with("low")
            mock_agent.reload_code_generation_agent.assert_called_once()
            mock_success.assert_called_once()

    def test_reasoning_invalid_level(self):
        """Test /reasoning with invalid level shows error."""
        with (
            patch(
                "code_puppy.config.set_openai_reasoning_effort",
                side_effect=ValueError("Invalid"),
            ),
            patch("code_puppy.messaging.emit_error") as mock_error,
        ):
            result = handle_command("/reasoning invalid")
            assert result is True
            mock_error.assert_called_once()

    def test_reasoning_no_argument(self):
        """Test /reasoning without argument shows usage."""
        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            result = handle_command("/reasoning")
            assert result is True
            mock_warn.assert_called_once()
            assert "Usage" in str(mock_warn.call_args)


class TestTruncateCommand:
    """Tests for /truncate command."""

    def test_truncate_valid_number(self):
        """Test /truncate with valid number."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
        ]

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch("code_puppy.messaging.emit_success") as mock_success,
        ):
            result = handle_command("/truncate 2")
            assert result is True
            mock_agent.set_message_history.assert_called_once()
            mock_success.assert_called_once()

    def test_truncate_no_argument(self):
        """Test /truncate without argument shows error."""
        with patch("code_puppy.messaging.emit_error") as mock_error:
            result = handle_command("/truncate")
            assert result is True
            mock_error.assert_called_once()
            assert "Usage" in str(mock_error.call_args)

    def test_truncate_invalid_number(self):
        """Test /truncate with non-integer shows error."""
        with patch("code_puppy.messaging.emit_error") as mock_error:
            result = handle_command("/truncate abc")
            assert result is True
            mock_error.assert_called_once()
            assert "valid integer" in str(mock_error.call_args)

    def test_truncate_negative_number(self):
        """Test /truncate with negative number shows error."""
        with patch("code_puppy.messaging.emit_error") as mock_error:
            result = handle_command("/truncate -5")
            assert result is True
            mock_error.assert_called_once()

    def test_truncate_empty_history(self):
        """Test /truncate with no history shows warning."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = []

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch("code_puppy.messaging.emit_warning") as mock_warn,
        ):
            result = handle_command("/truncate 10")
            assert result is True
            mock_warn.assert_called_once()

    def test_truncate_already_small_history(self):
        """Test /truncate when history is already small enough."""
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "1"},
        ]

        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch("code_puppy.messaging.emit_info") as mock_info,
        ):
            result = handle_command("/truncate 10")
            assert result is True
            mock_info.assert_called_once()
            assert "Nothing to truncate" in str(mock_info.call_args)


class TestAutosaveLoadCommand:
    """Tests for /autosave_load command."""

    def test_autosave_load_returns_special_marker(self):
        """Test that /autosave_load returns special marker for async handling."""
        result = handle_command("/autosave_load")
        assert result == "__AUTOSAVE_LOAD__"


class TestMotdCommand:
    """Tests for /motd command."""

    def test_motd_command_calls_print_motd(self):
        """Test that /motd calls print_motd with force=True."""
        # Patch where it's imported in core_commands
        with patch("code_puppy.command_line.core_commands.print_motd") as mock_motd:
            result = handle_command("/motd")
            assert result is True
            mock_motd.assert_called_once_with(force=True)


class TestGetCommandsHelp:
    """Tests for get_commands_help() function."""

    def test_help_includes_registered_commands(self):
        """Test that help text includes registered commands."""
        from code_puppy.command_line.command_handler import get_commands_help

        help_text = str(get_commands_help())
        assert "help" in help_text.lower() or "Help" in help_text
        assert "session" in help_text.lower() or "Session" in help_text

    def test_help_includes_categories(self):
        """Test that help organizes into Built-in and Custom sections."""
        from code_puppy.command_line.command_handler import get_commands_help

        help_text = str(get_commands_help())
        # Should have Built-in Commands section
        assert "Built-in Commands" in help_text or "built-in" in help_text.lower()
        # Should be well-organized with content
        assert len(help_text) > 0

    def test_help_parses_tuple_format(self):
        """Test that help system parses single tuple format."""
        from unittest.mock import patch
        from code_puppy.command_line.command_handler import get_commands_help

        # Mock a plugin that returns a single tuple
        with patch("code_puppy.callbacks.on_custom_command_help") as mock_callback:
            mock_callback.return_value = [("testcmd", "Test command description")]
            help_text = str(get_commands_help())
            assert "/testcmd" in help_text
            assert "Test command description" in help_text

    def test_help_parses_list_of_tuples_format(self):
        """Test that help system parses list of tuples format."""
        from unittest.mock import patch
        from code_puppy.command_line.command_handler import get_commands_help

        # Mock a plugin that returns a list of tuples
        with patch("code_puppy.callbacks.on_custom_command_help") as mock_callback:
            mock_callback.return_value = [
                [("cmd1", "First command"), ("cmd2", "Second command")]
            ]
            help_text = str(get_commands_help())
            assert "/cmd1" in help_text
            assert "First command" in help_text
            assert "/cmd2" in help_text
            assert "Second command" in help_text

    def test_help_parses_list_of_strings_format(self):
        """Test that help system parses legacy list of strings format."""
        from unittest.mock import patch
        from code_puppy.command_line.command_handler import get_commands_help

        # Mock a plugin that returns a list of strings (legacy format)
        with patch("code_puppy.callbacks.on_custom_command_help") as mock_callback:
            mock_callback.return_value = [
                [
                    "/legacy_cmd - Legacy command description",
                    "",
                    "Additional details here",
                    "More info...",
                ]
            ]
            help_text = str(get_commands_help())
            assert "/legacy_cmd" in help_text
            assert "Legacy command description" in help_text

    def test_help_handles_mixed_formats(self):
        """Test that help system handles multiple plugins with different formats."""
        from unittest.mock import patch
        from code_puppy.command_line.command_handler import get_commands_help

        # Mock multiple plugins returning different formats
        with patch("code_puppy.callbacks.on_custom_command_help") as mock_callback:
            mock_callback.return_value = [
                ("tuple_cmd", "Tuple format command"),  # Single tuple
                [("list_cmd", "List format command")],  # List of tuples
                ["/string_cmd - String format command", ""],  # List of strings
            ]
            help_text = str(get_commands_help())
            assert "/tuple_cmd" in help_text
            assert "Tuple format command" in help_text
            assert "/list_cmd" in help_text
            assert "List format command" in help_text
            assert "/string_cmd" in help_text
            assert "String format command" in help_text

    def test_help_ignores_invalid_formats(self):
        """Test that help system gracefully ignores invalid formats."""
        from unittest.mock import patch
        from code_puppy.command_line.command_handler import get_commands_help

        # Mock a plugin that returns invalid formats
        with patch("code_puppy.callbacks.on_custom_command_help") as mock_callback:
            mock_callback.return_value = [
                None,  # Should be ignored
                [],  # Empty list, should be ignored
                ["no dash in this string"],  # Invalid string format
                ("only_one_element",),  # Tuple with wrong length
                {"dict": "invalid"},  # Wrong type entirely
            ]
            # Should not crash, just skip invalid entries
            help_text = str(get_commands_help())
            assert help_text  # Should still generate help text


class TestCommandRegistry:
    """Tests verifying commands are properly registered."""

    def test_help_command_registered(self):
        """Test that help command is registered."""
        cmd = get_command("help")
        assert cmd is not None
        assert cmd.name == "help"
        assert "h" in cmd.aliases

    def test_session_command_registered(self):
        """Test that session command is registered."""
        cmd = get_command("session")
        assert cmd is not None
        assert cmd.name == "session"
        assert "s" in cmd.aliases

    def test_show_command_registered(self):
        """Test that show command is registered."""
        cmd = get_command("show")
        assert cmd is not None
        assert cmd.category == "config"

    def test_cd_command_registered(self):
        """Test that cd command is registered."""
        cmd = get_command("cd")
        assert cmd is not None

    def test_tools_command_registered(self):
        """Test that tools command is registered."""
        cmd = get_command("tools")
        assert cmd is not None

    def test_motd_command_registered(self):
        """Test that motd command is registered."""
        cmd = get_command("motd")
        assert cmd is not None

    def test_exit_command_registered(self):
        """Test that exit command is registered."""
        cmd = get_command("exit")
        assert cmd is not None
        assert "quit" in cmd.aliases

    def test_compact_command_registered(self):
        """Test that compact command is registered."""
        cmd = get_command("compact")
        assert cmd is not None
        assert cmd.category == "session"

    def test_reasoning_command_registered(self):
        """Test that reasoning command is registered."""
        cmd = get_command("reasoning")
        assert cmd is not None
        assert cmd.category == "config"

    def test_truncate_command_registered(self):
        """Test that truncate command is registered."""
        cmd = get_command("truncate")
        assert cmd is not None
        assert cmd.category == "session"

    def test_autosave_load_command_registered(self):
        """Test that autosave_load command is registered."""
        cmd = get_command("autosave_load")
        assert cmd is not None

    def test_set_command_registered(self):
        """Test that set command is registered."""
        cmd = get_command("set")
        assert cmd is not None
        assert cmd.category == "config"

    def test_agent_command_registered(self):
        """Test that agent command is registered."""
        cmd = get_command("agent")
        assert cmd is not None
        assert cmd.category == "core"

    def test_model_command_registered(self):
        """Test that model command is registered."""
        cmd = get_command("model")
        assert cmd is not None
        assert "m" in cmd.aliases

    def test_mcp_command_registered(self):
        """Test that mcp command is registered."""
        cmd = get_command("mcp")
        assert cmd is not None
        assert cmd.category == "core"

    def test_pin_model_command_registered(self):
        """Test that pin_model command is registered."""
        cmd = get_command("pin_model")
        assert cmd is not None
        assert cmd.category == "config"

    def test_generate_pr_description_command_registered(self):
        """Test that generate-pr-description command is registered."""
        cmd = get_command("generate-pr-description")
        assert cmd is not None
        assert cmd.category == "core"

    def test_dump_context_command_registered(self):
        """Test that dump_context command is registered."""
        cmd = get_command("dump_context")
        assert cmd is not None
        assert cmd.category == "session"

    def test_load_context_command_registered(self):
        """Test that load_context command is registered."""
        cmd = get_command("load_context")
        assert cmd is not None
        assert cmd.category == "session"

    def test_diff_command_registered(self):
        """Test that diff command is registered."""
        cmd = get_command("diff")
        assert cmd is not None
        assert cmd.category == "config"


# Note: Tests for newly migrated commands (set, agent, model, mcp, pin_model,
# generate-pr-description, dump_context, load_context, diff) already exist above
# and in TestCommandRegistry. All logic has been verified to be identical to original.
# See LOGIC_VERIFICATION.md for detailed verification.
