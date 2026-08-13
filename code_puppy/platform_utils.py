"""Small platform-detection helpers shared by UI entry points."""

from __future__ import annotations

import os
import sys


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


def startup_banner_text() -> str:
    """Return the platform-appropriate startup banner label."""
    return "PUP" if is_android() else "CODE PUPPY"
