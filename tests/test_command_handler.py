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
                "Usage:" in str(call) for call in mock_emit_warning.call_args_list
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


def test_undo_command_no_history():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with patch("code_puppy.state_management.get_message_history", return_value=[]):
            result = handle_command("/undo")
            assert result is True
            mock_emit_warning.assert_called_with("No history to undo!")
    finally:
        mocks["emit_warning"].stop()


def test_undo_command_no_prompt():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Mock history with no user messages
        mock_history = [
            type(
                "Message",
                (),
                {
                    "role": "assistant",
                    "parts": [type("Part", (), {"content": "test"})()],
                },
            )()
        ]
        with patch(
            "code_puppy.state_management.get_message_history", return_value=mock_history
        ):
            result = handle_command("/undo")
            assert result is True
            mock_emit_warning.assert_called_with("No prompt found to undo!")
    finally:
        mocks["emit_warning"].stop()


def test_undo_command_single_version():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch(
                "code_puppy.version_store.list_versions",
                return_value=[(1, 1, "2025-01-01T00:00:00")],
            ),
        ):
            result = handle_command("/undo")
            assert result is True
            mock_emit_warning.assert_called_with("No previous version to undo to!")
    finally:
        mocks["emit_warning"].stop()


def test_undo_command_success():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()
    mocks["emit_info"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        # Mock version store functions
        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch(
                "code_puppy.version_store.list_versions",
                return_value=[
                    (1, 1, "2025-01-01T00:00:00"),
                    (2, 2, "2025-01-01T00:01:00"),
                ],
            ),
            patch(
                "code_puppy.version_store.get_response_by_version",
                return_value={
                    "id": 1,
                    "version": 1,
                    "output_text": "test output",
                    "timestamp": "2025-01-01T00:00:00",
                },
            ),
            patch(
                "code_puppy.version_store.get_response_id_for_prompt_version",
                return_value=1,
            ),
            patch(
                "code_puppy.version_store.compute_snapshot_as_of_response_id",
                return_value=[],
            ),
        ):
            result = handle_command("/undo")
            assert result is True
            mock_emit_success.assert_called_with(
                "[bold green]✅ Undone to version 1[/bold green]"
            )
    finally:
        mocks["emit_success"].stop()
        mocks["emit_info"].stop()


def test_redo_command_no_history():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with patch("code_puppy.state_management.get_message_history", return_value=[]):
            result = handle_command("/redo")
            assert result is True
            mock_emit_warning.assert_called_with("No history to redo!")
    finally:
        mocks["emit_warning"].stop()


def test_redo_command_no_tracking():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Mock history with a user message but no version tracking
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        with patch(
            "code_puppy.state_management.get_message_history", return_value=mock_history
        ):
            result = handle_command("/redo")
            assert result is True
            mock_emit_warning.assert_called_with("No redo history available!")
    finally:
        mocks["emit_warning"].stop()


def test_redo_command_no_next_version():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch(
                "code_puppy.command_line.command_handler._current_version_track",
                {"test prompt": 2},
            ),
            patch(
                "code_puppy.version_store.list_versions",
                return_value=[(1, 1, "2025-01-01T00:00:00")],
            ),
        ):
            result = handle_command("/redo")
            assert result is True
            mock_emit_warning.assert_called_with("No version to redo to!")
    finally:
        mocks["emit_warning"].stop()


def test_redo_command_success():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()
    mocks["emit_info"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        # Mock version store functions
        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch(
                "code_puppy.command_line.command_handler._current_version_track",
                {"test prompt": 1},
            ),
            patch(
                "code_puppy.version_store.list_versions",
                return_value=[
                    (1, 1, "2025-01-01T00:00:00"),
                    (2, 2, "2025-01-01T00:01:00"),
                ],
            ),
            patch(
                "code_puppy.version_store.get_response_by_version",
                return_value={
                    "id": 2,
                    "version": 2,
                    "output_text": "test output",
                    "timestamp": "2025-01-01T00:01:00",
                },
            ),
            patch(
                "code_puppy.version_store.get_response_id_for_prompt_version",
                return_value=2,
            ),
            patch(
                "code_puppy.version_store.compute_snapshot_as_of_response_id",
                return_value=[],
            ),
        ):
            result = handle_command("/redo")
            assert result is True
            mock_emit_success.assert_called_with(
                "[bold green]✅ Redone to version 2[/bold green]"
            )
    finally:
        mocks["emit_success"].stop()
        mocks["emit_info"].stop()


