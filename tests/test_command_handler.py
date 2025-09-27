from unittest.mock import patch

from code_puppy.command_line.command_handler import handle_command


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
        assert any(
            "Commands Help" in str(call) for call in (mock_emit_info.call_args_list)
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
        patch("code_puppy.agent.get_code_generation_agent", return_value=None),
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
            "code_puppy.command_line.command_handler.tools_content",
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
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        result = handle_command("/exit")
        assert result is True
        mock_emit_success.assert_called_with("Goodbye!")
    finally:
        mocks["emit_success"].stop()


def test_quit_command():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()

    try:
        result = handle_command("/quit")
        assert result is True
        mock_emit_success.assert_called_with("Goodbye!")
    finally:
        mocks["emit_success"].stop()


def test_truncate_command():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Test with valid number
        with (
            patch(
                "code_puppy.state_management.get_message_history"
            ) as mock_get_history,
            patch(
                "code_puppy.state_management.set_message_history"
            ) as mock_set_history,
        ):
            mock_get_history.return_value = ["msg1", "msg2", "msg3", "msg4", "msg5"]
            result = handle_command("/truncate 3")
            assert result is True
            mock_set_history.assert_called_once()
            # Should keep first message + 2 most recent = 3 total
            call_args = mock_set_history.call_args[0][0]
            assert len(call_args) == 3
            assert call_args[0] == "msg1"  # First message preserved
            assert call_args[1] == "msg4"  # Second most recent
            assert call_args[2] == "msg5"  # Most recent
            mock_emit_success.assert_called_with(
                "Truncated message history from 5 to 3 messages (keeping system message and 2 most recent)"
            )
    finally:
        mocks["emit_success"].stop()
        mocks["emit_warning"].stop()


def test_truncate_command_no_history():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with patch(
            "code_puppy.state_management.get_message_history"
        ) as mock_get_history:
            mock_get_history.return_value = []
            result = handle_command("/truncate 5")
            assert result is True
            mock_emit_warning.assert_called_with(
                "No history to truncate yet. Ask me something first!"
            )
    finally:
        mocks["emit_warning"].stop()


def test_truncate_command_fewer_messages():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        with patch(
            "code_puppy.state_management.get_message_history"
        ) as mock_get_history:
            mock_get_history.return_value = ["msg1", "msg2"]
            result = handle_command("/truncate 5")
            assert result is True
            mock_emit_info.assert_called_with(
                "History already has 2 messages, which is <= 5. Nothing to truncate."
            )
    finally:
        mocks["emit_info"].stop()


def test_truncate_command_invalid_number():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        result = handle_command("/truncate notanumber")
        assert result is True
        mock_emit_error.assert_called_with("N must be a valid integer")
    finally:
        mocks["emit_error"].stop()


def test_truncate_command_negative_number():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        result = handle_command("/truncate -5")
        assert result is True
        mock_emit_error.assert_called_with("N must be a positive integer")
    finally:
        mocks["emit_error"].stop()


def test_truncate_command_no_number():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        result = handle_command("/truncate")
        assert result is True
        mock_emit_error.assert_called_with(
            "Usage: /truncate <N> (where N is the number of messages to keep)"
        )
    finally:
        mocks["emit_error"].stop()
