"""Windows listener raw-input clamp: VT input on, cooked (line/echo) bits off.

The cooked half is the Ctrl+S fix: with ENABLE_LINE_INPUT on, conhost treats
Ctrl+S as "pause output" and the Ctrl+X Ctrl+S speculation chord froze the
terminal. A stateful fake console checks real mode transitions.
"""

import sys
from types import SimpleNamespace

import pytest

from code_puppy import terminal_utils

LINE, ECHO, PROCESSED, VT = 0x0002, 0x0004, 0x0001, 0x0200
COOKED_DEFAULT = LINE | ECHO | PROCESSED | 0x01F0  # typical conhost stdin mode


class _FakeConsole:
    """Just enough kernel32 to hold one stdin mode."""

    def __init__(self, mode: int, *, supports_vt: bool = True):
        self.mode = mode
        self.supports_vt = supports_vt

    def GetStdHandle(self, _which):
        return 1

    def GetConsoleMode(self, _handle, ref):
        ref.value = self.mode
        return True

    def SetConsoleMode(self, _handle, mode):
        if mode & VT and not self.supports_vt:
            return False  # ancient host rejects the unknown flag
        if mode & ECHO and not mode & LINE:
            return False  # ERROR_INVALID_PARAMETER, like the real thing
        self.mode = mode
        return True


@pytest.fixture
def console(monkeypatch):
    def _install(mode: int = COOKED_DEFAULT, **kwargs) -> _FakeConsole:
        fake = _FakeConsole(mode, **kwargs)
        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(kernel32=fake),
            c_ulong=lambda: SimpleNamespace(value=0),
            byref=lambda obj: obj,
        )
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        monkeypatch.setattr(terminal_utils, "_stripped_cooked_bits", 0)
        return fake

    return _install


def test_enable_strips_line_input_so_ctrl_s_cannot_pause(console):
    fake = console()
    assert terminal_utils.enable_windows_raw_input() is True
    assert fake.mode & VT
    assert not fake.mode & (LINE | ECHO)
    assert fake.mode & PROCESSED  # not ours to touch; ensure_ctrl_c_disabled owns it


def test_disable_restores_exactly_what_was_taken(console):
    fake = console()
    terminal_utils.enable_windows_raw_input()
    terminal_utils.disable_windows_raw_input()
    assert fake.mode == COOKED_DEFAULT
    assert terminal_utils._stripped_cooked_bits == 0


def test_disable_never_invents_cooked_bits(console):
    fake = console(mode=PROCESSED)  # started raw: nothing to hand back
    terminal_utils.enable_windows_raw_input()
    terminal_utils.disable_windows_raw_input()
    assert fake.mode == PROCESSED


def test_reclamp_after_someone_restores_line_mode(console):
    fake = console()
    terminal_utils.enable_windows_raw_input()
    fake.mode |= LINE | ECHO  # a shell child flips it back mid-session
    terminal_utils.enable_windows_raw_input()
    assert not fake.mode & (LINE | ECHO)
    terminal_utils.disable_windows_raw_input()
    assert fake.mode == COOKED_DEFAULT


def test_ancient_host_still_loses_line_input(console):
    fake = console(supports_vt=False)
    assert terminal_utils.enable_windows_raw_input() is False  # VT unconfirmed
    assert not fake.mode & (LINE | ECHO)  # ...but Ctrl+S is still safe


def test_noop_off_windows(monkeypatch):
    monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
    assert terminal_utils.enable_windows_raw_input() is False
    terminal_utils.disable_windows_raw_input()  # must not raise
