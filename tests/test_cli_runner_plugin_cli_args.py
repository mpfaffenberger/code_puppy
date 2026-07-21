"""Tests for plugin-registered CLI args wiring in cli_runner.main().

Covers the register_cli_args / handle_cli_args hooks added to main():
- register_cli_args callbacks get the live parser before parse_args().
- a plugin flag appears in parsed args and in ``code-puppy --help`` output.
- handle_cli_args callbacks can short-circuit startup with a clean exit.
- a handler returning None leaves normal startup intact.
- duplicate option strings fail fast with an argparse.ArgumentError.
"""

import argparse
import asyncio
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from code_puppy import callbacks
from code_puppy.cli_runner import main


@pytest.fixture
def clean_cli_hooks():
    """Snapshot/restore the cli-arg callback registries around each test."""
    register_before = list(callbacks._callbacks["register_cli_args"])
    handle_before = list(callbacks._callbacks["handle_cli_args"])
    callbacks._callbacks["register_cli_args"] = []
    callbacks._callbacks["handle_cli_args"] = []
    try:
        yield
    finally:
        callbacks._callbacks["register_cli_args"] = register_before
        callbacks._callbacks["handle_cli_args"] = handle_before


def test_register_cli_args_runs_before_parse(clean_cli_hooks):
    """A plugin-registered flag is added to the parser and parsed into args."""
    seen = {}

    def _register(parser):
        parser.add_argument("--myplugin-foo", dest="myplugin_foo", default=None)

    def _handle(args):
        seen["foo"] = getattr(args, "myplugin_foo", "MISSING")
        # Short-circuit so the rest of main() never runs.
        return {"handled": True, "exit_code": 0}

    callbacks.register_callback("register_cli_args", _register)
    callbacks.register_callback("handle_cli_args", _handle)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy", "--myplugin-foo", "bar"]))
        result = asyncio.run(main())

    assert result == 0
    # The plugin flag was registered before parse_args and parsed correctly.
    assert seen["foo"] == "bar"


def test_plugin_flag_appears_in_help(clean_cli_hooks, capsys):
    """A plugin-registered flag shows up in ``code-puppy --help`` output.

    argparse prints help to stdout and exits 0, so we expect SystemExit and
    then assert the flag + its help string made it into the rendered help.
    """

    def _register(parser):
        parser.add_argument(
            "--myplugin-xyz",
            dest="myplugin_xyz",
            help="the all-important xyz flag",
        )

    callbacks.register_callback("register_cli_args", _register)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy", "--help"]))
        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(main())

    # --help is a clean exit.
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--myplugin-xyz" in out
    assert "the all-important xyz flag" in out


def test_prompt_mode_help_uses_catalog_strings(clean_cli_hooks, capsys):
    """The prompt-mode options expose their localized argparse help text."""
    from code_puppy.i18n import set_locale

    set_locale("en-US")

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy", "--help"]))
        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(main())

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Run interactively; with --prompt" in out
    assert "Execute a prompt and exit" in out


def test_help_survives_locale_bootstrap_failure(clean_cli_hooks, capsys):
    """Malformed optional config cannot block argparse's own help path."""
    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy", "--help"]))
        stack.enter_context(
            patch(
                "code_puppy.cli_runner.get_locale",
                side_effect=RuntimeError("bad config"),
            )
        )
        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(main())

    assert excinfo.value.code == 0
    assert "--interactive" in capsys.readouterr().out


def test_duplicate_option_strings_raise_argparse_error(clean_cli_hooks):
    """Two callbacks declaring the same option string fail fast.

    register_cli_args is intentionally NOT error-isolated: a conflicting
    option string is a fatal developer error, so the argparse.ArgumentError
    must propagate out of main() rather than being silently swallowed.
    """

    def _first(parser):
        parser.add_argument("--dup-flag", dest="dup_flag_a")

    def _second(parser):
        parser.add_argument("--dup-flag", dest="dup_flag_b")

    callbacks.register_callback("register_cli_args", _first)
    callbacks.register_callback("register_cli_args", _second)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy"]))
        with pytest.raises(argparse.ArgumentError) as excinfo:
            asyncio.run(main())

    msg = str(excinfo.value)
    assert "conflicting option string" in msg
    assert "--dup-flag" in msg


def test_handle_cli_args_short_circuits_with_exit_code(clean_cli_hooks):
    """A handled=True result returns its exit_code from main()."""

    def _handle(args):
        return {"handled": True, "exit_code": 7}

    callbacks.register_callback("handle_cli_args", _handle)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy"]))
        result = asyncio.run(main())

    assert result == 7


def test_handle_cli_args_default_exit_code_zero(clean_cli_hooks):
    """A handled result without exit_code defaults to 0."""

    def _handle(args):
        return {"handled": True}

    callbacks.register_callback("handle_cli_args", _handle)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy"]))
        result = asyncio.run(main())

    assert result == 0


def test_first_handled_result_wins(clean_cli_hooks):
    """The first handled=True result short-circuits; later handlers ignored."""
    calls = []

    def _first(args):
        calls.append("first")
        return {"handled": True, "exit_code": 3}

    def _second(args):
        calls.append("second")
        return {"handled": True, "exit_code": 99}

    callbacks.register_callback("handle_cli_args", _first)
    callbacks.register_callback("handle_cli_args", _second)

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy"]))
        result = asyncio.run(main())

    # Both callbacks execute (results collected), but the first handled wins.
    assert result == 3
    assert calls[0] == "first"


def test_handler_returning_none_does_not_short_circuit(clean_cli_hooks):
    """A handler returning None must not short-circuit; main() proceeds.

    We bail out shortly after the hook by raising from a patched downstream
    dependency, proving the early-return branch was *not* taken.
    """

    def _observe(args):
        return None  # observe only

    callbacks.register_callback("handle_cli_args", _observe)

    sentinel = RuntimeError("proceeded past cli-args hook")

    with ExitStack() as stack:
        stack.enter_context(patch("sys.argv", ["code-puppy", "-p", "hi"]))
        # First thing main() touches after the hook is the messaging import path;
        # force a recognizable failure to confirm we got past the early return.
        stack.enter_context(
            patch(
                "code_puppy.messaging.get_global_queue",
                side_effect=sentinel,
            )
        )
        with pytest.raises(RuntimeError, match="proceeded past cli-args hook"):
            asyncio.run(main())
