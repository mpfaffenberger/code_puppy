"""Tests for self-termination command detector — MacOS, Linux, Windows"""

from __future__ import annotations

import pytest

from code_puppy.plugins.self_termination_guardrail import detector
from code_puppy.plugins.self_termination_guardrail.detector import TerminationCommandMatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def stable_protected_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make detector tests deterministic.

    The detector computes PROTECTED_NAMES at import time from the current
    process tree. Patch that already-computed set instead of get_processes(),
    because patching get_processes() after import would be too late.
    """
    monkeypatch.setattr(
        detector,
        "PROTECTED_NAMES",
        {
            "12345",
            "4242",
            "98765",
            "bash",
            "cmd",
            "code-puppy",
            "code_puppy",
            "code-puppy-venv",
            "conhost",
            "login",
            "openconsole",
            "python",
            "python3",
            "terminal",
            "windowsterminal",
            "zsh",
            "-zsh",
        },
    )


def _hits(cmd: str) -> TerminationCommandMatch | None:
    """Return a match when the command is flagged."""
    return detector.detect_self_termination_command(f"&& {cmd}")


def _miss(cmd: str) -> bool:
    """Return True when the command is NOT flagged."""
    return detector.detect_self_termination_command(f"&& {cmd}") is None


def _raw_hits(cmd: str) -> TerminationCommandMatch | None:
    """Return a match for an unwrapped command string."""
    return detector.detect_self_termination_command(cmd)


# ===========================================================================
# MacOS and Linux
# ===========================================================================


class TestPkillCommand:
    """pkill -flag protected_name"""

    @pytest.mark.parametrize(
        "cmd",
        [
            "pkill python3",
            "pkill code-puppy",
            "pkill code_puppy",
            "pkill code-puppy-venv",
            "pkill -9 login",
            "pkill -n Terminal",
            "pkill -U uid -- -zsh",
            "pkill -f code-puppy",
            "pkill -9 -f code_puppy",
        ],
    )
    def test_matches(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


class TestKillallCommand:
    """killall -flag protected_name"""

    @pytest.mark.parametrize(
        "cmd",
        [
            "killall python",
            "killall -9 bash",
            "killall zsh",
            "killall -x python3",
        ],
    )
    def test_matches(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


class TestKillCommand:
    """kill -flag protected_pid"""

    @pytest.mark.parametrize(
        "cmd",
        [
            "kill 12345",
            "kill -9 4242",
            "kill -TERM 98765",
        ],
    )
    def test_matches_pid(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


# ===========================================================================
# Detector behavior
# ===========================================================================


class TestObfuscatedCommands:
    """Simple shell obfuscations are normalized before matching."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "p''kill python3",
            "task^kill /PID 12345",
        ],
    )
    def test_matches_obfuscated_command(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


class TestCompoundCommands:
    """Compound command strings are scanned subcommand-by-subcommand."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "echo hello && pkill python3",
            "echo hello || kill -9 12345",
            "echo hello & killall bash",
            "echo hello && taskkill /PID 12345",
            "echo hello && Stop-Process -Name python3",
            "echo hello && pkill python3 && echo goodbye",
            "pkill code-puppy && echo should_not_matter",
        ],
    )
    def test_matches_dangerous_subcommand(self, cmd: str) -> None:
        result = _raw_hits(cmd)
        assert result is not None


class TestWrapperCommands:
    """Supported command wrappers are unwrapped before matching."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "sudo pkill python3",
            "sudo -u root kill -9 4242",
            "sudo --user=root pkill code-puppy",
            "env FOO=bar pkill python3",
            "env -u FOO pkill python3",
            "env -- pkill python3",
            "nice -n 10 kill -9 4242",
            "nice --adjustment 10 pkill python3",
            "nohup -- pkill python3",
            "time -- kill 12345",
            "command -p pkill python3",
            "FOO=bar sudo pkill python3",
            "sudo env FOO=bar nice -n 5 pkill python3",
        ],
    )
    def test_matches_termination_command_after_wrapper(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


# ===========================================================================
# Windows
# ===========================================================================


class TestTaskkillCommand:
    """taskkill -flag protected_name"""

    @pytest.mark.parametrize(
        "cmd",
        [
            "taskkill /IM python.exe",
            "taskkill /IM PYTHON.EXE",
            "taskkill /IM cmd.exe",
            "taskkill /F /IM WindowsTerminal.exe",
            "taskkill /PID 12345",
            "taskkill /F /PID 4242",
        ],
    )
    def test_matches(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


class TestStopProcessCommand:
    """Stop-Process -flag protected_name"""

    @pytest.mark.parametrize(
        "cmd",
        [
            "Stop-Process -Name 'OpenConsole.exe'",
            "Stop-Process -Name 'conhost.exe' -Force",
            "STOP-PROCESS -Name PYTHON3",
            "Stop-Process -Id 98765",
            "spps -Name 'python3.exe'",
            "spps -Id 4242",
        ],
    )
    def test_matches(self, cmd: str) -> None:
        result = _hits(cmd)
        assert result is not None


# ===========================================================================
# False-positive guard
# ===========================================================================


class TestFalsePositives:
    """Commands that must NOT be flagged."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "pkill notepad",
            "kill -9 11111",
            "killall -9 'Google Chrome'",
            "taskkill /PID 11111",
            "echo pkill python3",
            "printf 'taskkill /PID 12345'",
            "echo 'Stop-Process -Name python'",
            "python3",
            "pkill",
            "echo hello && taskkill /PID 11111",
        ],
    )
    def test_safe_commands(self, cmd: str) -> None:
        assert _miss(cmd), f"False positive: {cmd!r} was flagged"