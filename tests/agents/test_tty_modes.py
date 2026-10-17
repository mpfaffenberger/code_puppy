"""Ctrl+Z / Ctrl+Y reach the line editor as keys instead of job control."""

import sys
import types

import pytest

from code_puppy.agents._key_listeners import _route_windows_burst, set_line_editor
from code_puppy.agents._tty_modes import apply_editor_cbreak_attrs

VDISABLE = 0xFF


def fake_termios(**cc_indices):
    return types.SimpleNamespace(
        ICRNL=0x100, IXON=0x200, IXOFF=0x400, IEXTEN=0x800, **cc_indices
    )


def make_attrs():
    cc = [b"\x00"] * 8
    return [0xFFFF, 0, 0, 0xFFFF, 0, 0, cc]


def test_disables_suspend_chars_and_keeps_line_tweaks():
    termios = fake_termios(VINTR=0, VSUSP=1, VDSUSP=2)
    attrs = apply_editor_cbreak_attrs(make_attrs(), termios, VDISABLE)
    cc = attrs[6]
    assert cc[0] == cc[1] == cc[2] == bytes([VDISABLE])
    assert cc[3] == b"\x00"  # VQUIT etc. untouched: ISIG stays on
    assert not attrs[0] & (termios.ICRNL | termios.IXON | termios.IXOFF)
    assert not attrs[3] & termios.IEXTEN


def test_platform_without_vdsusp_or_ixoff():
    termios = fake_termios(VINTR=0, VSUSP=1)  # Linux: no VDSUSP
    del termios.IXOFF
    cc = apply_editor_cbreak_attrs(make_attrs(), termios, VDISABLE)[6]
    assert cc[1] == bytes([VDISABLE])
    assert cc[2] == b"\x00"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pty only")
@pytest.mark.parametrize("key", [b"\x1a", b"\x19"])
def test_real_pty_delivers_ctrl_z_and_ctrl_y_as_bytes(key):
    """The line discipline hands ^Z/^Y to the reader instead of eating
    them as (delayed) suspend; with the stock attrs ^Z would be consumed."""
    import os
    import select
    import termios
    import tty

    master, slave = os.openpty()
    try:
        tty.setcbreak(slave)
        vdisable = os.fpathconf(slave, "PC_VDISABLE")
        attrs = apply_editor_cbreak_attrs(termios.tcgetattr(slave), termios, vdisable)
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        os.write(master, key)
        ready, _, _ = select.select([slave], [], [], 2.0)
        assert ready, "key was swallowed by the tty line discipline"
        assert os.read(slave, 16) == key
    finally:
        os.close(master)
        os.close(slave)


class TestWindowsDelivery:
    @pytest.fixture
    def editor(self):
        from code_puppy.messaging.line_editor import RunningLineEditor

        ed = RunningLineEditor()
        set_line_editor(ed)
        try:
            yield ed
        finally:
            set_line_editor(None)

    def test_ctrl_z_burst_is_undo_not_text_or_eof(self, editor):
        editor.insert_paste_text("hello")
        editor.feed("\x15")  # Ctrl+U
        items = [("char", "\x1a")]
        _route_windows_burst(items, lambda: None, None, None)
        assert editor.buffer == "hello"
        _route_windows_burst([("char", "\x19")], lambda: None, None, None)
        assert editor.buffer == ""

    def test_held_ctrl_z_is_not_coalesced_into_a_paste(self, editor):
        editor.feed("a b c")
        _route_windows_burst([("char", "\x1a")] * 3, lambda: None, None, None)
        assert editor.buffer == ""
