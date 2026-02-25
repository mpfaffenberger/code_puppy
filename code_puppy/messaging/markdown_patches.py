"""Patches for Rich's Markdown rendering and termflow word wrapping.

This module provides customizations to Rich's default Markdown rendering,
particularly for header justification which is hardcoded to center in Rich.

It also patches termflow's wrap_ansi to honour word boundaries instead of
cutting mid-word at the column limit.
"""

from rich import box
from rich.markdown import Heading, Markdown
from rich.panel import Panel
from rich.text import Text


class LeftJustifiedHeading(Heading):
    """A heading that left-justifies text instead of centering.

    Rich's default Heading class hardcodes `text.justify = 'center'`,
    which can look odd in a CLI context. This subclass overrides that
    to use left justification instead.
    """

    def __rich_console__(self, console, options):
        """Render the heading with left justification."""
        text = self.text
        text.justify = "left"  # Override Rich's default 'center'

        if self.tag == "h1":
            # Draw a border around h1s (same as Rich default)
            yield Panel(
                text,
                box=box.HEAVY,
                style="markdown.h1.border",
            )
        else:
            # Styled text for h2 and beyond (same as Rich default)
            if self.tag == "h2":
                yield Text("")
            yield text


_patched = False


def patch_markdown_headings():
    """Patch Rich's Markdown to use left-justified headings.

    This function is idempotent - calling it multiple times has no effect
    after the first call.
    """
    global _patched
    if _patched:
        return

    Markdown.elements["heading_open"] = LeftJustifiedHeading
    _patched = True


# ---------------------------------------------------------------------------
# termflow word-wrap patch
# ---------------------------------------------------------------------------

_termflow_patched = False


