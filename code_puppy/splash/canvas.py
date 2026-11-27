"""A character grid painted in Code Puppy's colours, written out as escapes.

Stdlib-only: it draws while the runtime is still importing.
"""

from __future__ import annotations

import os

from code_puppy import colors

RESET = "\x1b[0m"


def truecolor() -> bool:
    """Whether the terminal advertises 24-bit colour."""
    return os.getenv("COLORTERM", "").lower() in ("truecolor", "24bit")


def ink(colour: str, *, deep: bool) -> str:
    """The escape that paints ``colour``: exact in truecolor, else its basic code.

    Only theme colours have a basic code, so a stray hex fails loudly in tests.
    """
    if not deep:
        return f"\x1b[{colors.BASIC[colour]}m"
    red, green, blue = bytes.fromhex(colour[1:])
    return f"\x1b[38;2;{red};{green};{blue}m"


class Canvas:
    """A ``width`` x ``height`` grid of glyphs, each with a colour."""

    def __init__(self, width: int, height: int) -> None:
        self.width = max(0, width)
        self.height = max(0, height)
        self._cells = [[(" ", "")] * self.width for _ in range(self.height)]

    def put(self, x: int, y: int, glyph: str, colour: str) -> None:
        """Paint one cell; off-canvas cells and spaces are ignored."""
        if glyph != " " and 0 <= x < self.width and 0 <= y < self.height:
            self._cells[y][x] = (glyph, colour)

    def sprite(self, x: int, y: int, rows: tuple[str, ...], colour: str) -> None:
        """Paint ``rows`` with their top-left corner at ``(x, y)``; spaces are transparent."""
        for row_offset, row in enumerate(rows):
            for glyph_offset, glyph in enumerate(row):
                self.put(x + glyph_offset, y + row_offset, glyph, colour)

    def colours(self) -> set[str]:
        """Every colour painted so far."""
        return {colour for row in self._cells for _, colour in row if colour}

    def render(self, *, deep: bool) -> str:
        """The whole grid, each row placed absolutely so nothing ever scrolls."""
        lines = []
        for y, row in enumerate(self._cells):
            out = [f"\x1b[{y + 1};1H"]
            current = ""
            for glyph, colour in row:
                if colour and colour != current:
                    out.append(ink(colour, deep=deep))
                    current = colour
                out.append(glyph)
            lines.append("".join(out) + RESET)
        return "".join(lines)
