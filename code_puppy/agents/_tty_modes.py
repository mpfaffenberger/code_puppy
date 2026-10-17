"""POSIX termios tweaks the key listener applies on top of ``tty.setcbreak``.

Pure function over a ``termios.tcgetattr`` list so it is unit-testable
without a real TTY. Mirrors the raw-mode emulation prompt_toolkit's
classic path used, plus the undo/redo keys of the line editor.
"""

from __future__ import annotations

from types import ModuleType
from typing import List, Union

#: ``termios.tcgetattr`` shape: 6 flag/speed ints + the ``cc`` list.
TermiosAttrs = List[Union[int, List[Union[bytes, int]]]]

#: Control chars delivered raw to the editor instead of firing a signal.
#: ISIG stays ON, so Ctrl+\\ (SIGQUIT) keeps working.
#:  - VINTR: ^C arrives as \\x03 (buffer-first clear / cancel policy).
#:  - VSUSP: ^Z arrives as \\x1a (prompt undo) instead of SIGTSTP.
#:  - VDSUSP (BSD/macOS only): delayed suspend on ^Y, which is redo.
_RAW_SIGNAL_CHARS = ("VINTR", "VSUSP", "VDSUSP")


def apply_editor_cbreak_attrs(
    attrs: TermiosAttrs, termios: ModuleType, vdisable: int
) -> TermiosAttrs:
    """Return ``attrs`` adjusted for the raw line editor (mutated in place).

    - ICRNL off: keep Enter (\\r) distinct from Ctrl+J (\\n).
    - IXON/IXOFF off: Ctrl+S would freeze output and brick a repaint on
      the listener thread (2026-07-11 incident). Windows twin:
      ``enable_windows_raw_input`` drops LINE_INPUT.
    - IEXTEN off: BSD/macOS VLNEXT eats the first ^V as a quote prefix
      (the 'Ctrl+V twice to paste an image' bug); VDISCARD (^O) too.
    - Signal chars in ``_RAW_SIGNAL_CHARS`` set to ``_POSIX_VDISABLE``.
    """
    attrs[0] &= ~termios.ICRNL
    attrs[0] &= ~termios.IXON
    if hasattr(termios, "IXOFF"):
        attrs[0] &= ~termios.IXOFF
    attrs[3] &= ~termios.IEXTEN
    cc = attrs[6]
    for name in _RAW_SIGNAL_CHARS:
        index = getattr(termios, name, None)
        if index is not None:
            cc[index] = bytes([vdisable])
    return attrs


__all__ = ["TermiosAttrs", "apply_editor_cbreak_attrs"]
