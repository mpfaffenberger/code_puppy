"""Layout + row painters for the bottom bar (mixin).

Split out of ``bottom_bar.py`` for the 600-line cap. Everything here is
pure computation over the bar's state → escape strings; the stateful
scroll-region lifecycle stays in :class:`BottomBar`, which mixes this in.

Bottom-up reserved-row layout (Claude Code style: status UNDER the
prompt, and only while it has something to say):

    row H                     status row (spinner + tokens) — reserved
                              ONLY when non-empty; otherwise the prompt
                              block is the bottom of the screen
    popup rows                completion popup, directly BELOW the prompt
    rows above popup          prompt viewport (1..PROMPT_MAX_ROWS)
    panel rows                sub-agent panel (hidden while popup open)
    top margin                blank separator below the transcript

The popup opens UNDER the typed line (IDE-dropdown feel): the prompt
rows slide up to make room — the existing ``_sync_reserved``
grow/shrink machinery provides the motion. On close the prompt does
NOT slide back down: the vacated rows persist as blank ``_popup_slack``
until ``notify_transcript_output`` reclaims them, so the prompt falls
back into place only when new output is scrolling anyway. The same
machinery materializes/collapses the status row when its text appears
or empties (``_total_reserved`` changes → region grows/shrinks).
"""

from __future__ import annotations

import re

from .bar_rendering import (
    CLEAR_LINE as _CLEAR_LINE,
)
from .bar_rendering import (
    RESTORE_CURSOR as _RESTORE_CURSOR,
)
from .bar_rendering import (
    SAVE_CURSOR as _SAVE_CURSOR,
)
from .bar_rendering import (
    WRAP_OFF as _WRAP_OFF,
)
from .bar_rendering import (
    WRAP_ON as _WRAP_ON,
)
from .bar_rendering import (
    clip_cells as _clip_cells,
)
from .bar_rendering import (
    count_prompt_rows as _count_prompt_rows,
)
from .bar_rendering import (
    render_prompt_block as _render_prompt_block,
)
from .bar_rendering import (
    render_styled_line as _render_styled_line,
)
from .bar_rendering import (
    sanitize as _sanitize,
)

#: Maximum rows for the multiline prompt viewport.
PROMPT_MAX_ROWS = 5

#: Chrome dimming (SGR 2): popup/status/panel rows render faint so they
#: read as UI chrome, not transcript content. Applied AFTER sanitization
#: and AFTER clipping — sanitize strips completer/user-supplied escapes,
#: and clip math must never count our own SGR bytes as cells.
_DIM_ON = "\x1b[2m"
_DIM_OFF = "\x1b[22m"

#: Selected popup row: full-brightness brand accent (bold + ANSI cyan,
#: SGR 1;36) instead of reverse video. WHY ANSI cyan and not truecolor:
#: the theme plugin recolors the terminal by remapping ANSI palette
#: slots via OSC 4 (osc_palette.py) — there is no runtime accent-token
#: accessor to query — so emitting the standard cyan slot means themes
#: restyle the selection automatically, and the default palette shows
#: the repo-wide "bold cyan" brand accent (rich_renderer et al.).
_SELECT_ON = "\x1b[1;36m"
_SELECT_OFF = "\x1b[22;39m"  # reset weight + foreground only
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _prompt_color_sgr() -> str:
    """Resolve a plugin-provided truecolor foreground for prompt text."""
    try:
        from code_puppy.callbacks import on_prompt_text_color

        color = on_prompt_text_color()
        if color and _HEX_COLOR_RE.fullmatch(color):
            red, green, blue = (
                int(color[index : index + 2], 16) for index in (1, 3, 5)
            )
            return f"\x1b[38;2;{red};{green};{blue}m"
    except Exception:
        pass
    return ""


def _dim(text: str) -> str:
    """Wrap ``text`` in faint SGR (no-op for empty strings)."""
    return f"{_DIM_ON}{text}{_DIM_OFF}" if text else text


def _panel_overflow_row(hidden: int) -> str:
    """A single summary row standing in for ``hidden`` sub-agent panel
    rows that were clamped off because they don't fit the terminal
    height. Emitted as a plain string so it dims like every other panel
    row at paint time (no double-dimming)."""
    return f"\u2026 +{hidden} more"


