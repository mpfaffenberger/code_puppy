"""Small platform-detection helpers shared by UI entry points."""

from __future__ import annotations

import os
import shutil
import sys

# ``CODE PUPPY`` rendered in pyfiglet's ansi_shadow spans 79 columns
# (pinned by tests/test_platform_utils.py). Baked so banner selection
# stays import-light -- no pyfiglet needed just to pick a label.
_FULL_BANNER = "CODE PUPPY"
_FULL_BANNER_WIDTH = 79
_COMPACT_BANNER = "PUP"


def is_android() -> bool:
    """Return whether Code Puppy is running on Android or in Termux.

    Current Android Python builds expose an ``android`` platform name, while
    older Termux builds may report ``linux``. Environment markers cover that
    compatibility gap without making each UI entry point invent its own check.
    """
    if sys.platform.startswith("android"):
        return True

    return bool(
        os.environ.get("TERMUX_VERSION")
        or (os.environ.get("ANDROID_ROOT") and os.environ.get("ANDROID_DATA"))
    )


def startup_banner_text(columns: int | None = None) -> str:
    """Return the widest startup banner label the terminal can fit.

    Width-based rather than platform-based: a phone terminal in landscape
    earns the full banner, and a squeezed desktop split gets the compact
    one. ``columns`` defaults to the detected terminal width.
    """
    if columns is None:
        columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    return _FULL_BANNER if columns >= _FULL_BANNER_WIDTH else _COMPACT_BANNER
