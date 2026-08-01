from __future__ import annotations

import io

from code_puppy.plugins.computer_use import inline_image


def test_terminal_detection(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    assert inline_image._terminal_kind() == "kitty"

    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    assert inline_image._terminal_kind() == "iterm"

    monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
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
