"""Dim ANSI Markdown without leaking terminal styling into later output."""

import re

_SGR = re.compile(r"\x1b\[[0-9;]*m")


class DimWriter:
    """Reapply dim after every Markdown style change, including resets."""

    def __init__(self, target) -> None:
        self._target = target

    def write(self, text: str) -> int:
        if text:
            dimmed = _SGR.sub(lambda match: match[0] + "\x1b[2m", text)
            self._target.write("\x1b[2m" + dimmed + "\x1b[0m")
        return len(text)

    def flush(self):
        return self._target.flush()
