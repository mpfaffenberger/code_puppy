"""Separate prompt metadata from input and paint its single chrome row."""

from rich.cells import cell_len

from .bar_rendering import elide_middle, sanitize, stylize_slice

#: SGR the prompt colors punctuation with (see :func:`split_identity`). The
#: elision marker borrows it so the gap reads as chrome, not as cwd text.
_MUTED_SGR = "90"


def split_identity(
    prefix: str, sgrs: list[str]
) -> tuple[str, list[str], str, list[str]]:
    """Recognize the standard rich prompt, leaving custom prompts untouched."""
    marker = prefix.rfind(">>>")
    if marker <= 0 or not prefix[:marker].strip():
        return prefix, sgrs, "", []
    identity = prefix[:marker].rstrip()
    # Neutral chrome with existing palette highlights; punctuation stays grey.
    colors = [
        sgrs[index]
        if index < len(sgrs) and sgrs[index] and char not in " []()"
        else "90"
        for index, char in enumerate(identity)
    ]
    return prefix[marker:].replace("\n", ""), sgrs[marker:], identity, colors


class IdentityLineMixin:
    """Optional metadata row shared by fixed-region and inline bars."""

    def _identity_row_count(self) -> int:
        return int(bool(getattr(self, "_identity_text", "")))

    def _render_identity_line(self, width: int) -> str:
        """One row, always -- elided in the middle when the row is narrow.

        The row is painted with autowrap off, so an over-wide line is
        chopped rather than wrapped; chopping from the head alone hides
        the working directory, which is the half of the row people scan
        for. Eliding the middle keeps the puppy name AND the cwd on one
        row at any width.
        """
        text = sanitize(self._identity_text)
        if cell_len(text) <= width:
            return stylize_slice(text, 0, self._identity_sgrs)
        elided, keep = elide_middle(text, width)
        # split_identity pads the prompt's SGR list to the full prefix, but a
        # plugin-patched prompt can be shorter; pad defensively so the
        # elided row's styling stays index-aligned with its characters.
        padded = [
            *self._identity_sgrs,
            *([""] * max(0, len(text) - len(self._identity_sgrs))),
        ]
        sgrs = [_MUTED_SGR if index < 0 else padded[index] for index in keep]
        return stylize_slice(elided, 0, sgrs)

    def _identity_seq(self) -> str:
        if not self._identity_row_count():
            return ""
        row = self._rows - int(self._status_visible())
        return (
            f"\x1b7\x1b[?7l\x1b[{row};1H\x1b[2K"
            f"{self._render_identity_line(self._cols)}\x1b[?7h\x1b8"
        )
