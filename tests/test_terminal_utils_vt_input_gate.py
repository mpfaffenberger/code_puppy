"""Regression tests for the Wave-only Windows VT-input compatibility gate."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import terminal_utils


@pytest.mark.parametrize("term_program", ["waveterm", "WaveTerm", "  WAVETERM\t"])
def test_wave_host_detection_is_case_and_whitespace_tolerant(monkeypatch, term_program):
    monkeypatch.setenv("TERM_PROGRAM", term_program)

    assert terminal_utils._vt_input_host_is_broken() is True


@pytest.mark.parametrize(
    "term_program",
    ["", "wave", "waveterm-preview", "Windows_Terminal", "Apple_Terminal"],
)
def test_non_wave_hosts_are_not_blocked(monkeypatch, term_program):
    monkeypatch.setenv("TERM_PROGRAM", term_program)

    assert terminal_utils._vt_input_host_is_broken() is False


def test_missing_term_program_is_not_blocked(monkeypatch):
    monkeypatch.delenv("TERM_PROGRAM", raising=False)

    assert terminal_utils._vt_input_host_is_broken() is False


def test_wave_on_windows_clears_vt_input_instead_of_enabling_it(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "waveterm")

    with (
        patch.object(terminal_utils.platform, "system", return_value="Windows"),
        patch.object(terminal_utils, "disable_windows_vt_input") as disable,
    ):
        assert terminal_utils.enable_windows_vt_input() is False

    disable.assert_called_once_with()


def test_wave_gate_does_not_change_non_windows_behavior(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "waveterm")

    with (
        patch.object(terminal_utils.platform, "system", return_value="Linux"),
        patch.object(terminal_utils, "disable_windows_vt_input") as disable,
    ):
        assert terminal_utils.enable_windows_vt_input() is False

    disable.assert_not_called()


def test_other_windows_terminals_keep_existing_vt_input_path(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "Windows_Terminal")
    kernel32 = MagicMock()
    mode_reads = iter([0, terminal_utils._ENABLE_VIRTUAL_TERMINAL_INPUT])

    def get_console_mode(_handle, mode):
        mode.value = next(mode_reads)
        return True

    kernel32.GetStdHandle.return_value = 123
    kernel32.GetConsoleMode.side_effect = get_console_mode
    kernel32.SetConsoleMode.return_value = True
    fake_ctypes = SimpleNamespace(
        c_ulong=lambda: SimpleNamespace(value=0),
        byref=lambda value: value,
        windll=SimpleNamespace(kernel32=kernel32),
    )

    with (
        patch.object(terminal_utils.platform, "system", return_value="Windows"),
        patch.dict(sys.modules, {"ctypes": fake_ctypes}),
        patch.object(terminal_utils, "disable_windows_vt_input") as disable,
    ):
        assert terminal_utils.enable_windows_vt_input() is True

    disable.assert_not_called()
    kernel32.SetConsoleMode.assert_called_once_with(
        123, terminal_utils._ENABLE_VIRTUAL_TERMINAL_INPUT
    )
