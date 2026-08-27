"""Import-time neon splash: a shimmering Pydantic pyramid while imports load.

Code Puppy's cold start is dominated by heavy imports (pydantic-ai,
prompt_toolkit, rich, ...). This module is deliberately **stdlib-only** so
``code_puppy/main.py`` can start the animation *before* those imports begin
and stop it the moment they finish. Do not import anything from
``code_puppy`` here -- that would defeat the entire point.

The animation is pure art (no text), so it stays outside the i18n seam.
It runs full-screen on the alternate screen buffer, centered both axes;
leaving the alt screen on stop() restores the user's terminal exactly as
it was. Stray import-time output (e.g. plugin warnings emitted while
``cli_runner`` loads) is buffered and replayed afterwards. Everything
fails soft: a broken terminal gets a no-op splash, never a crashed CLI.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import threading

# Pyramid raster, 20 rows x <=44 cols. Digits are glow tiers:
# 0 = empty, 1 = outer halo, 2 = inner glow, 3 = neon core.
_PYRAMID = (
    "000000000000000000112333211",
    "0000000000000000112233233221",
    "000000000000000112332212232211",
    "0000000000000012233211012233211",
    "00000000000011223221100011233221",
    "0000000000011233221000000112232211",
    "00000000011223321100000000012233211",
    "000000001123322110001111100011233221",
    "00000001223321101112223222110112232211",
    "000001122322111122333333332221112233211",
    "0000112332211223332222322233322211233221",
    "001122332222333222111232111223333222232211",
    "0112332223332221100012321001112223332233211",
    "12233233322111000000123210000001122233333221",
    "22333322111000000000123210000000001122233322",
    "23333222111100000000123210000000011122233332",
    "11222333332221110000123210001111222333322211",
    "00011122223333222211123211122233333222111",
    "0000000011122233333222322233332222111",
    "00000000000011112223333333222111",
)
_CHARS = (" ", "\u2591", "\u2592", "\u2588")
_PYRAMID_WIDTH = 44

# "CODE PUPPY" / "PUP" pre-rendered in pyfiglet's ansi_shadow (the same
# font as the scrollback banner). Baked as constants: pyfiglet is not
# stdlib and this module must stay import-light. Solid blocks render as
# the neon core tier; the box-drawing shadow trim renders as the mid
# glow tier.
_BANNER_FULL = (
    " \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557    \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557   \u2588\u2588\u2557",
    "\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\u2588\u2588\u2554\u2550\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d    \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u255a\u2588\u2588\u2557 \u2588\u2588\u2554\u255d",
    "\u2588\u2588\u2551     \u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2557      \u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d \u255a\u2588\u2588\u2588\u2588\u2554\u255d",
    "\u2588\u2588\u2551     \u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u255d      \u2588\u2588\u2554\u2550\u2550\u2550\u255d \u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u255d \u2588\u2588\u2554\u2550\u2550\u2550\u255d   \u255a\u2588\u2588\u2554\u255d",
    "\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557    \u2588\u2588\u2551     \u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551     \u2588\u2588\u2551        \u2588\u2588\u2551",
    " \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d    \u255a\u2550\u255d      \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d     \u255a\u2550\u255d        \u255a\u2550\u255d",
)
_BANNER_FULL_WIDTH = 79
_BANNER_COMPACT = (
    "\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2557",
    "\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557",
    "\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d",
    "\u2588\u2588\u2554\u2550\u2550\u2550\u255d \u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u255d",
    "\u2588\u2588\u2551     \u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551",
    "\u255a\u2550\u255d      \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d",
)
_BANNER_COMPACT_WIDTH = 25
_SHADOW_TRIM = frozenset("\u2550\u2551\u2554\u2557\u255a\u255d")

_RESET = "\x1b[0m"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
# Alternate screen buffer (like vim/less): the splash owns a blank
# full-screen canvas, and leaving it restores the user's scrollback
# untouched -- no erase bookkeeping needed on the way out.
_ALT_SCREEN_ON = "\x1b[?1049h"
_ALT_SCREEN_OFF = "\x1b[?1049l"
_CLEAR_SCREEN = "\x1b[2J"
# Synchronized output (DEC 2026): terminals that support it (iTerm2, kitty,
# WezTerm, Ghostty, Alacritty, ...) render the whole frame atomically --
# zero flicker. Terminals that don't simply ignore the markers.
_SYNC_START = "\x1b[?2026h"
_SYNC_END = "\x1b[?2026l"

# Neon palette: violet haze -> brand magenta -> hot pink core, with a
# white-hot crest where the sheen band passes.
_TRUECOLOR_BASE = (
    "",
    "\x1b[38;2;122;17;145m",
    "\x1b[38;2;195;31;212m",
    "\x1b[1;38;2;255;92;244m",
)
_TRUECOLOR_HOT = (
    "",
    "\x1b[38;2;195;31;212m",
    "\x1b[38;2;255;92;244m",
    "\x1b[1;38;2;255;209;251m",
)
_FALLBACK_BASE = ("", "\x1b[35m", "\x1b[95m", "\x1b[1;95m")
_FALLBACK_HOT = ("", "\x1b[95m", "\x1b[1;95m", "\x1b[1;97m")

_SHEEN_PERIOD = 70
_SHEEN_WIDTH = 7
_FRAME_SECONDS = 0.033

#: Frame interval over a remote link. Each frame repaints the whole
#: raster, so the ~30fps local rate writes roughly a megabyte of escape
#: sequences during a one-second boot -- 99.7% of everything the CLI
#: writes to the terminal at startup. On a local terminal that is free.
#: Over SSH or a forwarded tmux it is the dominant cost of launching, and
#: the animation ends up *slower* than the imports it was hiding.
_REMOTE_FRAME_SECONDS = 0.1

#: Environment markers set by sshd on the remote side of a session.
_REMOTE_MARKERS = ("SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT")


def _frame_seconds() -> float:
    """Seconds between splash repaints, eased off on a remote link.

    Same animation, roughly a third of the bytes. Kept deliberately
    coarse: a precise bandwidth estimate is not worth a syscall on the
    startup path, and being wrong only costs a slightly choppier splash.
    """
    try:
        if any(os.environ.get(marker) for marker in _REMOTE_MARKERS):
            return _REMOTE_FRAME_SECONDS
    except Exception:
        pass
    return _FRAME_SECONDS


# argv values that still mean "interactive boot" (splash-worthy).
_INTERACTIVE_ARGS = frozenset({"-i", "--interactive"})


def _truecolor() -> bool:
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def _compose_rows(columns: int, lines: int):
    """Pick the biggest lockup the terminal can hold and lay it out.

    Returns a list of (kind, content) rows: ``art`` rows are pyramid tier
    digits, ``text`` rows are literal figlet glyphs. Degrades gracefully:
    pyramid + "CODE PUPPY" -> pyramid + "PUP" -> pyramid only.
    """
    full = [(line, _BANNER_FULL_WIDTH) for line in _BANNER_FULL]
    compact = [(line, _BANNER_COMPACT_WIDTH) for line in _BANNER_COMPACT]
    variants = (
        (full, _BANNER_FULL_WIDTH),
        (compact, _BANNER_COMPACT_WIDTH),
        ([], _PYRAMID_WIDTH),
    )
    for text_rows, text_width in variants:
        width = max(_PYRAMID_WIDTH, text_width)
        height = len(_PYRAMID) + (1 + len(text_rows) if text_rows else 0)
        if columns >= width + 2 and lines >= height + 2:
            break
    rows = []
    art_pad = "0" * ((width - _PYRAMID_WIDTH) // 2)
    for row in _PYRAMID:
        rows.append(("art", art_pad + row))
    if text_rows:
        rows.append(("text", ""))
        for line, block_width in text_rows:
            # Center each figlet block independently (blocks differ in width).
            pad = " " * ((width - block_width) // 2) if line else ""
            rows.append(("text", pad + line))
    return rows


def _center_rows(rows, columns: int):
    """Pad every row so the artwork block sits horizontally centered.

    Art rows pad with '0' (the empty glow tier) and text rows with spaces,
    so ``_build_frame`` needs no knowledge of centering at all.
    """
    block_width = max((len(content) for _, content in rows), default=0)
    pad = max(0, (columns - block_width) // 2)
    if not pad:
        return list(rows)
    return [
        (kind, ("0" * pad if kind == "art" else " " * pad) + content)
        for kind, content in rows
    ]


def _build_frame(phase: int, truecolor: bool, rows) -> str:
    """Render one frame as newline-joined lines with NO trailing newline.

    Cells are overwritten in place (row shapes are constant across frames,
    only colors change), so no erase codes are needed -- erase-then-redraw
    is exactly what flickers on terminals without synchronized output. The
    sheen band is computed from absolute (column, row) so it sweeps one
    continuous diagonal across the pyramid AND the figlet text below it.
    """
    base = _TRUECOLOR_BASE if truecolor else _FALLBACK_BASE
    hot = _TRUECOLOR_HOT if truecolor else _FALLBACK_HOT
    lines = []
    for y, (kind, content) in enumerate(rows):
        parts = []
        current = ""
        for x, ch in enumerate(content):
            if kind == "art":
                tier = int(ch)
                glyph = _CHARS[tier]
            else:
                tier = 3 if ch == "\u2588" else 2 if ch in _SHADOW_TRIM else 0
                glyph = ch
            if tier == 0:
                parts.append(" ")
                continue
            in_band = (x + 2 * y - phase) % _SHEEN_PERIOD < _SHEEN_WIDTH
            style = (hot if in_band else base)[tier]
            if style != current:
                parts.append(style)
                current = style
            parts.append(glyph)
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


class _NullSplash:
    """Do-nothing stand-in so callers never need to branch."""

    def stop(self) -> None:
        pass


class _StreamCapture(io.TextIOBase):
    """Buffers writes made while the splash owns the screen.

    Import-time code (plugin loading, theme setup, warnings) can print mid-
    animation; a single stray newline shifts the cursor and derails the
    relative-cursor redraws. So while the splash runs, sys.stdout/stderr
    point here, and everything is replayed verbatim after the splash erases
    itself -- output is deferred, never dropped.
    """

    def __init__(self, real, buffer: io.StringIO, lock: threading.Lock) -> None:
        self._real = real
        self._buffer = buffer
        self._lock = lock

    def write(self, s: str) -> int:
        with self._lock:
            self._buffer.write(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        # Mirror the real stream so import-time color/TTY sniffing behaves
        # exactly as it would without a splash.
        try:
            return self._real.isatty()
        except Exception:
            return False

    def fileno(self) -> int:
        return self._real.fileno()

    @property
    def encoding(self):
        return getattr(self._real, "encoding", "utf-8")


class _Splash:
    def __init__(self, stream) -> None:
        self._stream = stream
        self._stop_event = threading.Event()
        # Divert stdout/stderr into buffers for the splash's lifetime so
        # import-time output can't move the cursor mid-frame. Replayed in
        # stop(). Per-stream buffers keep each message on its real stream.
        lock = threading.Lock()
        self._out_buffer = io.StringIO()
        self._err_buffer = io.StringIO()
        self._orig_out, self._orig_err = sys.stdout, sys.stderr
        self._cap_out = _StreamCapture(self._orig_out, self._out_buffer, lock)
        self._cap_err = _StreamCapture(self._orig_err, self._err_buffer, lock)
        sys.stdout, sys.stderr = self._cap_out, self._cap_err
        self._truecolor = _truecolor()
        self._thread = threading.Thread(
            target=self._run, name="code-puppy-splash", daemon=True
        )
        size = shutil.get_terminal_size(fallback=(80, 24))
        self._rows = _center_rows(_compose_rows(size.columns, size.lines), size.columns)
        self._height = len(self._rows)
        # 1-based row where the frame starts, vertically centering the art.
        self._top_row = max(1, (size.lines - self._height) // 2 + 1)
        self._stopped = False
        self._thread.start()

    def _run(self) -> None:
        phase = 0
        # The alt screen is ours alone, so every frame repaints from the
        # same absolute, vertically-centered origin. The frame has no
        # trailing newline, so nothing ever scrolls.
        reposition = f"\x1b[{self._top_row};1H"
        try:
            first = _build_frame(phase, self._truecolor, self._rows)
            self._stream.write(
                f"{_ALT_SCREEN_ON}{_HIDE_CURSOR}{_CLEAR_SCREEN}"
                f"{_SYNC_START}{reposition}{first}{_SYNC_END}"
            )
            self._stream.flush()
            frame_seconds = _frame_seconds()
            while not self._stop_event.wait(frame_seconds):
                phase = (phase + 2) % _SHEEN_PERIOD
                frame = _build_frame(phase, self._truecolor, self._rows)
                # One atomic write per frame: no tearing between reposition
                # and repaint even without DEC 2026 support.
                self._stream.write(f"{_SYNC_START}{reposition}{frame}{_SYNC_END}")
                self._stream.flush()
        except Exception:
            pass  # a dying terminal must never take the CLI down

    def stop(self) -> None:
        """Stop the animation and erase it so real output starts clean."""
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        try:
            # Leaving the alt screen restores the pre-splash terminal
            # content and cursor position in one move; nothing to erase.
            self._stream.write(f"{_ALT_SCREEN_OFF}{_SHOW_CURSOR}")
            self._stream.flush()
        except Exception:
            pass
        # Hand the streams back (only if nobody else swapped them since),
        # then replay everything that printed during the show.
        if sys.stdout is self._cap_out:
            sys.stdout = self._orig_out
        if sys.stderr is self._cap_err:
            sys.stderr = self._orig_err
        for buffer, real in (
            (self._out_buffer, self._orig_out),
            (self._err_buffer, self._orig_err),
        ):
            pending = buffer.getvalue()
            if pending:
                try:
                    real.write(pending)
                    real.flush()
                except Exception:
                    pass


def _wants_splash(argv: list[str]) -> bool:
    """Only animate for an interactive-looking boot; fail closed otherwise."""
    if os.environ.get("CODE_PUPPY_NO_SPLASH") or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    # Any flag beyond plain interactive mode (headless -p, --help, acp
    # bridges, ...) means someone else owns stdout. Stay out of the way.
    return all(arg in _INTERACTIVE_ARGS for arg in argv[1:])


def _enable_windows_vt(stream) -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def start_splash(stream=None, force: bool = False):
    """Start the shimmer if the terminal deserves it; else return a no-op.

    ``force=True`` bypasses ALL gating -- TTY detection included -- and is
    strictly for tests and demos; you get ANSI in whatever stream you gave
    us.
    """
    stream = stream if stream is not None else sys.stdout
    try:
        if not force:
            if not (hasattr(stream, "isatty") and stream.isatty()):
                return _NullSplash()
            if not _wants_splash(sys.argv):
                return _NullSplash()
            # _compose_rows degrades CODE PUPPY -> PUP -> bare pyramid,
            # but below even the pyramid's footprint there is nothing
            # honest left to draw: stay silent, never clip art.
            size = shutil.get_terminal_size(fallback=(80, 24))
            if size.columns < _PYRAMID_WIDTH + 2 or size.lines < len(_PYRAMID) + 2:
                return _NullSplash()
        if not _enable_windows_vt(stream):
            return _NullSplash()
        return _Splash(stream)
    except Exception:
        return _NullSplash()
