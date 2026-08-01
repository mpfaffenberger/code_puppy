from __future__ import annotations

import io

import pytest

from code_puppy.plugins.computer_use import inline_image


@pytest.fixture(autouse=True)
def hermetic_terminal_env(monkeypatch):
    """Scrub terminal-identity env vars so the host terminal can't leak in.

    ``_terminal_kind`` checks ``ITERM_SESSION_ID`` before ``TERM_PROGRAM``,
    so running the suite inside iTerm2 (or kitty) would otherwise override
    the values these tests monkeypatch.
    """
    for var in ("TERM_PROGRAM", "TERM", "ITERM_SESSION_ID", "KITTY_WINDOW_ID"):
        monkeypatch.delenv(var, raising=False)


def test_terminal_detection(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    assert inline_image._terminal_kind() == "kitty"

    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    assert inline_image._terminal_kind() == "iterm"

    monkeypatch.setenv("TERM_PROGRAM", "unknown")
    monkeypatch.setenv("TERM", "dumb")
    assert inline_image._terminal_kind() is None


def test_ghostty_emits_kitty_graphics_sequence(monkeypatch, tmp_path):
    class TTYBuffer(io.StringIO):
        def isatty(self):
            return True

    image = tmp_path / "screen.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    output = TTYBuffer()
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setattr(inline_image.sys, "stdout", output)

    assert inline_image.emit_inline_image(image) is True
    sequence = output.getvalue()
    assert sequence.startswith("\033_G")
    assert "a=T,t=f,f=100,q=2,c=64,r=22" in sequence
    assert sequence.endswith("\033\\\n")