def _word_boundary_wrap_ansi(text: str, width: int) -> list[str]:
    """Wrap *text* to *width* columns at word boundaries, preserving ANSI codes.

    This is a drop-in replacement for ``termflow.ansi.utils.wrap_ansi``.
    The original implementation wraps character-by-character without any
    word-boundary awareness, which causes words to be split mid-character
    at the column limit.  This version:

    1. Tokenises the input into ``(kind, value)`` pairs where *kind* is
       either ``'ansi'`` or ``'word'`` / ``'space'``.
    2. Fills the current output line with whole words, greedy left-to-right.
    3. On overflow, starts a new line and re-emits the active ANSI codes.
    4. Falls back to character-boundary wrapping only for words that are
       individually wider than *width* (une hard break).
    """
    import re

    from wcwidth import wcwidth

    if width <= 0:
        return [text] if text else []

    # ------------------------------------------------------------------
    # Regex from termflow.ansi.utils (replicated to avoid circular deps)
    # ------------------------------------------------------------------
    ANSI_RE = re.compile(
        r"\x1b"
        r"(?:"
        r"\[[0-9;?]*[a-zA-Z]"
        r"|"
        r"\][0-9]*;[^\x1b]*(?:\x1b\\|\x07)"
        r"|"
        r"\[\?[0-9;]*[a-zA-Z]"
        r"|"
        r"[()][AB0-9]"
        r")"
    )
    ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
    RESET = "\x1b[0m"

    def _visible_width(s: str) -> int:
        from wcwidth import wcswidth

        plain = ANSI_RE.sub("", s)
        w = wcswidth(plain)
        return w if w >= 0 else sum(max(0, wcwidth(c)) for c in plain)

    def _is_ansi(s: str) -> bool:
        m = ANSI_RE.match(s)
        return m is not None and m.group() == s

    def _update_active(active: list[str], code: str) -> None:
        """Mutate *active* to reflect the new SGR code."""
        m = ANSI_SGR_RE.match(code)
        if not m:
            return
        params_str = m.group(1)
        params = [int(p) for p in params_str.split(";") if p] if params_str else [0]
        if 0 in params:
            active.clear()
        # keep non-reset codes
        if params != [0]:
            active.append(code)

    # ------------------------------------------------------------------
    # Tokenise into segments: ANSI codes, words, and spaces
    # ------------------------------------------------------------------
    # We split on runs of spaces so that each token is either:
    #   ('ansi',  <escape-seq>)
    #   ('space', <one-or-more-spaces>)
    #   ('text',  <non-space run that may contain ANSI codes>)
    tokens: list[tuple[str, str]] = []
    pos = 0
    for m in re.finditer(r"\x1b[^\x1b]*?[a-zA-Z]| +|\S+", text):
        tokens.append(("raw", m.group()))

    # ------------------------------------------------------------------
    # Line-filling loop
    # ------------------------------------------------------------------
    lines: list[str] = []
    current: list[str] = []   # fragments on the current line
    col = 0                   # visible width of current line
    active_codes: list[str] = []  # currently active ANSI SGR codes

    def _flush_line() -> None:
        """Commit the current line to *lines* and reset state."""
        nonlocal col
        if active_codes:
            current.append(RESET)
        lines.append("".join(current))
        current.clear()
        # Re-open active styles on the new line
        current.extend(active_codes)
        col = 0

    for _, raw in tokens:
        # ---- pure ANSI code? ----
        if _is_ansi(raw):
            _update_active(active_codes, raw)
            current.append(raw)
            continue

        # ---- space run? ----
        if raw.lstrip(" ") == "":
            space_w = len(raw)  # spaces are always width-1
            if col + space_w <= width:
                current.append(raw)
                col += space_w
            else:
                # Space at EOL — skip it (acts as the line break)
                _flush_line()
            continue

        # ---- text token (may embed ANSI codes, treat as a word) ----
        word_w = _visible_width(raw)

        if word_w <= width:
            # Does it fit on the current line?
            gap = 1 if col > 0 else 0  # space before word already accounted for
            # The space was a separate token, so just check the word itself
            if col + word_w <= width:
                current.append(raw)
                col += word_w
            else:
                # Doesn't fit → new line, then place word
                _flush_line()
                current.append(raw)
                col = word_w
        else:
            # Word is wider than the whole line → hard-break inside the word
            for char in ANSI_RE.split(raw):
                if not char:
                    continue
                if _is_ansi(char):
                    _update_active(active_codes, char)
                    current.append(char)
                    continue
                for ch in char:
                    ch_w = max(0, wcwidth(ch))
                    if col + ch_w > width and col > 0:
                        _flush_line()
                    current.append(ch)
                    col += ch_w

    if current:
        lines.append("".join(current))

    return lines if lines else [""]


def patch_termflow_word_wrap() -> None:
    """Monkey-patch termflow's ``wrap_ansi`` to use word-boundary wrapping.

    This is idempotent — safe to call multiple times.

    Important: termflow.render.text does ``from termflow.ansi import wrap_ansi``
    which creates a *local* binding that is unaffected by patching the source
    module.  We must also replace that local reference directly.
    """
    global _termflow_patched
    if _termflow_patched:
        return

    try:
        import termflow.ansi.utils as _tfu
        import termflow.ansi as _tfa

        # Patch the canonical location
        _tfu.wrap_ansi = _word_boundary_wrap_ansi  # type: ignore[attr-defined]
        # Patch the public re-export in termflow.ansi.__init__
        if hasattr(_tfa, "wrap_ansi"):
            _tfa.wrap_ansi = _word_boundary_wrap_ansi  # type: ignore[attr-defined]

        # CRITICAL: termflow.render.text does `from termflow.ansi import wrap_ansi`
        # which caches a local reference — we must patch it directly too.
        try:
            import termflow.render.text as _tfrt
            if hasattr(_tfrt, "wrap_ansi"):
                _tfrt.wrap_ansi = _word_boundary_wrap_ansi  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

        _termflow_patched = True
    except Exception:  # pragma: no cover
        # If termflow isn't available (e.g. unit-test environment), skip silently.
        pass


__all__ = [
    "patch_markdown_headings",
    "patch_termflow_word_wrap",
    "LeftJustifiedHeading",
]
