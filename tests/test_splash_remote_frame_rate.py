"""The splash must not flood a remote terminal.

Every frame repaints the whole raster, so the ~30fps local rate writes
roughly a megabyte of escape sequences during a one-second boot --
measured at 1,058,225 bytes against 3,363 bytes for the real UI, i.e.
99.7% of everything the CLI writes to the terminal at startup.

Free on a local terminal. Over SSH or a forwarded tmux it becomes the
dominant cost of launching, and the animation ends up slower than the
imports it existed to hide.
"""

from code_puppy.splash import (
    _FRAME_SECONDS,
    _REMOTE_FRAME_SECONDS,
    _frame_seconds,
)

REMOTE_MARKERS = ("SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT")


def _clear_remote(monkeypatch):
    for marker in REMOTE_MARKERS:
        monkeypatch.delenv(marker, raising=False)


def test_local_session_keeps_the_smooth_frame_rate(monkeypatch):
    _clear_remote(monkeypatch)
    assert _frame_seconds() == _FRAME_SECONDS


def test_each_ssh_marker_slows_the_frame_rate(monkeypatch):
    for marker in REMOTE_MARKERS:
        _clear_remote(monkeypatch)
        monkeypatch.setenv(marker, "1")
        assert _frame_seconds() == _REMOTE_FRAME_SECONDS, f"{marker} not honored"


def test_remote_rate_is_actually_slower(monkeypatch):
    assert _REMOTE_FRAME_SECONDS > _FRAME_SECONDS


def test_remote_writes_meaningfully_fewer_frames(monkeypatch):
    """A one-second boot should cost roughly a third of the bytes."""
    local_frames = 1.0 / _FRAME_SECONDS
    remote_frames = 1.0 / _REMOTE_FRAME_SECONDS
    assert remote_frames <= local_frames / 3


def test_empty_marker_is_not_treated_as_remote(monkeypatch):
    """An exported-but-empty SSH_TTY is not a remote session."""
    _clear_remote(monkeypatch)
    monkeypatch.setenv("SSH_TTY", "")
    assert _frame_seconds() == _FRAME_SECONDS


def test_still_animates_remotely(monkeypatch):
    """Slower, not disabled -- the splash still hides import latency."""
    _clear_remote(monkeypatch)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")
    assert 0 < _frame_seconds() < 1.0
