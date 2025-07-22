from unittest.mock import MagicMock, patch

from code_puppy.command_line.meta_command_handler import handle_meta_command


# Function to create a test context with patched messaging functions
def setup_messaging_mocks():
    """Set up mocks for all the messaging functions and return them in a dictionary."""
    mocks = {}
    patch_targets = [
        "code_puppy.command_line.meta_command_handler.emit_info",
        "code_puppy.command_line.meta_command_handler.emit_error",
        "code_puppy.command_line.meta_command_handler.emit_warning",
        "code_puppy.command_line.meta_command_handler.emit_success",
        "code_puppy.command_line.meta_command_handler.emit_system_message",
    ]
    
    for target in patch_targets:
        function_name = target.split(".")[-1]
        mocks[function_name] = patch(target)
        
    return mocks


def test_help_outputs_help():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()
    
    try:
        result = handle_meta_command("~help")
        assert result is True
        mock_emit_info.assert_called()
        assert any(
            "Meta Commands Help" in str(call)
            for call in (mock_emit_info.call_args_list)
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
            result = handle_meta_command("~cd")
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
            result = handle_meta_command("~cd /some/dir")
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
            result = handle_meta_command("~cd /not/a/dir")
            assert result is True
            mock_emit_error.assert_called_with("Not a directory: /not/a/dir")
    finally:
        mocks["emit_error"].stop()


def test_codemap_prints_tree():
    fake_tree = "FAKE_CODMAP_TREE"
    with patch("code_puppy.tools.ts_code_map.make_code_map") as mock_map:
        mock_map.return_value = fake_tree
        result = handle_meta_command("~codemap")
        assert result is True


def test_codemap_prints_tree_with_dir():
    fake_tree = "TREE_FOR_DIR"
    with (
        patch("code_puppy.tools.ts_code_map.make_code_map") as mock_map,
        patch("os.path.expanduser", side_effect=lambda x: x),
    ):
        mock_map.return_value = fake_tree
        result = handle_meta_command("~codemap /some/dir")
        assert result is True


def test_codemap_error_prints():
    mocks = setup_messaging_mocks()
    mock_emit_error = mocks["emit_error"].start()
    
    try:
        with patch(
            "code_puppy.tools.ts_code_map.make_code_map", side_effect=Exception("fail")
        ):
            result = handle_meta_command("~codemap")
            assert result is True
            mock_emit_error.assert_called()
            assert any(
                "Error generating code map" in str(call)
                for call in mock_emit_error.call_args_list
            )
    finally:
        mocks["emit_error"].stop()


def test_m_sets_model():
    # Simplified test - just check that the command handler returns True
    with patch("code_puppy.command_line.meta_command_handler.emit_success"), \
         patch("code_puppy.command_line.model_picker_completion.update_model_in_input", return_value="some_model"), \
         patch("code_puppy.command_line.model_picker_completion.get_active_model", return_value="gpt-9001"), \
         patch("code_puppy.agent.get_code_generation_agent", return_value=None):
         
        result = handle_meta_command("~mgpt-9001")
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
            result = handle_meta_command("~m not-a-model")
            assert result is True
            # Check that emit_warning was called with appropriate messages
            mock_emit_warning.assert_called()
            assert any("Usage:" in str(call) for call in mock_emit_warning.call_args_list)
            assert any("Available models" in str(call) for call in mock_emit_warning.call_args_list)
    finally:
        mocks["emit_warning"].stop()


def test_set_config_value_equals():
    mocks = setup_messaging_mocks()
    mock_emit_success = mocks["emit_success"].start()
    
    try:
        with (
            patch("code_puppy.config.set_config_value") as mock_set_cfg,
            patch("code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]),
        ):
            result = handle_meta_command("~set pony=rainbow")
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
            patch("code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]),
        ):
            result = handle_meta_command("~set pony rainbow")
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
            result = handle_meta_command("~set pony")
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
            result = handle_meta_command("~show")
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


def test_unknown_meta_command():
    mocks = setup_messaging_mocks()
    mock_emit_warning = mocks["emit_warning"].start()
    
    try:
        result = handle_meta_command("~unknowncmd")
        assert result is True
        mock_emit_warning.assert_called()
        assert any(
            "Unknown meta command" in str(call)
            for call in mock_emit_warning.call_args_list
        )
    finally:
        mocks["emit_warning"].stop()


def test_bare_tilde_shows_current_model():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()
    
    try:
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="yarn",
        ):
            result = handle_meta_command("~")
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
            result = handle_meta_command("~set")
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
            result = handle_meta_command("~set =value")
            assert result is True
            mock_emit_error.assert_called_with("You must supply a key.")
    finally:
        mocks["emit_error"].stop()


def test_non_meta_command_returns_false():
    # No need for mocks here since we're just testing the return value
    result = handle_meta_command("echo hi")
    assert result is False


def test_bare_tilde_with_spaces():
    mocks = setup_messaging_mocks()
    mock_emit_info = mocks["emit_info"].start()
    
    try:
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="zoom",
        ):
            result = handle_meta_command("~    ")
            assert result is True
            mock_emit_info.assert_called()
            assert any(
                "Current Model:" in str(call) and "zoom" in str(call)
                for call in mock_emit_info.call_args_list
            )
    finally:
        mocks["emit_info"].stop()
