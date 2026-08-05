"""Compatibility patches for the external Termflow Markdown renderer."""

from __future__ import annotations

from typing import Any


_PATCH_MARKER = "_code_puppy_table_alignment_patch"


def patch_termflow_table_alignment() -> None:
    """Preserve one alignment entry for every Markdown table column.

    Termflow currently skips unaligned ``---`` separator cells. A separator
    such as ``|---|---|---:|`` therefore emits ``("right",)`` instead of
    ``("none", "none", "right")``, shifting alignment metadata onto the
    wrong columns. Keep the compatibility patch here until Termflow ships the
    corresponding parser fix.
    """
    try:
        from termflow.parser.parser import Parser
    except ImportError:
        return

    original = getattr(Parser, "_parse_table_alignments", None)
    if original is None or getattr(original, _PATCH_MARKER, False):
        return

    def _parse_table_alignments(self: Any, content: str) -> None:
        self.table_alignments.clear()
        for raw_cell in content.split("|"):
            cell = raw_cell.strip()
            if not cell:
                continue
            if cell.startswith(":") and cell.endswith(":"):
                alignment = "center"
            elif cell.endswith(":"):
                alignment = "right"
            elif cell.startswith(":"):
                alignment = "left"
            else:
                alignment = "none"
            self.table_alignments.append(alignment)

    setattr(_parse_table_alignments, _PATCH_MARKER, True)
    Parser._parse_table_alignments = _parse_table_alignments


__all__ = ["patch_termflow_table_alignment"]
