"""The startup splash: stdlib-only, painted in theme colours, never ``PUP``."""

from __future__ import annotations

import io
import re
import subprocess
import sys

import pytest

from code_puppy import colors
from code_puppy.splash import SCENES, Splash
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


def test_disabled_off_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    splash = Splash()
    splash.start()
    assert sys.stdout is not None and splash._thread is None
    splash.stop()


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
