"""Tests for ``erase_progress_line`` on dead and non-terminal consoles."""

import errno
import io
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from code_puppy.tools.display import erase_progress_line


def _terminal_console(buf: io.StringIO) -> Console:
    return Console(file=buf, force_terminal=True, width=80)


def test_emits_erase_sequence_on_a_terminal():
    buf = io.StringIO()
    erase_progress_line(_terminal_console(buf))
    assert "\x1b[2K" in buf.getvalue() and "\r" in buf.getvalue()


def test_is_a_no_op_on_a_non_terminal():
    console = MagicMock(is_terminal=False)
    erase_progress_line(console)
    console.control.assert_not_called()


@pytest.mark.parametrize("code", [errno.EINVAL, errno.EBADF, errno.EPIPE])
def test_dead_handle_error_is_swallowed(code):
    console = MagicMock(is_terminal=True)
    console.control.side_effect = OSError(code, "dead")
    erase_progress_line(console)


def test_unrelated_oserror_propagates():
    console = MagicMock(is_terminal=True)
    console.control.side_effect = OSError(errno.ENOSPC, "disk full")
    with pytest.raises(OSError):
        erase_progress_line(console)
