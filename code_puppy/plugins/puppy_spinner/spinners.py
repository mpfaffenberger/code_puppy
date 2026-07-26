"""Spinner catalogue + persistence for the ``puppy_spinner`` plugin.

Built-in spinners live here. Users add their own by dropping a
``spinners.json`` next to ``puppy.cfg`` (see ``USER_SPINNERS_FILE``)::

    {
      "my-spinner": {
        "frames": ["( .    ) ", "(  .   ) ", "(   .  ) "],
        "interval": 0.1,
        "description": "a very minimalist puppy"
      }
    }

User spinners win on name collision (so you *can* redefine "puppy",
you monster). An entry that names a builtin and omits ``frames`` is a
*tweak*: it inherits the builtin's frames and just overrides the
interval (and/or description) -- the cheap way to re-speed a builtin
without copying its art::

    {
      "zoomies": {"interval": 0.1}
    }

The active choice persists under the ``spinner_style`` key in
``puppy.cfg`` and is cached in-process; ``invalidate_cache()`` forces a
re-read after external edits. Speed has one rule: a spinner runs at its
spinners.json value when present, else the builtin default. Dialing a
speed in the picker (or ``/spinner <name> <secs>``) simply *saves* that
value into spinners.json -- user land keeps its own numbers, no
shadow-override layer to reason about.

Everything here fails gracefully: a broken JSON file or a vanished
spinner name always degrades to the classic kennel-bounce puppy.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from rich.cells import cell_len

from code_puppy.config import CONFIG_DIR, get_value, set_value

from .builtin_frames import EXTRA_SPECS

logger = logging.getLogger(__name__)

CONFIG_KEY = "spinner_style"
DEFAULT_SPINNER = "puppy"
USER_SPINNERS_FILE = os.path.join(CONFIG_DIR, "spinners.json")

MIN_INTERVAL = 0.02  # 50 fps -- any faster is just terminal abuse
MAX_INTERVAL = 1.0
#: One speed to rule them all: every builtin ships at this, and it's the
#: fallback when spinners.json omits (or fumbles) an interval.
_DEFAULT_INTERVAL = 0.2
#: ...except the classic. The kennel bounce was tuned for a quicker trot
#: (0.05s originally) and looks sluggish at the pack default.
_PUPPY_INTERVAL = 0.06
_MAX_FRAME_LEN = 40  # the status-prefix slot is prime real estate

# Escape-spelled glyphs (repo emoji filter).
PUPPY = "\U0001f436"  # dog face
_DOG = "\U0001f415"  # dog (side view, runs left)
_DASH = "\U0001f4a8"  # dust cloud
_PAW = "\U0001f43e"  # paw prints
_BONE = "\U0001f9b4"  # bone


@dataclass(frozen=True)
class Spinner:
    """One spinner: a frame cycle, a tick interval, and provenance."""

    name: str
    frames: Tuple[str, ...]
    interval: float
    description: str = ""
    source: str = "builtin"  # "builtin" | "user"


def _pad(frames) -> Tuple[str, ...]:
    """Right-pad every frame to a common *cell* width so text after the
    spinner never jumps.

    ``len()`` is a dirty liar for emoji: a paw print is one code point
    but TWO terminal cells. Padding by ``rich.cells.cell_len`` keeps the
    rendered width constant even when frames mix emoji and ASCII.
    """
    frames = tuple(frames)  # materialize: generators only pour out once
    width = max(cell_len(f) for f in frames)
    return tuple(f + " " * (width - cell_len(f)) for f in frames)


def _kennel_bounce(critter: str) -> Tuple[str, ...]:
    """The classic 5-cell kennel bounce: positions 0..4 and back again."""
    return tuple(
        f"({' ' * i}{critter}{' ' * (4 - i)}) " for i in (0, 1, 2, 3, 4, 3, 2, 1)
    )


# name -> (frames, interval, description)
_BUILTIN_SPECS = {
    "puppy": (
        _kennel_bounce(PUPPY),
        _PUPPY_INTERVAL,
        "the classic kennel bounce (default)",
    ),
    "bone": (
        _kennel_bounce(_BONE),
        _DEFAULT_INTERVAL,
        "same kennel, chewier occupant",
    ),
    "zoomies": (
        tuple(f"{' ' * i}{_DOG}{_DASH}{' ' * (5 - i)}" for i in (5, 4, 3, 2, 1, 0)),
        _DEFAULT_INTERVAL,
        "full-speed dog, dust trailing",
    ),
    "paws": (
        tuple(_PAW * n for n in (1, 2, 3, 4)),  # _pad cell-aligns the trail
        _DEFAULT_INTERVAL,
        "a trail of paw prints",
    ),
    "dots": (
        tuple(
            chr(cp)
            for cp in (
                0x280B,
                0x2819,
                0x2839,
                0x2838,
                0x283C,
                0x2834,
                0x2826,
                0x2827,
                0x2807,
                0x280F,
            )
        ),
        _DEFAULT_INTERVAL,
        "classic braille dots",
    ),
}

# The cli-spinners-style pack (frames + blurbs live in ``builtin_frames``,
# a generated data-only module). Same default speed as everything else.
_BUILTIN_SPECS.update(
    {
        name: (frames, _DEFAULT_INTERVAL, desc)
        for name, (frames, desc) in EXTRA_SPECS.items()
    }
)

BUILTIN_SPINNERS: Dict[str, Spinner] = {
    name: Spinner(name=name, frames=_pad(frames), interval=interval, description=desc)
    for name, (frames, interval, desc) in _BUILTIN_SPECS.items()
}


# --- User spinners (external JSON file) --------------------------------------
def _parse_interval(name: str, spec: dict, default: float) -> float:
    """Validate + clamp a spec's 'interval', falling back to *default*."""
    interval = spec.get("interval", default)
    # bool check first: JSON `true` is an int subclass, and float(True)
    # is a surprise 1-second spinner. No booleans, thanks.
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or interval <= 0
    ):
        logger.warning(
            "spinners.json: %r has a bad 'interval'; using %s", name, default
        )
        interval = default
    return clamp_interval(float(interval))


