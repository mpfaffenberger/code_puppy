"""Interactive-loop tests for the Phase A persistent prompt branch.

Drives ``interactive_mode`` with the persistent path forced and the
run_ui layer stubbed, verifying the transcript echo and both quit paths.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import code_puppy.cli_runner as cli_runner


@pytest.fixture
def renderer():
    r = MagicMock()
    r.console = MagicMock()
    return r


def _drive_interactive(monkeypatch, submissions):
    """Patch the persistent plumbing; yield captured transcript lines.

    ``submissions`` items are strings, or EOFError to simulate Ctrl+D.
    """
    items = list(submissions)

    async def fake_wait():
        if not items:
            raise EOFError
        item = items.pop(0)
        if item is EOFError:
            raise EOFError
        return item

    monkeypatch.setattr(cli_runner, "_use_persistent_prompt", lambda: True)
    monkeypatch.setattr(cli_runner, "_persistent_prompt_parts", lambda: (">>> ", []))
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.start_persistent_ui",
        lambda prompt_prefix=None, prefix_sgrs=None: True,
    )
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.set_idle_prompt_prefix",
        lambda prefix, prefix_sgrs=None: None,
    )
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.wait_for_idle_submission", fake_wait
    )
    stopped = []
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.stop_persistent_ui",
        lambda: stopped.append(True),
    )
    monkeypatch.setattr(cli_runner, "print_truecolor_warning", lambda console: None)
    monkeypatch.setattr(cli_runner, "record_terminal_session", lambda *a, **k: None)
    return stopped


@pytest.mark.asyncio
async def test_persistent_submission_is_echoed_then_exit(monkeypatch, renderer):
    stopped = _drive_interactive(monkeypatch, ["/exit"])
    infos = []
    successes = []
    with (
        patch("code_puppy.messaging.emit_info", lambda msg, **k: infos.append(msg)),
        patch(
            "code_puppy.messaging.emit_success",
            lambda msg, **k: successes.append(str(msg)),
        ),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    # Transcript echo: a USER banner tag followed by the user's text — no
    # copy of the prompt chrome (prefix/model/cwd stay on the bar).
    echoes = [str(m) for m in infos if str(m) == "\n USER  /exit"]
    assert echoes, f"expected transcript echo, got infos: {[str(m) for m in infos]}"
    assert not any(">>> /exit" in str(m) for m in infos)  # chrome not echoed
    assert any("Goodbye" in s for s in successes)
    assert stopped  # persistent UI torn down after the loop


@pytest.mark.asyncio
async def test_persistent_ctrl_d_quits(monkeypatch, renderer):
    stopped = _drive_interactive(monkeypatch, [EOFError])
    successes = []
    with (
        patch("code_puppy.messaging.emit_info", lambda msg, **k: None),
        patch(
            "code_puppy.messaging.emit_success",
            lambda msg, **k: successes.append(str(msg)),
        ),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    assert any("Ctrl+D" in s for s in successes)
    assert stopped


@pytest.mark.asyncio
async def test_persistent_path_skips_task_banner(monkeypatch, renderer):
    _drive_interactive(monkeypatch, ["/exit"])
    infos = []
    with (
        patch(
            "code_puppy.messaging.emit_info", lambda msg, **k: infos.append(str(msg))
        ),
        patch("code_puppy.messaging.emit_success", lambda msg, **k: None),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    assert not any("Enter your coding task" in m for m in infos)


@pytest.mark.asyncio
async def test_persistent_start_failure_degrades_to_classic(monkeypatch, renderer):
    """start_persistent_ui returning False must fall back to the classic
    prompt path (non-TTY bar) rather than crash or hang."""
    monkeypatch.setattr(cli_runner, "_use_persistent_prompt", lambda: True)
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.start_persistent_ui",
        lambda prompt_prefix=None: False,
    )
    monkeypatch.setattr(cli_runner, "print_truecolor_warning", lambda console: None)
    monkeypatch.setattr(cli_runner, "record_terminal_session", lambda *a, **k: None)

    async def fake_classic_input(*a, **k):
        return "/exit"

    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
            fake_classic_input,
        ),
        patch("code_puppy.messaging.emit_info", lambda msg, **k: None),
        patch("code_puppy.messaging.emit_success", lambda msg, **k: None),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )


class TestUsePersistentPromptVTGate:
    """The raw-VT gate: unconfirmed VT support -> classic prompt."""

    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("CODE_PUPPY_CLASSIC_PROMPT", raising=False)
        monkeypatch.delenv("CODE_PUPPY_NO_TUI", raising=False)
        monkeypatch.setattr("code_puppy.config.get_value", lambda _k: None)
        tty = MagicMock()
        tty.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", tty)
        monkeypatch.setattr("sys.stdout", tty)

    def test_degrades_to_classic_when_vt_unconfirmed(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setattr(
            "code_puppy.terminal_utils.ensure_windows_vt_processing",
            lambda: False,
        )
        assert cli_runner._use_persistent_prompt() is False

    def test_persistent_when_vt_confirmed(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setattr(
            "code_puppy.terminal_utils.ensure_windows_vt_processing",
            lambda: True,
        )
        assert cli_runner._use_persistent_prompt() is True

    def test_gate_crash_never_blocks_persistent_ui(self, monkeypatch):
        """A blown-up gate must fail OPEN (POSIX safety), not closed."""
        self._clean_env(monkeypatch)

        def boom():
            raise RuntimeError("kernel32 ate my homework")

        monkeypatch.setattr(
            "code_puppy.terminal_utils.ensure_windows_vt_processing", boom
        )
        assert cli_runner._use_persistent_prompt() is True
