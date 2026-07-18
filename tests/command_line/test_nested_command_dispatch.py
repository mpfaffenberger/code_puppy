"""Regression tests for namespaced (nested) custom command dispatch.

The command handler has a file-path disambiguation heuristic: a leading-slash
token with more than one slash (``/Users/me/file.py``) is treated as normal
input, not a command. Namespaced custom commands (``/flux/status``) also carry
multiple slashes, so the heuristic must special-case *known* custom commands --
otherwise ``/flux/...`` silently falls through to the agent instead of running
its handler (e.g. an ``exec:`` directive). See ``_is_namespaced_custom_command``.
"""

from unittest.mock import patch

from code_puppy.command_line.command_handler import (
    _is_namespaced_custom_command,
    handle_command,
)


def test_known_nested_command_is_not_treated_as_file_path():
    """A loaded ``/flux/status`` command is recognized despite two slashes."""
    with patch(
        "code_puppy.plugins.customizable_commands.register_callbacks.is_custom_command",
        return_value=True,
    ):
        assert _is_namespaced_custom_command("/flux/status") is True


def test_real_file_path_is_still_treated_as_file_path():
    """A genuine multi-slash path is NOT mistaken for a command."""
    with patch(
        "code_puppy.plugins.customizable_commands.register_callbacks.is_custom_command",
        return_value=False,
    ):
        assert _is_namespaced_custom_command("/Users/me/workspace/file.py") is False


def test_disambiguation_fails_closed_without_plugin():
    """If the plugin can't be imported, the token is NOT treated as a command."""
    real_import = __import__

    def _boom(name, *args, **kwargs):
        if name == "code_puppy.plugins.customizable_commands.register_callbacks":
            raise ImportError("simulated missing plugin")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_boom):
        # Fails closed: no plugin -> can't be a nested command -> False.
        assert _is_namespaced_custom_command("/flux/status") is False


def test_multi_slash_file_path_falls_through_to_normal_input():
    """``handle_command`` returns False for a real path (processed as input)."""
    with patch(
        "code_puppy.command_line.command_handler._is_namespaced_custom_command",
        return_value=False,
    ):
        assert handle_command("/Users/me/workspace/notes.md") is False


def test_nested_command_reaches_custom_command_dispatch():
    """A recognized nested command is NOT short-circuited as a file path.

    We stub the disambiguation to say "yes this is a command", then confirm the
    handler proceeds to the custom-command callback layer (returning True when a
    plugin claims the command) instead of bailing out with False.
    """
    with (
        patch(
            "code_puppy.command_line.command_handler._is_namespaced_custom_command",
            return_value=True,
        ),
        patch("code_puppy.command_line.command_handler._ensure_plugins_loaded"),
        patch("code_puppy.callbacks.on_custom_command", return_value=[True]),
    ):
        assert handle_command("/flux/status review") is True