def test_checkout_command_invalid_args():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        result = handle_command("/checkout")
        assert result is True
        mock_emit_warning.assert_called_with(
            "Usage: /checkout <response-id> or /checkout prompt <version-number>"
        )
    finally:
        mocks["emit_warning"].stop()


def test_checkout_command_invalid_version():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()

    try:
        result = handle_command("/checkout not-a-number")
        assert result is True
        mock_emit_error.assert_called_with("Version number must be an integer!")
    finally:
        mocks["emit_error"].stop()


def test_checkout_command_no_history():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        with (
            patch("code_puppy.state_management.get_message_history", return_value=[]),
            patch("code_puppy.version_store.get_response_by_id", return_value=None),
        ):
            result = handle_command("/checkout 1")
            assert result is True
            mock_emit_warning.assert_called_with("No history to checkout!")
    finally:
        mocks["emit_warning"].stop()


def test_checkout_command_success():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()
    mocks["emit_info"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        # Mock version store functions
        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch("code_puppy.version_store.get_response_by_id", return_value=None),
            patch(
                "code_puppy.version_store.get_response_by_version",
                return_value={
                    "id": 1,
                    "version": 1,
                    "output_text": "test output",
                    "timestamp": "2025-01-01T00:00:00",
                },
            ),
            patch(
                "code_puppy.version_store.get_response_id_for_prompt_version",
                return_value=1,
            ),
            patch(
                "code_puppy.version_store.compute_snapshot_as_of_response_id",
                return_value=[],
            ),
        ):
            result = handle_command("/checkout 1")
            assert result is True
            mock_emit_success.assert_called_with(
                "[bold green]✅ Checked out version 1[/bold green]"
            )
    finally:
        mocks["emit_success"].stop()
        mocks["emit_info"].stop()


def test_history_command_no_history():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()

    try:
        # Default /history uses versions store; empty returns warning
        with patch("code_puppy.version_store.list_all_versions", return_value=[]):
            result = handle_command("/history")
            assert result is True
            mock_emit_warning.assert_called_with("No versions found!")
    finally:
        mocks["emit_warning"].stop()


def test_history_prompts_current_prompt_success():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        # Mock history with a user message
        mock_user_msg = type(
            "Message",
            (),
            {"role": "user", "parts": [type("Part", (), {"content": "test prompt"})()]},
        )()
        mock_history = [mock_user_msg]

        with (
            patch(
                "code_puppy.state_management.get_message_history",
                return_value=mock_history,
            ),
            patch(
                "code_puppy.version_store.list_versions",
                return_value=[
                    (1, 1, "2025-01-01T00:00:00"),
                    (2, 2, "2025-01-01T00:01:00"),
                ],
            ),
        ):
            result = handle_command("/history prompts")
            assert result is True
            mock_emit_info.assert_called()
            assert any(
                "Version History" in str(call) for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()


def test_history_command_success():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()

    try:
        # Default /history now mirrors /versions
        with (
            patch(
                "code_puppy.version_store.list_all_versions",
                return_value=[
                    (10, "prompt A", 1, "2025-01-01T00:00:00"),
                    (11, "prompt B", 2, "2025-01-01T00:01:00"),
                ],
            ),
        ):
            result = handle_command("/history")
            assert result is True
            mock_emit_info.assert_called()
            # Check that recent versions were displayed
            assert any(
                "Recent Versions" in str(call) for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()
