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


# TODO: test_codemap_prints_tree
# TODO: test_m_sets_model
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


# TODO: test_set_config_value_space
# TODO: test_show_status
# TODO: test_unknown_meta_command
# TODO: test_bare_tilde_shows_current_model
