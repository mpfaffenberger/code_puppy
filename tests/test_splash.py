"""The startup splash: stdlib-only, painted in theme colours, never ``PUP``."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

from code_puppy import colors
from code_puppy.splash import LEAVE, SCENES, Splash
from code_puppy.splash import __main__ as preview
from code_puppy.splash.canvas import Canvas
from code_puppy.splash.scenes import CAPTION, caption

SIZES = [(45, 22), (80, 24), (200, 60), (10, 4), (0, 0)]
TICKS = range(0, 400, 7)


@pytest.mark.parametrize("name", SCENES)
@pytest.mark.parametrize(("width", "height"), SIZES)
def test_every_frame_paints_only_theme_colours(
    name: str, width: int, height: int
) -> None:
    for tick in TICKS:
        canvas = Canvas(width, height)
        SCENES[name](canvas, tick)
        caption(canvas, tick)
        assert canvas.colours() <= {s.colour for s in colors.SHADES.values()}
        # Raises for a colour without a 16-colour fallback.
        canvas.render(deep=False)


@pytest.mark.parametrize("name", SCENES)
def test_scenes_never_freeze(name: str) -> None:
    def frame(tick: int) -> str:
        canvas = Canvas(80, 24)
        SCENES[name](canvas, tick)
        return canvas.render(deep=True)

    stills = [tick for tick in range(400) if frame(tick) == frame(tick + 2)]
    assert len(stills) < 40, stills


def _plain_rows(frame: str) -> list[str]:
    """A rendered frame's rows, escapes removed."""
    return re.sub(r"\x1b\[[0-9;]*m", "", frame).split("\x1b[")[1:]


@pytest.mark.parametrize("name", SCENES)
def test_the_caption_names_code_puppy_and_nothing_says_pup(name: str) -> None:
    for tick in TICKS:
        rows = _plain_rows(
            Splash(enabled=False, scene=SCENES[name]).frame(tick, 80, 24)
        )
        assert rows[22].split("H", 1)[1].strip() == CAPTION
        assert "PUP" not in "".join(rows)


def test_frames_fill_the_screen_but_never_the_last_column() -> None:
    rows = _plain_rows(Splash(enabled=False).frame(10, 80, 24))
    assert [row.split("H", 1)[0] for row in rows] == [f"{y};1" for y in range(1, 25)]
    assert {len(row.split("H", 1)[1]) for row in rows} == {79}


def test_ships_three_scenes() -> None:
    assert list(SCENES) == ["paw-trail", "kibble-rain", "sniff"]


def test_each_launch_picks_a_scene_at_random() -> None:
    picked = {Splash(enabled=False)._scene for _ in range(200)}
    assert picked == set(SCENES.values())


