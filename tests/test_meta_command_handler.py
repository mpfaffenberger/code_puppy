from unittest.mock import MagicMock, patch

from rich.console import Console

from code_puppy.command_line.meta_command_handler import handle_meta_command


# Dummy console for testing output capture
def make_fake_console():
    fake_console = MagicMock(spec=Console)
    fake_console.print = MagicMock()
    return fake_console


def test_help_outputs_help():
    console = make_fake_console()
    result = handle_meta_command("~help", console)
    assert result is True
    console.print.assert_called()
    assert any(
        "Meta Commands Help" in str(call)
        for call in (c.args[0] for c in console.print.call_args_list)
    )


def test_cd_show_lists_directories():
    console = make_fake_console()
    with patch("code_puppy.command_line.utils.make_directory_table") as mock_table:
        mock_table.return_value = "FAKE_TABLE"
        result = handle_meta_command("~cd", console)
        assert result is True
        from rich.table import Table

        assert any(
            isinstance(call.args[0], Table) for call in console.print.call_args_list
        )


def test_cd_valid_change():
    console = make_fake_console()
    with (
        patch("os.path.expanduser", side_effect=lambda x: x),
        patch("os.path.isabs", return_value=True),
        patch("os.path.isdir", return_value=True),
        patch("os.chdir") as mock_chdir,
    ):
        result = handle_meta_command("~cd /some/dir", console)
        assert result is True
        mock_chdir.assert_called_once_with("/some/dir")
        console.print.assert_any_call(
            "[bold green]Changed directory to:[/bold green] [cyan]/some/dir[/cyan]"
        )


def test_cd_invalid_directory():
    console = make_fake_console()
    with (
        patch("os.path.expanduser", side_effect=lambda x: x),
        patch("os.path.isabs", return_value=True),
        patch("os.path.isdir", return_value=False),
    ):
        result = handle_meta_command("~cd /not/a/dir", console)
        assert result is True
        console.print.assert_any_call(
            "[red]Not a directory:[/red] [bold]/not/a/dir[/bold]"
        )


def test_codemap_prints_tree():
    console = make_fake_console()
    fake_tree = "FAKE_CODMAP_TREE"
    with patch("code_puppy.tools.ts_code_map.make_code_map") as mock_map:
        mock_map.return_value = fake_tree
        result = handle_meta_command("~codemap", console)
        assert result is True


def test_codemap_prints_tree_with_dir():
    console = make_fake_console()
    fake_tree = "TREE_FOR_DIR"
    with (
        patch("code_puppy.tools.ts_code_map.make_code_map") as mock_map,
        patch("os.path.expanduser", side_effect=lambda x: x),
    ):
        mock_map.return_value = fake_tree
        result = handle_meta_command("~codemap /some/dir", console)
        assert result is True


def test_codemap_error_prints():
    console = make_fake_console()
    with patch(
        "code_puppy.tools.ts_code_map.make_code_map", side_effect=Exception("fail")
    ):
        result = handle_meta_command("~codemap", console)
        assert result is True
        assert any(
            "Error generating code map" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_m_sets_model():
    console = make_fake_console()
    with (
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
        result = handle_meta_command("~mgpt-9001", console)
        assert result is True


def test_m_unrecognized_model_lists_options():
    console = make_fake_console()
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
        result = handle_meta_command("~m not-a-model", console)
        assert result is True
        assert any(
            "Available models" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )
        assert any(
            "Usage:" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )
    console = make_fake_console()
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
        result = handle_meta_command("~m not-a-model", console)
        assert result is True
        assert any(
            "Available models" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )
        assert any(
            "Usage:" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_set_config_value_equals():
    console = make_fake_console()
    with (
        patch("code_puppy.config.set_config_value") as mock_set_cfg,
        patch("code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]),
    ):
        result = handle_meta_command("~set pony=rainbow", console)
        assert result is True
        mock_set_cfg.assert_called_once_with("pony", "rainbow")
        assert any(
            "Set" in str(call) and "pony" in str(call) and "rainbow" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_set_config_value_space():
    console = make_fake_console()
    with (
        patch("code_puppy.config.set_config_value") as mock_set_cfg,
        patch("code_puppy.config.get_config_keys", return_value=["pony", "rainbow"]),
    ):
        result = handle_meta_command("~set pony rainbow", console)
        assert result is True
        mock_set_cfg.assert_called_once_with("pony", "rainbow")
        assert any(
            "Set" in str(call) and "pony" in str(call) and "rainbow" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_set_config_only_key():
    console = make_fake_console()
    with (
        patch("code_puppy.config.set_config_value") as mock_set_cfg,
        patch("code_puppy.config.get_config_keys", return_value=["key"]),
    ):
        result = handle_meta_command("~set pony", console)
        assert result is True
        mock_set_cfg.assert_called_once_with("pony", "")
        assert any(
            "Set" in str(call) and "pony" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_show_status():
    console = make_fake_console()
    with (
        patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="MODEL-X",
        ),
        patch("code_puppy.config.get_owner_name", return_value="Ivan"),
        patch("code_puppy.config.get_puppy_name", return_value="Biscuit"),
        patch("code_puppy.config.get_yolo_mode", return_value=True),
    ):
        result = handle_meta_command("~show", console)
        assert result is True
        assert any(
            "Puppy Status" in str(call)
            and "Ivan" in str(call)
            and "Biscuit" in str(call)
            and "MODEL-X" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_unknown_meta_command():
    console = make_fake_console()
    result = handle_meta_command("~unknowncmd", console)
    assert result is True
    assert any(
        "Unknown meta command" in str(call)
        for call in (c.args[0] for c in console.print.call_args_list)
    )


def test_bare_tilde_shows_current_model():
    console = make_fake_console()
    with patch(
        "code_puppy.command_line.model_picker_completion.get_active_model",
        return_value="yarn",
    ):
        result = handle_meta_command("~", console)
        assert result is True
        assert any(
            "Current Model:" in str(call) and "yarn" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_set_no_args_prints_usage():
    console = make_fake_console()
    with patch("code_puppy.config.get_config_keys", return_value=["foo", "bar"]):
        result = handle_meta_command("~set", console)
        assert result is True
        assert any(
            "Usage" in str(call) and "Config keys" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_set_missing_key_errors():
    console = make_fake_console()
    # This will enter the 'else' branch printing 'You must supply a key.'
    with patch("code_puppy.config.get_config_keys", return_value=["foo", "bar"]):
        result = handle_meta_command("~set =value", console)
        assert result is True
        assert any(
            "You must supply a key" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )


def test_non_meta_command_returns_false():
    console = make_fake_console()
    result = handle_meta_command("echo hi", console)
    assert result is False
    console.print.assert_not_called()


def test_bare_tilde_with_spaces():
    console = make_fake_console()
    with patch(
        "code_puppy.command_line.model_picker_completion.get_active_model",
        return_value="zoom",
    ):
        result = handle_meta_command("~    ", console)
        assert result is True
        assert any(
            "Current Model:" in str(call) and "zoom" in str(call)
            for call in (c.args[0] for c in console.print.call_args_list)
        )
