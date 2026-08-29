"""Compatibility patches for the external Termflow Markdown renderer."""

from __future__ import annotations

from typing import Any


_PATCH_MARKER = "_code_puppy_table_alignment_patch"


def _patch_failed(
    patch_name: str,
    exc: BaseException,
    consequence: str,
) -> bool:
    """Report a broken Termflow patch through the central patch logger."""
    from code_puppy.pydantic_patches import _patch_failed as report_failure

    return report_failure(patch_name, exc, consequence, target="termflow")


def _optional_lib_missing(patch_name: str, exc: ImportError) -> bool:
    """Report an unavailable optional Termflow dependency quietly."""
    from code_puppy.pydantic_patches import (
        _optional_lib_missing as report_missing,
    )

    return report_missing(patch_name, exc)


def patch_termflow_clipboard() -> bool:
    """Disable Termflow's OSC 52 clipboard hijacking globally."""
    try:
        from termflow.render.renderer import Renderer
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_clipboard", exc)

    try:
        if not hasattr(Renderer, "_copy_to_clipboard"):
            raise AttributeError("termflow Renderer._copy_to_clipboard not found")
        Renderer._copy_to_clipboard = lambda self, text: None  # type: ignore[method-assign]
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_clipboard",
            exc,
            "OSC 52 clipboard hijacking is ACTIVE; code blocks may silently "
            "overwrite the user's clipboard.",
        )


def _no_pad_render_code_line(_line, highlighted, width, margin, style, pretty_pad=True):
    """Drop-in for Termflow's code-line renderer without trailing padding."""
    return f"{margin}{highlighted}"


def patch_termflow_code_padding() -> bool:
    """Strip trailing-space padding from Termflow code lines (#505)."""
    try:
        import termflow.render.code as _termflow_code
        import termflow.render.renderer as _termflow_renderer
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_code_padding", exc)

    try:
        if not hasattr(_termflow_code, "render_code_line") or not hasattr(
            _termflow_renderer, "render_code_line"
        ):
            raise AttributeError("termflow render_code_line not found")
        _termflow_code.render_code_line = _no_pad_render_code_line
        _termflow_renderer.render_code_line = _no_pad_render_code_line
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_code_padding",
            exc,
            "code lines keep invisible trailing-space padding (copy/paste corruption).",
        )


def patch_termflow_table_alignment() -> bool:
    """Preserve one alignment entry for every Markdown table column.

    Termflow currently skips unaligned ``---`` separator cells. A separator
    such as ``|---|---|---:|`` therefore emits ``("right",)`` instead of
    ``("none", "none", "right")``, shifting alignment metadata onto the
    wrong columns. Keep the compatibility patch here until Termflow ships the
    corresponding parser fix.
    """
    try:
        from termflow.parser.parser import Parser
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_table_alignment", exc)

    try:
        original = getattr(Parser, "_parse_table_alignments", None)
        if original is None:
            raise AttributeError("termflow Parser._parse_table_alignments not found")
        if getattr(original, _PATCH_MARKER, False):
            return True

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
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_table_alignment",
            exc,
            "table alignment metadata may shift onto the wrong columns.",
        )


__all__ = [
    "patch_termflow_clipboard",
    "patch_termflow_code_padding",
    "patch_termflow_table_alignment",
]
