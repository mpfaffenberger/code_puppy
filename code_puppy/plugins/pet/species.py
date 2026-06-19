"""The 19 good boys.

Ported (and dog-ified) from claude-buddy's species catalog. One shared puppy
template keeps things DRY -- the only thing that differs per breed is the ears
(line 0). Snoot, eyes, and jowls are universal because all dogs are perfect.

Each species exposes three idle animation frames (idle / tongue-out / blink),
each frame being a list of 5 equal-width-ish lines. ``{E}`` is the eye
placeholder, swapped for a real eye glyph at render time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# ── Shared face lines (the bits every dog has) ─────────────────────────────
_NOSE = "( \u1d25 )"  # ( ᴥ ) doge snoot
_EYES_OPEN = "( {E}  {E} )"
_EYES_BLINK = "( -  - )"
_MOUTH_IDLE = "\\__/"
_MOUTH_HAPPY = "\\_v_/"  # tongue out, mid-wag
_CHIN = "\\____/"


def _center(text: str, width: int = 12) -> str:
    """Center ``text`` inside ``width`` columns (cosmetic alignment only)."""
    if len(text) >= width:
        return text
    pad = width - len(text)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _make_dog(ears: str) -> List[List[str]]:
    """Build the 3 idle frames for a breed from its distinctive ear art."""
    e = _center(ears)
    nose = _center(_NOSE)
    chin = _center(_CHIN)
    eyes_open = _center(_EYES_OPEN.replace("{E}", "\x00")).replace("\x00", "{E}")
    eyes_blink = _center(_EYES_BLINK)
    mouth_idle = _center(_MOUTH_IDLE)
    mouth_happy = _center(_MOUTH_HAPPY)
    return [
        [e, eyes_open, nose, mouth_idle, chin],  # frame 0: idle
        [e, eyes_open, nose, mouth_happy, chin],  # frame 1: happy / tongue
        [e, eyes_blink, nose, mouth_idle, chin],  # frame 2: blink
    ]


# Per-breed ears. The whole personality of the silhouette lives here.
_EARS: Dict[str, str] = {
    "corgi": "/\\___/\\",
    "shiba": "/^\\_/^\\",
    "pug": "(_____)",
    "husky": "/\\_^_/\\",
    "poodle": "@@___@@",
    "dachshund": "(_)_(_)",
    "beagle": "(\\___/)",
    "labrador": "(\\_ _/)",
    "chihuahua": "/\\_ _/\\",
    "dalmatian": "(\\.o./)",
    "bulldog": "<_____>",
    "greatdane": "/|___|\\",
    "pomeranian": "{*___*}",
    "terrier": "/v___v\\",
    "boxer": "(|___|)",
    "collie": "/\\~/\\",
    "samoyed": "((___))",
    "doberman": "/!___!\\",
    "mutt": "(\\_o_/)",
}

# Rarity drives the border color + star count. Hand-tuned so the picker has a
# nice spread of common pups and a few legends to chase.
_RARITY: Dict[str, str] = {
    "mutt": "common",
    "beagle": "common",
    "labrador": "common",
    "pug": "common",
    "terrier": "common",
    "boxer": "uncommon",
    "dachshund": "uncommon",
    "chihuahua": "uncommon",
    "bulldog": "uncommon",
    "collie": "uncommon",
    "corgi": "rare",
    "husky": "rare",
    "dalmatian": "rare",
    "pomeranian": "rare",
    "greatdane": "epic",
    "doberman": "epic",
    "poodle": "epic",
    "shiba": "legendary",
    "samoyed": "legendary",
}

# A friendly default name per breed (used until the user renames their pet).
_DEFAULT_NAMES: Dict[str, str] = {
    "corgi": "Biscuit",
    "shiba": "Mochi",
    "pug": "Sir Snorts",
    "husky": "Blue",
    "poodle": "Coco",
    "dachshund": "Noodle",
    "beagle": "Scout",
    "labrador": "Buddy",
    "chihuahua": "Taco",
    "dalmatian": "Domino",
    "bulldog": "Tank",
    "greatdane": "Goliath",
    "pomeranian": "Puff",
    "terrier": "Pixel",
    "boxer": "Rocky",
    "collie": "Lassie",
    "samoyed": "Marshmallow",
    "doberman": "Zeus",
    "mutt": "Good Boy",
}


@dataclass(frozen=True)
class DogSpecies:
    """A single breed: art frames + flavour metadata."""

    name: str
    rarity: str
    default_name: str
    frames: List[List[str]] = field(default_factory=list)

    @property
    def stars(self) -> str:
        return _RARITY_STARS.get(self.rarity, "\u2605")

    @property
    def face(self) -> str:
        """Compact one-liner snoot for the picker preview."""
        return self.frames[0][1].replace("{E}", "\u00b7").strip()


_RARITY_STARS: Dict[str, str] = {
    "common": "\u2605",
    "uncommon": "\u2605\u2605",
    "rare": "\u2605\u2605\u2605",
    "epic": "\u2605\u2605\u2605\u2605",
    "legendary": "\u2605\u2605\u2605\u2605\u2605",
}

# 24-bit border colors keyed by rarity (matches claude-buddy's dark theme).
RARITY_RGB: Dict[str, tuple] = {
    "common": (153, 153, 153),
    "uncommon": (78, 186, 101),
    "rare": (177, 185, 249),
    "epic": (175, 135, 255),
    "legendary": (255, 193, 7),
}

# Build the catalog once. 19 dogs, deterministic order.
DOG_SPECIES: Dict[str, DogSpecies] = {
    name: DogSpecies(
        name=name,
        rarity=_RARITY[name],
        default_name=_DEFAULT_NAMES[name],
        frames=_make_dog(ears),
    )
    for name, ears in _EARS.items()
}


def list_species() -> List[str]:
    """Return breed names in catalog order."""
    return list(DOG_SPECIES.keys())


# ── Quips: the whole point of having a desktop dog ─────────────────────────
# ``{model}`` is interpolated with the active model name at render time, so the
# pet genuinely reflects "the model the user set."
QUIPS: List[str] = [
    "did someone say walkies? i mean... deploy?",
    "i sniffed a bug on line 42. it smells funny.",
    "tests passed! good human! *wags*",
    "that semicolon you forgot? mine now.",
    "refactor later. belly rubs now.",
    "i fetched the stack trace. who's a good boy?",
    "10/10 would compile again.",
    "your code is like a stick: i will chase it forever.",
    "merge conflict? i'll bury it in the yard.",
    "running on {model} and pure zoomies.",
    "i didn't chew the cables. probably.",
    "ship it! ship it! SHIP IT!",
    "is that... a TODO? *growls softly*",
    "you've been coding a while. drink some water, friend.",
    "i believe in you. also, treats.",
    "the linter and i are both judging you. lovingly.",
    "off-by-one again? classic. *flops over*",
    "{model} says hi. i say bork.",
    "git push and then we go to the park, ok?",
    "i guarded main from a force-push. you're welcome.",
    "nap detected. resuming supervision of your code.",
    "good news: it builds. bad news: i ate your mouse.",
    "every PR is a treat if you believe hard enough.",
    "*tilts head at your regex*",
]
