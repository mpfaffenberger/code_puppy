"""The splash's scenes. Each paints frame ``tick`` onto a canvas.

A scene is a pure function of the canvas size and the frame number, so any
frame can be drawn, and tested, on its own. Scenes draw on the stage: every
row but the bottom :data:`CAPTION_ROWS`, which hold the caption.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from functools import lru_cache

from code_puppy import _art
from code_puppy.colors import (
    BLUE,
    CHARCOAL,
    CYAN,
    GRAPHITE,
    GREEN,
    GREY,
    ORCHID,
    ROLES,
    YELLOW,
)
from code_puppy.splash.canvas import Canvas

Scene = Callable[[Canvas, int], None]

RAMP: tuple[str, ...] = ROLES["BANNER"]
"""The banner's blue → cyan → green, so the splash hands over to it seamlessly."""
FADE = (*RAMP, GREY, GRAPHITE, CHARCOAL)
"""Fresh to faded: the ramp, then down into the background."""
GLINT = (YELLOW, YELLOW, ORCHID, GRAPHITE, CHARCOAL)

CAPTION = "c o d e   p u p p y"
CAPTION_ROWS = 3
RAIN = "{}[]()<>=;:+*/01"


def stage_height(canvas: Canvas) -> int:
    """Rows a scene may draw on."""
    return max(0, canvas.height - CAPTION_ROWS)


def fade(age: float, step: float, colours: tuple[str, ...] = FADE) -> str | None:
    """The colour of something ``age`` frames old, ``step`` frames per shade; ``None`` once gone."""
    index = math.floor(age / step)
    return colours[index] if 0 <= index < len(colours) else None


def caption(canvas: Canvas, tick: int) -> None:
    """The name in the ramp's colours, with a golden glint sweeping through it."""
    left = (canvas.width - len(CAPTION)) // 2
    for index, glyph in enumerate(CAPTION):
        glint = (index - tick // 2) % 30 < 2
        colour = YELLOW if glint else RAMP[index * len(RAMP) // len(CAPTION)]
        canvas.put(left + index, canvas.height - 2, glyph, colour)


def paw_trail(canvas: Canvas, tick: int) -> None:
    """Paw prints stamp across the screen, flash gold, then fade down the ramp."""
    stride, beat, life = 7, 4, 7
    steps = max(1, (canvas.width - len(_art.PRINT[0])) // stride + 1)
    now = tick % (steps * beat + 2 + life * len(FADE))
    middle = stage_height(canvas) // 2 - 2
    for step in range(steps):
        age = now - step * beat
        if age < 0:
            break
        colour = YELLOW if age < 2 else fade(age - 2, life)
        if colour is None:
            continue
        sway = round(2 * math.sin(step / 2.5))
        foot = -2 if step % 2 else 2
        canvas.sprite(step * stride, middle + sway + foot, _art.PRINT, colour)


@lru_cache(maxsize=4)
def _paw_cells(width: int, stage: int) -> dict[tuple[int, int], int]:
    """The paw raster scaled to fit the stage, centred: cell → shade tier."""
    rows = max(0, min(len(_art.PAW), stage - 1))
    cols = round(len(_art.PAW[0]) * rows / len(_art.PAW))
    left, top = (width - cols) // 2, (stage - rows) // 2
    cells = {}
    for y in range(rows):
        source = _art.PAW[y * len(_art.PAW) // rows]
        for x in range(cols):
            if tier := int(source[x * len(source) // cols]):
                cells[left + x, top + y] = tier
    return cells


@lru_cache(maxsize=4)
def _drops(width: int, stage: int) -> tuple[tuple[float, float, int, int], ...]:
    """Each column's raindrop: speed, delay, trail length and cycle, fixed per column."""
    drops = []
    for column in range(width):
        dice = random.Random(column)
        length = dice.randint(4, 10)
        drops.append(
            (
                dice.uniform(0.6, 1.4),
                dice.uniform(0, stage),
                length,
                stage + length + dice.randint(0, max(1, stage)),
            )
        )
    return tuple(drops)


def kibble_rain(canvas: Canvas, tick: int) -> None:
    """Code rain falls; wherever it has fallen, a big paw is left behind."""
    stage = stage_height(canvas)
    paw = _paw_cells(canvas.width, stage)
    trail = (GREEN, GREEN, GREY, GRAPHITE, CHARCOAL)
    for column, (speed, delay, length, cycle) in enumerate(_drops(canvas.width, stage)):
        fallen = tick * speed - delay
        for y in range(min(stage, math.floor(fallen) + 1)):
            tier = paw.get((column, y))
            if tier:
                glint = (column + 2 * y - tick) % 70 < 4
                colour = YELLOW if glint else (CYAN, CYAN, BLUE)[tier - 1]
                canvas.put(column, y, " ░▒█"[tier], colour)
        if fallen < 0:
            continue
        head = math.floor(fallen) % cycle
        for back in range(length):
            y = head - back
            colour = fade(back, length / len(trail), trail)
            if 0 <= y < stage and (column, y) not in paw and colour is not None:
                glyph = RAIN[(column * 31 + y * 17 + tick // 3) % len(RAIN)]
                canvas.put(column, y, glyph, colour)


@lru_cache(maxsize=4)
def _contacts(width: int, stage: int) -> tuple[tuple[int, int], ...]:
    """Where the treats are hidden for ``sniff`` to find."""
    dice = random.Random(7)
    return tuple(
        (dice.randrange(max(1, width)), dice.randrange(max(1, stage))) for _ in range(7)
    )


def sniff(canvas: Canvas, tick: int) -> None:
    """A nose sends out sonar rings that fade with distance and light up hidden treats."""
    stage = stage_height(canvas)
    middle_x, middle_y = canvas.width // 2, stage // 2
    speed, spacing = 0.4, 7.0
    front = tick * speed
    reach = max(1.0, math.hypot(middle_x / 2, middle_y))

    def distance(x: int, y: int) -> float:
        # Cells are about twice as tall as they are wide.
        return math.hypot((x - middle_x) / 2, y - middle_y)

    for y in range(stage):
        for x in range(canvas.width):
            away = distance(x, y)
            lag = (front - away) % spacing
            if away < 3 or away > front or lag >= 1.2:
                continue
            glyph = "○" if lag < 0.4 else "∘" if lag < 0.8 else "·"
            colour = FADE[min(len(FADE) - 1, int(away / reach * len(FADE)))]
            canvas.put(x, y, glyph, colour)
    for x, y in _contacts(canvas.width, stage):
        away = distance(x, y)
        if away >= 3 and front >= away:
            colour = fade(((front - away) % spacing) / speed, 3, GLINT)
            if colour is not None:
                canvas.put(x, y, "◆", colour)
    pulse = CYAN if front % spacing < 1.5 else BLUE
    canvas.sprite(middle_x - 2, middle_y - 1, _art.PRINT, pulse)


SCENES: dict[str, Scene] = {
    "paw-trail": paw_trail,
    "kibble-rain": kibble_rain,
    "sniff": sniff,
}
"""Every scene, by name. Each launch plays one at random."""