class FakeTerminal(io.StringIO):
    """A stream that says it is a terminal and keeps everything written to it."""

    def __init__(self, *, tty: bool = True, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding

    def isatty(self) -> bool:
        return self._tty


def attach(
    monkeypatch: pytest.MonkeyPatch, *, tty: bool = True, encoding: str = "utf-8"
) -> tuple[FakeTerminal, FakeTerminal]:
    """Put fake terminals on stdout and stderr.

    Called from the test body: pytest's own capture replaces ``sys.stdout``
    again between fixture setup and the test call.
    """
    out, err = FakeTerminal(tty=tty, encoding=encoding), FakeTerminal()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A colour-capable 80x24 POSIX terminal; ``attach`` supplies its streams."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shutil, "get_terminal_size", lambda: os.terminal_size((80, 24)))
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.mark.usefixtures("terminal")
def test_start_holds_output_back_and_stop_replays_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out, err = attach(monkeypatch)
    splash = Splash(scene=SCENES["sniff"])
    splash.start()
    assert sys.stdout is not out and sys.stderr is not err
    print("hello")
    print("oops", file=sys.stderr)
    deadline = time.monotonic() + 5
    while CAPTION[0] not in out.getvalue() and time.monotonic() < deadline:
        time.sleep(0.01)
    splash.stop()

    assert sys.stdout is out and sys.stderr is err
    painted, _, replayed = out.getvalue().partition("\x1b[?1049l\x1b[?25h")
    assert painted.startswith("\x1b[?1049h\x1b[?25l")
    assert "".join(_plain_rows(painted)).count("c o d e") >= 1
    assert replayed == "hello\n"
    assert err.getvalue() == "oops\n"
    splash.stop()  # A second stop is harmless.


def broken_scene(canvas: Canvas, tick: int) -> None:
    raise RuntimeError("a bug in a scene")


@pytest.mark.usefixtures("terminal")
def test_a_failing_frame_hands_the_screen_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No blank, cursorless screen while startup continues, and nothing lost."""
    out, _ = attach(monkeypatch)
    splash = Splash(scene=broken_scene)
    splash.start()
    print("hello")
    assert splash._thread is not None
    splash._thread.join(timeout=5)

    assert not splash._thread.is_alive()
    assert out.getvalue() == "\x1b[?1049h\x1b[?25l" + LEAVE
    splash.stop()
    assert sys.stdout is out
    assert out.getvalue().endswith(LEAVE + "hello\n")


@pytest.mark.parametrize(
    ("change", "enabled"),
    [
        ({}, True),
        ({"enabled": False}, False),
        ({"tty": False}, False),
        ({"NO_COLOR": "1"}, False),
        ({"TERM": "dumb"}, False),
        ({"size": (45, 24)}, False),
        ({"size": (80, 21)}, False),
        ({"size": (46, 22)}, True),
        ({"platform": "win32"}, False),
        ({"platform": "linux"}, True),
        # `PYTHONIOENCODING=ascii`, or a C locale: the glyphs cannot be written.
        ({"encoding": "ascii"}, False),
        ({"encoding": "latin-1"}, False),
        ({"encoding": "no-such-codec"}, False),
        ({"encoding": "UTF8"}, True),
    ],
)
@pytest.mark.usefixtures("terminal")
def test_the_splash_only_runs_on_a_capable_terminal(
    monkeypatch: pytest.MonkeyPatch, change: dict[str, object], enabled: bool
) -> None:
    attach(
        monkeypatch,
        tty=bool(change.get("tty", True)),
        encoding=str(change.get("encoding", "utf-8")),
    )
    for name in ("NO_COLOR", "TERM"):
        if name in change:
            monkeypatch.setenv(name, str(change[name]))
    if "size" in change:
        size = os.terminal_size(change["size"])  # type: ignore[arg-type]
        monkeypatch.setattr(shutil, "get_terminal_size", lambda: size)
    if "platform" in change:
        monkeypatch.setattr(sys, "platform", change["platform"])

    splash = Splash(enabled=bool(change.get("enabled", True)))
    assert splash._enabled is enabled


class RecordingSplash:
    """Stands in for ``Splash`` in the preview command."""

    made: list[RecordingSplash] = []

    def __init__(self, *, scene: object) -> None:
        self.scene = scene
        self.calls: list[str] = []
        RecordingSplash.made.append(self)

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")


@pytest.mark.parametrize(
    ("argv", "played"),
    [(["paw-trail"], ["paw-trail"]), ([], list(SCENES))],
)
def test_the_preview_plays_the_scenes_asked_for(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], played: list[str]
) -> None:
    monkeypatch.setattr(preview, "Splash", RecordingSplash)
    monkeypatch.setattr(RecordingSplash, "made", [])

    preview.main([*argv, "--seconds", "0"])

    assert [splash.scene for splash in RecordingSplash.made] == [
        SCENES[name] for name in played
    ]
    assert all(splash.calls == ["start", "stop"] for splash in RecordingSplash.made)


def test_the_preview_refuses_an_unknown_scene(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        preview.main(["nope"])
    assert exit_info.value.code == 2
    assert "unknown scene nope" in capsys.readouterr().err


def test_importing_the_splash_loads_no_runtime() -> None:
    script = (
        "import sys, code_puppy.splash; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in "
        "('pydantic_ai_pax', 'pydantic_ai', 'rich', 'pydantic')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert result.stdout.strip() == "[]"
