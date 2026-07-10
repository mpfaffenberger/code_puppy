"""Interactive spinner picker TUI.

Same full-screen prompt_toolkit pattern as the theme plugin's picker,
but with a preview pane that actually *animates*: a background asyncio
task invalidates the app ~20x/sec, and the preview control derives the
current frame from wall-clock time, so every spinner runs at its own
configured interval.

Navigation follows the plugins-menu convention (same split-pane shape,
same muscle memory): ``j``/``k`` + arrows move the selection (clamped,
no wraparound), ``pageup``/``pagedown`` page through the list via the
shared pagination helpers, ``g``/``G``/``home``/``end`` jump to the
first/last entry, ``enter`` applies, and ``q``/``esc``/``ctrl-c`` bail.
``i`` writes the starter spinners.json without leaving; the animator
task also watches the file's mtime, so external edits reload the menu
live while the picker is open.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import List, Optional, Tuple

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)

from . import spinners as sp

#: Invalidation cadence for the preview animation. Pinned to the speed
#: floor so even a spinner dialed all the way down to MIN_INTERVAL
#: previews at its true speed (frames still pick their own timing).
_REFRESH_INTERVAL_S = sp.MIN_INTERVAL
PAGE_SIZE = 20  # one line per entry, same as the plugins menu
#: Speed-key step per keypress. Matches the MIN_INTERVAL clamp floor,
#: so the whole 0.02..1.0 range is one clean grid -- the floor is just
#: another grid point, never an off-grid clamp artifact.
_SPEED_STEP_S = 0.02


def _step_interval(current: float, delta: float) -> float:
    """One speed-key step from *current*: snap to the step grid, then clamp.

    Snapping matters at the edges: clamping alone strands you off-grid
    (0.05 -> floor 0.02 -> 0.07 -> 0.12 ...). Rounding to the nearest
    multiple of the step first means the floor is just a stop -- the
    next nudge up lands back on 0.05. Off-grid starting values (from a
    spinners.json tweak) get folded onto the grid the same way.
    """
    stepped = round((current + delta) / _SPEED_STEP_S) * _SPEED_STEP_S
    return sp.clamp_interval(stepped)


def _format_menu(
    entries: List[sp.Spinner], selected: int, page: int, active: str
) -> FormattedText:
    """Left-hand menu, styled to match the plugins menu's list pane.

    One line per entry: ``" > "`` marks the selection (bold), a green
    ``*`` glyph marks the active spinner (the plugins menu's ``+``/``x``
    slot), names only -- descriptions live in the preview pane, exactly
    like plugin descriptions live in the detail pane.
    """
    total_pages = get_total_pages(len(entries), PAGE_SIZE)
    start, end = get_page_bounds(page, len(entries), PAGE_SIZE)

    lines: list[tuple[str, str]] = [
        ("bold", " Spinners"),
        ("", "\n\n"),
    ]
    for i in range(start, end):
        spinner = entries[i]
        is_selected = i == selected
        icon = "*" if spinner.name == active else " "
        prefix = " > " if is_selected else "   "

        if is_selected:
            lines.append(("bold", prefix))
            lines.append(("fg:ansigreen bold", icon))
            lines.append(("bold", f" {spinner.name}"))
        else:
            lines.append(("", prefix))
            lines.append(("fg:ansigreen", icon))
            lines.append(("fg:ansibrightblack", f" {spinner.name}"))
        lines.append(("", "\n"))

    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", f" Page {page + 1}/{total_pages}"))
    lines.append(("", "\n"))

    _render_hints(lines)
    return FormattedText(lines)


#: (style, keys, action) rows for the hint block. Keys are padded to a
#: common cell width in ``_render_hints`` so the action column always
#: lines up -- hand-padding drifted the moment a row gained an arrow.
_HINTS = [
    ("fg:ansibrightblack", "up/down or j/k", "Navigate"),
    ("fg:ansibrightblack", "PgUp/PgDn", "Page"),
    ("fg:ansibrightblack", "g / G", "First / Last"),
    ("fg:ansibrightblack", "-/+ or \u2190/\u2192", "Slower / Faster"),
    ("fg:ansibrightblack", "i", "Init spinners.json"),
    ("fg:ansigreen", "Enter", "Apply"),
    ("fg:ansired", "q / Esc", "Exit"),
]


def _render_hints(lines: list[tuple[str, str]]) -> None:
    """The plugins menu's hint block, with a speed row where their
    detail-scroll row sits. The key column is computed, not hand-padded.
    """
    key_col = max(len(keys) for _, keys, _ in _HINTS) + 1
    lines.append(("", "\n"))
    for i, (style, keys, label) in enumerate(_HINTS):
        lines.append((style, f"  {keys.ljust(key_col)}"))
        lines.append(("", label if i == len(_HINTS) - 1 else f"{label}\n"))


def _format_preview(
    spinner: sp.Spinner,
    started_at: float,
    interval: Optional[float] = None,
    notice: str = "",
) -> FormattedText:
    """Right-hand pane, styled like the plugins menu's detail pane.

    *interval* is the speed the user dialed with the speed keys; None
    means the spinner's own speed (the usual case). *notice* is a
    one-line status message (e.g. the outcome of pressing ``i``).
    """
    effective = interval if interval is not None else spinner.interval
    elapsed = time.monotonic() - started_at
    frame = spinner.frames[int(elapsed / effective) % len(spinner.frames)]
    lines: list[tuple[str, str]] = [
        ("dim cyan", " LIVE PREVIEW"),
        ("", "\n\n"),
        ("bold", f"  {spinner.name}"),
        ("", "\n\n"),
    ]
    if spinner.description:
        lines.append(("", f"  {spinner.description}"))
        lines.append(("", "\n\n"))
    lines.extend(
        [
            ("bold", f"  {frame}"),
            ("", "\n\n"),
            ("bold", "  Source: "),
            ("", spinner.source),
            ("", "\n"),
            ("bold", "  Frames: "),
            ("", str(len(spinner.frames))),
            ("", "\n"),
            ("bold", "  Interval: "),
            ("", f"{effective:.2f}s"),
            (
                "fg:ansiyellow",
                "  (custom -- Enter saves it)" if interval is not None else "",
            ),
            ("", "\n\n"),
            ("bold", "  Custom spinners:"),
            ("", "\n"),
            ("fg:ansibrightblack", f"    {sp.USER_SPINNERS_FILE}"),
            ("", "\n"),
            ("fg:ansibrightblack", "    (press i to write a starter file)"),
            ("", "\n"),
        ]
    )
    if notice:
        lines.append(("", "\n"))
        lines.append(("fg:ansiyellow", f"  {notice}"))
        lines.append(("", "\n"))
    return FormattedText(lines)


async def interactive_spinner_picker() -> Optional[Tuple[str, Optional[float]]]:
    """Show the full-screen spinner picker.

    Returns:
        ``(name, interval)`` -- *interval* is the dialed custom speed or
        None for the spinner's own speed -- or ``None`` if cancelled.
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    entries = list(sp.get_catalogue().values())
    active = sp.get_active_spinner().name
    selected = [next((i for i, s in enumerate(entries) if s.name == active), 0)]
    page = [get_page_for_index(selected[0], PAGE_SIZE)]
    custom_interval: list[Optional[float]] = [None]
    notice = [""]
    result: list[Optional[Tuple[str, Optional[float]]]] = [None]
    started_at = time.monotonic()

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)

    def _set_selection(new_idx: int) -> None:
        """Clamp selection and keep its page visible (plugins-menu contract).

        Moving resets the dialed speed -- each entry previews at its own
        speed until you nudge it.
        """
        selected[0] = max(0, min(new_idx, len(entries) - 1))
        page[0] = ensure_visible_page(selected[0], page[0], len(entries), PAGE_SIZE)
        custom_interval[0] = None

    def _nudge_speed(delta: float) -> None:
        current = (
            custom_interval[0]
            if custom_interval[0] is not None
            else entries[selected[0]].interval
        )
        custom_interval[0] = _step_interval(current, delta)

    def _refresh_entries() -> None:
        """Re-read the catalogue in place, keeping the selection pinned by
        name. Shared by the ``i`` key and the live file watcher."""
        current_name = entries[selected[0]].name
        entries[:] = list(sp.get_catalogue().values())
        _set_selection(
            next((i for i, s in enumerate(entries) if s.name == current_name), 0)
        )

    def _change_page(delta: int) -> None:
        """Move the page by *delta* (clamped) and jump selection to its head."""
        total_pages = get_total_pages(len(entries), PAGE_SIZE)
        new_page = max(0, min(page[0] + delta, total_pages - 1))
        if new_page == page[0]:
            return
        page[0] = new_page
        _set_selection(new_page * PAGE_SIZE)

    kb = KeyBindings()

    # -- Selection (j = up, k = down -- plugins-menu convention) ------------
    @kb.add("up")
    @kb.add("c-p")
    @kb.add("j")
    def _(event):
        _set_selection(selected[0] - 1)
        event.app.invalidate()

    @kb.add("down")
    @kb.add("c-n")
    @kb.add("k")
    def _(event):
        _set_selection(selected[0] + 1)
        event.app.invalidate()

    # -- Page through the list ----------------------------------------------
    @kb.add("pageup")
    def _(event):
        _change_page(-1)
        event.app.invalidate()

    @kb.add("pagedown")
    def _(event):
        _change_page(+1)
        event.app.invalidate()

    # -- Jump to first / last -------------------------------------------------
    @kb.add("home")
    @kb.add("g")
    def _(event):
        _set_selection(0)
        event.app.invalidate()

    @kb.add("end")
    @kb.add("G")
    def _(event):
        _set_selection(len(entries) - 1)
        event.app.invalidate()

    # -- Speed (left/- slower, right/+ faster: interval moves inversely) ----
    @kb.add("left")
    @kb.add("-")
    def _(event):
        _nudge_speed(+_SPEED_STEP_S)
        event.app.invalidate()

    @kb.add("right")
    @kb.add("+")
    @kb.add("=")  # unshifted + on most layouts
    def _(event):
        _nudge_speed(-_SPEED_STEP_S)
        event.app.invalidate()

    # -- Init the user spinners file (no need to leave the menu) -----------
    @kb.add("i")
    def _(event):
        try:
            created = sp.write_template()
            notice[0] = (
                "Starter file written -- edit it freely, changes apply live."
                if created
                else "spinners.json already exists -- edit it directly."
            )
        except OSError as exc:
            notice[0] = f"Could not write starter file: {exc}"
        _refresh_entries()
        event.app.invalidate()

    # -- Actions / exit --------------------------------------------------------
    @kb.add("enter")
    def _(event):
        result[0] = (entries[selected[0]].name, custom_interval[0])
        event.app.exit()

    @kb.add("q")
    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    left = Window(
        content=FormattedTextControl(
            lambda: _format_menu(entries, selected[0], page[0], active)
        ),
        width=36,  # widest hint row is 35 cells; don't guillotine the json
    )
    right = Window(
        content=FormattedTextControl(
            lambda: _format_preview(
                entries[selected[0]], started_at, custom_interval[0], notice[0]
            )
        ),
    )

    layout = Layout(
        VSplit([Frame(left, title="Spinners"), Frame(right, title="Live Preview")])
    )
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    async def _animate() -> None:
        """Poke the app awake so the preview frame advances -- and watch
        spinners.json so external edits reload the menu while it's open
        (the same mtime signal the tick loop uses).
        """
        file_stamp = sp.user_file_stamp()
        try:
            while True:
                await asyncio.sleep(_REFRESH_INTERVAL_S)
                stamp = sp.user_file_stamp()
                if stamp != file_stamp:
                    file_stamp = stamp
                    _refresh_entries()
                app.invalidate()
        except asyncio.CancelledError:
            pass

    animator = asyncio.get_running_loop().create_task(_animate())
    try:
        await app.run_async()
    finally:
        animator.cancel()
        set_awaiting_user_input(False)
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    return result[0]
