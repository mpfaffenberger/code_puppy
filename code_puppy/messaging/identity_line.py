"""Separate prompt metadata from input and paint its single chrome row."""

from .bar_rendering import clip_cells, sanitize, stylize_slice


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
        text = clip_cells(sanitize(self._identity_text), width)
        return stylize_slice(text, 0, self._identity_sgrs)

    def _identity_seq(self) -> str:
        if not self._identity_row_count():
            return ""
        row = self._rows - int(self._status_visible())
        return (
            f"\x1b7\x1b[?7l\x1b[{row};1H\x1b[2K"
            f"{self._render_identity_line(self._cols)}\x1b[?7h\x1b8"
        )