class BarPainterMixin:
    """Layout math + reserved-row painters for :class:`BottomBar`."""

    def _prompt_row_count(self) -> int:
        """Rows the prompt viewport needs (1..PROMPT_MAX_ROWS).

        Counts SOFT-WRAPPED visual rows (cell-accurate), so a long
        single-logical-line buffer grows the viewport instead of
        scrolling horizontally.
        """
        width = self._cols if self._cols > 0 else 80
        count = _count_prompt_rows(
            self._prompt_prefix, self._prompt_buffer, self._prompt_cursor, width
        )
        return max(1, min(PROMPT_MAX_ROWS, count))

    def _visible_popup_lines(self) -> list:
        """Popup rows that actually fit — the prompt viewport WINS.

        When the terminal is short, the popup sheds rows (bottom-first)
        before the small-terminal dormancy logic would trigger: margin +
        prompt + status always keep their space, plus one scroll row.
        """
        if not self._popup_lines:
            return []
        rows = self._rows if self._rows > 0 else 24
        # top margin + (possible) status + one scroll row keep their space.
        budget = rows - self._prompt_row_count() - 3
        return self._popup_lines[: max(0, budget)]

    def _visible_popup_slack(self) -> int:
        """Blank rows still reserved below the prompt after the popup
        shrank/closed (high-water residue awaiting lazy reclaim).

        Clamped to whatever the popup's own row budget has left, so a
        short terminal sheds slack exactly like it sheds popup rows.
        """
        slack = self._popup_slack
        if slack <= 0:
            return 0
        rows = self._rows if self._rows > 0 else 24
        budget = rows - self._prompt_row_count() - 3 - len(self._visible_popup_lines())
        return max(0, min(slack, budget))

    def _panel_row_budget(self) -> int:
        """Max panel rows that fit without forcing the bar dormant.

        Mirrors :meth:`_visible_popup_lines`' "prompt viewport WINS" rule:
        the top margin, prompt, popup, and status always keep their rows,
        plus one scroll row for the transcript region. Whatever height is
        left is the panel's viewport budget. An optional user ceiling can
        reduce it further, but can never override terminal safety. This keeps
        a big sub-agent swarm from overflowing past ``rows - 1`` and tripping
        the ``rows < reserved + 1`` dormancy guard in :meth:`_establish`
        (which would blank the panel, prompt, AND status all at once).
        """
        rows = self._rows if self._rows > 0 else 24
        non_panel = (
            1  # top margin (blank separator below the transcript)
            + self._prompt_row_count()
            + len(self._visible_popup_lines())
            + self._visible_popup_slack()
            + (1 if self._status_visible() else 0)
        )
        viewport_budget = max(0, rows - 1 - non_panel)
        configured_max = self._panel_max_rows
        if configured_max > 0:
            return min(viewport_budget, configured_max)
        return viewport_budget

    def _visible_panel_lines(self) -> list:
        """Panel rows to paint — popup takes precedence while open, and the
        list is clamped to :meth:`_panel_row_budget` so it can never
        overflow the terminal height. When the panel is taller than the
        budget, the last visible row collapses the remainder into a
        "+N more" summary instead of dropping the whole bar.
        """
        if self._visible_popup_lines():
            return []
        panel = self._panel_lines
        budget = self._panel_row_budget()
        if len(panel) <= budget:
            return panel
        if budget <= 0:
            return []
        hidden = len(panel) - (budget - 1)
        return panel[: budget - 1] + [_panel_overflow_row(hidden)]

    def _status_visible(self) -> bool:
        """The status row exists only while ANY slot has content."""
        return bool(self._status_prefix or self._status or self._status_suffix)

    def _total_reserved(self) -> int:
        """Rows needed: top margin + panel + prompt + popup + status."""
        return (
            1  # top margin (blank separator below the transcript)
            + len(self._visible_panel_lines())
            + self._prompt_row_count()
            + len(self._visible_popup_lines())
            + self._visible_popup_slack()
            + (1 if self._status_visible() else 0)
        )

    def _row_anchors(self) -> tuple:
        """(prompt_top, popup_top, status_row, panel_top) row numbers.

        Bottom-up layout: status on row H (when visible); completion
        popup directly above it (i.e. BELOW the prompt — first candidate
        on the popup's top row, adjacent to the typed line); prompt
        block above the popup; panel above the prompt; top margin above
        the panel. ``status_row`` is always H — ``_status_seq`` checks
        visibility itself.
        """
        rows = self._rows
        status_rows = 1 if self._status_visible() else 0
        popup_top = (
            rows
            - status_rows
            - self._visible_popup_slack()
            - len(self._visible_popup_lines())
            + 1
        )
        prompt_top = popup_top - self._prompt_row_count()
        panel_top = prompt_top - len(self._visible_panel_lines())
        return prompt_top, popup_top, rows, panel_top

    def _reserved_rows_seq(self) -> str:
        """Paint every reserved row: margin + panel + prompt + popup + status."""
        return (
            self._top_margin_seq()
            + self._panel_seq()
            + self._prompt_seq()
            + self._popup_seq()
            + self._status_seq()
        )

    def _panel_seq(self) -> str:
        """Save cursor, paint the sub-agent panel rows, restore cursor."""
        panel = self._visible_panel_lines()
        if not panel:
            return ""
        from rich.text import Text

        parts = [_SAVE_CURSOR, _WRAP_OFF]
        _pt, _pop, _status, panel_top = self._row_anchors()
        for i, line in enumerate(panel):
            if isinstance(line, Text):
                # Styled row: SGRs regenerated from trusted Style objects,
                # segment text sanitized in render_styled_line. Painted at
                # full color -- live rows should match the frozen record.
                text = _render_styled_line(line, self._cols)
            else:
                # Plain string row (pre-sanitized): dim = chrome.
                text = _dim(_clip_cells(line, self._cols))
            parts.append(f"\x1b[{panel_top + i};1H{_CLEAR_LINE}{text}")
        parts.append(_WRAP_ON)
        parts.append(_RESTORE_CURSOR)
        return "".join(parts)

    def _popup_seq(self) -> str:
        """Save cursor, paint the completion popup rows, restore cursor.

        Chrome styling applied HERE, after sanitization (user text can't
        carry escapes) and after clipping (SGR bytes never count as
        cells): the selected row renders in the full-brightness brand
        accent; every other row renders dim so the popup doesn't blend
        into the transcript scrolling above it.
        """
        popup = self._visible_popup_lines()
        slack = self._visible_popup_slack()
        if not popup and not slack:
            return ""
        parts = [_SAVE_CURSOR, _WRAP_OFF]
        _pt, popup_top, _status, _panel = self._row_anchors()
        for i, line in enumerate(popup):
            text = _clip_cells(line, self._cols)
            if i == self._popup_selected:
                text = f"{_SELECT_ON}{text}{_SELECT_OFF}"
            else:
                text = _dim(text)
            parts.append(f"\x1b[{popup_top + i};1H{_CLEAR_LINE}{text}")
        # Slack rows (below any remaining popup rows) must be actively
        # blanked — they still hold the closed menu's paint otherwise.
        for j in range(slack):
            parts.append(f"\x1b[{popup_top + len(popup) + j};1H{_CLEAR_LINE}")
        parts.append(_WRAP_ON)
        parts.append(_RESTORE_CURSOR)
        return "".join(parts)

    def _status_seq(self) -> str:
        """Save cursor, paint the status row (dim — chrome), restore.

        The row is ``status_prefix + status``: the prefix is the spinner
        slot (animated by the puppy_spinner plugin), the status is the
        token/context info — two writers, one row, zero stomping. While
        both slots are empty the row isn't reserved at all, so there is
        nothing to paint.
        """
        if not self._status_visible():
            return ""
        _pt, _pop, status_row, _panel = self._row_anchors()
        combined = f"{self._status_prefix}{self._status}{self._status_suffix}"
        text = _dim(_clip_cells(_sanitize(combined), self._cols))
        return (
            f"{_SAVE_CURSOR}{_WRAP_OFF}\x1b[{status_row};1H{_CLEAR_LINE}{text}"
            f"{_WRAP_ON}{_RESTORE_CURSOR}"
        )

    def _prompt_seq(self) -> str:
        """Save cursor, paint the prompt viewport rows, restore cursor."""
        prompt_top, _pop, _status, _panel = self._row_anchors()
        rendered_rows, _cursor_row = _render_prompt_block(
            self._prompt_prefix,
            self._prompt_buffer,
            self._prompt_cursor,
            self._cols,
            PROMPT_MAX_ROWS,
            prefix_sgrs=getattr(self, "_prompt_prefix_sgrs", None),
        )
        parts = [_SAVE_CURSOR, _WRAP_OFF]
        prompt_sgr = _prompt_color_sgr()
        prompt_reset = "\x1b[39m" if prompt_sgr else ""
        for i, rendered in enumerate(rendered_rows):
            if prompt_sgr:
                # Prefix styling uses full SGR resets between color runs. Restore
                # the theme foreground after each reset so user text doesn't
                # fall back to terminal-default white on light themes.
                rendered = rendered.replace("\x1b[0m", f"\x1b[0m{prompt_sgr}")
            parts.append(
                f"\x1b[{prompt_top + i};1H{_CLEAR_LINE}"
                f"{prompt_sgr}{rendered}{prompt_reset}"
            )
        parts.append(_WRAP_ON)
        parts.append(_RESTORE_CURSOR)
        return "".join(parts)

    def _top_margin_seq(self) -> str:
        """Save cursor, blank the top margin row, restore cursor.

        This row separates the transcript's last line from the bar chrome
        (panel/status/spinner/prompt) with guaranteed breathing room. It
        must be actively CLEARED, not just reserved: rows entering the
        reserved area may still hold old transcript text.
        """
        _pt, _pop, _status, panel_top = self._row_anchors()
        return f"{_SAVE_CURSOR}\x1b[{panel_top - 1};1H{_CLEAR_LINE}{_RESTORE_CURSOR}"


__all__ = ["PROMPT_MAX_ROWS", "BarPainterMixin"]
