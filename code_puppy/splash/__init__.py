"""Code Puppy's startup splash: an animation while the runtime imports.

Stdlib-only, so it is on screen before anything heavy loads. It stands in for
pax's ``Splash``: pax's ``cli.run(splash=...)`` only ever calls :meth:`stop`.
While it runs, anything printed is held back and replayed when it stops.
Each launch plays one of :data:`SCENES`, picked at random.
"""

from __future__ import annotations

import codecs
import contextlib
import io
import os
import random
import shutil
import sys
import threading

from code_puppy.splash.canvas import Canvas, truecolor
from code_puppy.splash.scenes import SCENES, Scene, caption

MIN_COLUMNS = 46
MIN_LINES = 22
FRAME_SECONDS = 1 / 30

ENTER = "\x1b[?1049h\x1b[?25l"
"""Switch to the alternate screen and hide the cursor."""
LEAVE = "\x1b[?1049l\x1b[?25h"
"""Leave the alternate screen and show the cursor again."""

__all__ = ["SCENES", "Splash"]


def _speaks_unicode(stream: object) -> bool:
    """Whether ``stream`` can write the scenes' block and circle glyphs.

    A stream without an encoding (a ``StringIO``) takes any text.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    try:
        return codecs.lookup(encoding).name.startswith("utf")
    except LookupError:
        return False


class Splash:
    """Own the alternate screen and animate a scene until :meth:`stop`."""

    def __init__(self, *, enabled: bool = True, scene: Scene | None = None) -> None:
        self._scene = scene or random.choice(list(SCENES.values()))
        self._stream = sys.stdout
        self._originals = (sys.stdout, sys.stderr)
        self._buffers = (io.StringIO(), io.StringIO())
        self._stop = threading.Event()
        self._lock = threading.Lock()
        """Held for each write, so no frame can follow the one that leaves the screen."""
        self._thread: threading.Thread | None = None
        self._deep = truecolor()
        size = shutil.get_terminal_size()
        self._enabled = (
            enabled
            and self._stream.isatty()
            and not os.getenv("NO_COLOR")
            and os.getenv("TERM") != "dumb"
            and size.columns >= MIN_COLUMNS
            and size.lines >= MIN_LINES
            and sys.platform != "win32"
            and _speaks_unicode(self._stream)
        )

    def frame(self, tick: int, columns: int, lines: int) -> str:
        """Frame ``tick`` for a ``columns`` x ``lines`` terminal.

        The last column stays empty: writing it makes some terminals wrap.
        """
        canvas = Canvas(columns - 1, lines)
        self._scene(canvas, tick)
        caption(canvas, tick)
        return canvas.render(deep=self._deep)

    def start(self) -> None:
        """Start one animation thread and hold back output until :meth:`stop`.

        Output is held back only once the thread runs: if it cannot start,
        startup carries on without the animation and with its streams intact.
        """
        if not self._enabled or self._thread is not None:
            return
        thread = threading.Thread(
            target=self._run, name="code-puppy-splash", daemon=True
        )
        try:
            thread.start()
        except RuntimeError:  # "can't start new thread": no animation, that's all
            return
        self._thread = thread
        sys.stdout, sys.stderr = self._buffers

    def _run(self) -> None:
        """Paint until stopped. Any failure hands the screen back and stops painting.

        Held-back output still waits for :meth:`stop`, which replays it.
        """
        try:
            self._draw(ENTER)
            tick, size = 0, None
            while not self._stop.is_set():
                size = self._paint(tick, size)
                tick += 1
                self._stop.wait(FRAME_SECONDS)
        except Exception:  # noqa: BLE001 - a broken frame must not blank the screen
            with contextlib.suppress(Exception):
                self._leave()

    def _paint(self, tick: int, previous: os.terminal_size | None) -> os.terminal_size:
        """Write frame ``tick`` at the current size, clearing first if it changed."""
        size = shutil.get_terminal_size()
        clear = "\x1b[2J" if size != previous else ""
        frame = self.frame(tick, size.columns, size.lines)
        self._draw(f"\x1b[?2026h{clear}{frame}\x1b[?2026l")
        return size

    def _draw(self, text: str) -> None:
        """Write ``text`` unless the splash is stopping."""
        with self._lock:
            if not self._stop.is_set():
                self._stream.write(text)
                self._stream.flush()

    def _leave(self) -> None:
        with self._lock:
            self._stream.write(LEAVE)
            self._stream.flush()

    def stop(self) -> None:
        """Join the painter, restore the screen, and replay held-back output.

        The terminal is restored even if the join is interrupted (Ctrl-C).
        """
        if self._thread is None:
            return
        self._stop.set()
        try:
            self._thread.join()
        finally:
            self._thread = None
            self._restore()

    def _restore(self) -> None:
        try:
            self._leave()
        finally:
            if sys.stdout is self._buffers[0]:
                sys.stdout = self._originals[0]
            if sys.stderr is self._buffers[1]:
                sys.stderr = self._originals[1]
            for buffer, original in zip(self._buffers, self._originals, strict=True):
                original.write(buffer.getvalue())
                original.flush()
