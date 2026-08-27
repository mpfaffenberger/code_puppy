"""``quiet_startup`` hides chrome and never hides warnings.

Interactive startup prints nine messages before the prompt and exactly
one is situational: the untrusted-hooks warning, which says project hooks
can run arbitrary shell commands. It renders with the same weight as an
install log, so the line that matters is the one nobody reads.

These tests pin the boundary. The flag may skip decoration; it may never
skip anything that tells the user something is wrong.
"""

from unittest.mock import MagicMock, patch

from code_puppy.config import get_quiet_startup


def test_defaults_to_off_so_existing_installs_are_unchanged():
    with patch("code_puppy.config.get_truthy_bool_value", return_value=False) as g:
        assert get_quiet_startup() is False
    g.assert_called_once_with("quiet_startup", False)


def test_reads_the_config_key():
    with patch("code_puppy.config.get_truthy_bool_value", return_value=True):
        assert get_quiet_startup() is True


def test_quiet_startup_is_an_advertised_config_key():
    """It must show up in /config so it is discoverable, not folklore."""
    from code_puppy.config import get_config_keys

    assert "quiet_startup" in get_config_keys()


def test_version_line_suppressed_when_quiet_and_up_to_date():
    """The 'Current version:' line is chrome when nothing is wrong."""
    from code_puppy import version_checker

    with (
        patch.object(version_checker, "fetch_latest_version", return_value="1.0.0"),
        patch.object(version_checker, "get_message_bus", return_value=MagicMock()),
        patch.object(version_checker, "emit_info") as emit,
        patch("code_puppy.config.get_quiet_startup", return_value=True),
    ):
        version_checker.default_version_mismatch_behavior("1.0.0")

    assert emit.call_count == 0


def test_update_notice_survives_quiet_startup():
    """An available update is news, not chrome. It must still print."""
    from code_puppy import version_checker

    with (
        patch.object(version_checker, "fetch_latest_version", return_value="9.9.9"),
        patch.object(version_checker, "get_message_bus", return_value=MagicMock()),
        patch.object(version_checker, "emit_info") as emit,
        patch("code_puppy.config.get_quiet_startup", return_value=True),
    ):
        version_checker.default_version_mismatch_behavior("1.0.0")

    emitted = " ".join(str(c.args[0]) for c in emit.call_args_list)
    assert "1.0.0" in emitted, "current version must still print alongside an update"
    assert "9.9.9" in emitted, "update notice must not be silenced by quiet_startup"


def test_version_line_prints_normally_when_not_quiet():
    from code_puppy import version_checker

    with (
        patch.object(version_checker, "fetch_latest_version", return_value="1.0.0"),
        patch.object(version_checker, "get_message_bus", return_value=MagicMock()),
        patch.object(version_checker, "emit_info") as emit,
        patch("code_puppy.config.get_quiet_startup", return_value=False),
    ):
        version_checker.default_version_mismatch_behavior("1.0.0")

    assert emit.call_count == 1


def test_truecolor_warning_is_never_gated_on_quiet_startup():
    """Warnings are exempt by construction -- pin it against a refactor."""
    import inspect

    from code_puppy import cli_runner

    source = inspect.getsource(cli_runner)
    idx = source.index("print_truecolor_warning(display_console)")
    preceding = source[max(0, idx - 400) : idx]
    warn_line = preceding.rsplit("\n", 2)[-1]
    assert "get_quiet_startup" not in warn_line