def _parse_builtin_tweak(name: str, spec: dict) -> Optional[Spinner]:
    """A frameless entry naming a builtin: inherit its frames, override
    the rest. The cheap way to re-speed a builtin without copying art.
    """
    if "interval" not in spec and "description" not in spec:
        logger.warning(
            "spinners.json: %r tweaks builtin %r but overrides nothing "
            "(add 'interval' or 'description'); skipping",
            name,
            name,
        )
        return None
    base = BUILTIN_SPINNERS[name]
    description = spec.get("description", base.description)
    if not isinstance(description, str):
        description = base.description
    return Spinner(
        name=name,
        frames=base.frames,
        interval=_parse_interval(name, spec, base.interval),
        description=description,
        source="builtin+user",
    )


def _parse_user_spinner(name: str, spec: object) -> Optional[Spinner]:
    """Validate one user entry. Returns None (and logs) on any problem."""
    if not isinstance(name, str) or not name.strip():
        logger.warning("spinners.json: skipping entry with a blank name")
        return None
    if not isinstance(spec, dict):
        logger.warning("spinners.json: %r is not an object; skipping", name)
        return None

    raw_frames = spec.get("frames")
    if raw_frames is None and name in BUILTIN_SPINNERS:
        return _parse_builtin_tweak(name, spec)
    if (
        not isinstance(raw_frames, list)
        or not raw_frames
        or not all(isinstance(f, str) and f for f in raw_frames)
    ):
        logger.warning(
            "spinners.json: %r needs a non-empty 'frames' list of strings; skipping",
            name,
        )
        return None
    frames = _pad(f[:_MAX_FRAME_LEN] for f in raw_frames)

    description = spec.get("description", "")
    if not isinstance(description, str):
        description = ""

    return Spinner(
        name=name.strip(),
        frames=frames,
        interval=_parse_interval(name, spec, _DEFAULT_INTERVAL),
        description=description,
        source="user",
    )


def load_user_spinners() -> Dict[str, Spinner]:
    """Read + validate the user spinner file. Missing/broken file = {}."""
    if not os.path.isfile(USER_SPINNERS_FILE):
        return {}
    try:
        with open(USER_SPINNERS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", USER_SPINNERS_FILE, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s must be a JSON object; ignoring", USER_SPINNERS_FILE)
        return {}

    spinners: Dict[str, Spinner] = {}
    for name, spec in data.items():
        spinner = _parse_user_spinner(name, spec)
        if spinner is not None:
            spinners[spinner.name] = spinner
    return spinners


def get_catalogue() -> Dict[str, Spinner]:
    """Builtin + user spinners, user winning on name collision.

    Sorted alphabetically (case-insensitive) -- every consumer iterates
    this, so ordering lives here once.
    """
    catalogue = dict(BUILTIN_SPINNERS)
    for name, spinner in load_user_spinners().items():
        if name in catalogue:
            logger.info("user spinner %r overrides the builtin one", name)
        catalogue[name] = spinner
    return dict(sorted(catalogue.items(), key=lambda kv: kv[0].lower()))


# --- Saving a speed back into user land ---------------------------------------
def clamp_interval(value: float) -> float:
    """Clamp *value* into the sane range and round to whole centiseconds."""
    return round(min(max(value, MIN_INTERVAL), MAX_INTERVAL), 2)


