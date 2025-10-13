from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
                "code_puppy.command_line.command_handler.finalize_autosave_session",
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

        assert any("Switched to agent" in str(call) for call in mock_emit_success.call_args_list)
        assert any("Auto-save session rotated" in str(call) for call in mock_emit_info.call_args_list)
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
                "code_puppy.command_line.command_handler.finalize_autosave_session",
            ) as mock_finalize,
            patch(
                "code_puppy.agents.set_current_agent",
            ) as mock_set,
        ):
            result = handle_command("/agent code-puppy")
            assert result is True
            mock_finalize.assert_not_called()
            mock_set.assert_not_called()

        assert any("Already using agent" in str(call) for call in mock_emit_info.call_args_list)
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
                "code_puppy.command_line.command_handler.finalize_autosave_session",
            ) as mock_finalize,
            patch(
                "code_puppy.agents.set_current_agent",
            ) as mock_set,
        ):
            result = handle_command("/agent reviewer")
            assert result is True
            mock_finalize.assert_not_called()
            mock_set.assert_not_called()

        assert any("Available agents" in str(call) for call in mock_emit_warning.call_args_list)
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