def save_interval_tweak(name: str, interval: float) -> bool:
    """Persist *interval* for *name* into spinners.json (creating the
    file if needed).

    In user land the file *is* the truth: a dialed speed is just a saved
    value, not a separate override layer. Existing entry keys (frames,
    description) are preserved; only ``interval`` changes.

    Returns False (and logs) when the file can't be read or written --
    we never overwrite a file we couldn't parse.
    """
    interval = clamp_interval(interval)
    data: dict = {}
    if os.path.isfile(USER_SPINNERS_FILE):
        try:
            with open(USER_SPINNERS_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Not saving speed: %s is unreadable (%s)", USER_SPINNERS_FILE, exc
            )
            return False
        if not isinstance(data, dict):
            logger.warning(
                "Not saving speed: %s is not a JSON object", USER_SPINNERS_FILE
            )
            return False
    entry = data.get(name)
    if not isinstance(entry, dict):
        entry = {}
    entry["interval"] = interval
    data[name] = entry
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(USER_SPINNERS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        logger.warning("Could not save speed to %s: %s", USER_SPINNERS_FILE, exc)
        return False
    return True


# --- Active spinner (persisted + cached) -------------------------------------
# The cache exists so the tick loop isn't parsing config + JSON dozens of
# times a second. It self-invalidates when spinners.json's mtime moves,
# so external edits are picked up on the next animation frame -- no
# reload command, no restart.
_active_cache: Optional[Spinner] = None
_active_cache_stamp: Optional[float] = None


def user_file_stamp() -> Optional[float]:
    """spinners.json's mtime, or None when the file doesn't exist.

    Public because the picker watches it too: both the tick loop and the
    open TUI use the same signal to notice external edits.
    """
    try:
        return os.path.getmtime(USER_SPINNERS_FILE)
    except OSError:
        return None


def _load_active() -> Spinner:
    try:
        name = get_value(CONFIG_KEY)
    except Exception:  # config layer must never break the spinner
        name = None
    name = (name or DEFAULT_SPINNER).strip()
    catalogue = get_catalogue()
    if name not in catalogue:
        if name != DEFAULT_SPINNER:
            logger.warning(
                "Configured spinner %r not found; falling back to %r",
                name,
                DEFAULT_SPINNER,
            )
        spinner = BUILTIN_SPINNERS[DEFAULT_SPINNER]
    else:
        spinner = catalogue[name]
    return spinner


def get_active_spinner() -> Spinner:
    """The currently selected spinner.

    Cached, but re-read whenever spinners.json changes on disk (an
    os.stat per call -- cheap enough for the ~5 Hz tick loop).
    """
    global _active_cache, _active_cache_stamp
    stamp = user_file_stamp()
    if _active_cache is None or stamp != _active_cache_stamp:
        _active_cache = _load_active()
        _active_cache_stamp = stamp
    return _active_cache


def set_active(name: str, interval: Optional[float] = None) -> Spinner:
    """Persist + activate *name*, optionally saving a custom speed.

    A given *interval* is written straight into spinners.json as that
    spinner's speed -- the file is the single source of truth, so the
    value sticks until the user changes it again (there is no separate
    override to clear). Raises KeyError for unknown spinners.
    """
    global _active_cache, _active_cache_stamp
    catalogue = get_catalogue()
    if name not in catalogue:
        raise KeyError(name)
    set_value(CONFIG_KEY, name)
    spinner = catalogue[name]
    if interval is not None:
        interval = clamp_interval(interval)
        if save_interval_tweak(name, interval):
            spinner = get_catalogue()[name]  # re-read: the file is the truth
        else:
            # Couldn't write (broken/readonly file): honor the speed for
            # this session rather than silently dropping the request.
            spinner = replace(spinner, interval=interval)
    _active_cache = spinner
    _active_cache_stamp = user_file_stamp()
    return _active_cache


def invalidate_cache() -> None:
    """Drop the cache so the next read re-checks config + spinners.json.

    Rarely needed -- file edits are caught automatically via mtime; this
    covers out-of-band ``puppy.cfg`` changes (and test isolation).
    """
    global _active_cache, _active_cache_stamp
    _active_cache = None
    _active_cache_stamp = None


# --- Starter template for /spinner init --------------------------------------
_TEMPLATE = {
    "sniffer": {
        "frames": ["( .    ) ", "(  .   ) ", "(   .  ) ", "(    . ) "],
        "interval": 0.1,
        "description": "a very minimalist puppy",
    },
    # A frameless entry naming a builtin just re-speeds it (this example
    # matches the builtin default, so it's a safe demo -- edit away).
    "zoomies": {"interval": 0.2},
}


def write_template() -> bool:
    """Write a starter spinners.json. Returns False if one already exists."""
    if os.path.isfile(USER_SPINNERS_FILE):
        return False
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(USER_SPINNERS_FILE, "w", encoding="utf-8") as fh:
        json.dump(_TEMPLATE, fh, indent=2)
        fh.write("\n")
    return True
