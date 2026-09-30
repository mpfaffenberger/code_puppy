"""Locate the ripgrep executable -- the one place that knows how.

Code Puppy depends on the ``ripgrep`` wheel, which installs ``rg`` next to the
interpreter (``bin/`` on Unix, ``Scripts/`` on Windows) -- a directory that is
not on PATH unless the virtualenv is activated. Every rg consumer (grep,
list_files, @-file completion, plugins) must therefore look in both places;
keep that logic here so they cannot drift apart again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

# Bare ``rg`` also covers Windows-without-extension installs; ``rg.exe`` is the
# wheel's Windows binary.
_BUNDLED_NAMES = ("rg", "rg.exe")

# How long we're willing to wait on a health-check ``rg --version`` before
# treating the executable as broken. Real ripgrep answers in milliseconds;
# anything that hangs this long is not one we want to shell out to per call.
_HEALTH_CHECK_TIMEOUT_SECONDS = 2


def _executable_works(path: str) -> bool:
    """Best-effort check that ``path`` is an ``rg`` that actually runs.

    Environment managers such as pyenv can leave a broken shim on PATH --
    present, executable-looking, but failing or hanging when invoked. A
    plain ``shutil.which`` hit can't tell the difference; this can.
    """
    try:
        subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=_HEALTH_CHECK_TIMEOUT_SECONDS,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def find_ripgrep() -> str | None:
    """Path to ``rg``: PATH first, then the copy bundled beside the interpreter.

    A PATH entry that exists but doesn't actually run (a broken pyenv shim,
    for example) is treated as absent so a working bundled copy gets a
    chance -- we'd rather hand back a working ``rg`` from an unexpected
    place than a dead one from the expected place.
    """
    on_path = shutil.which("rg")
    if on_path and _executable_works(on_path):
        return on_path

    interpreter_dir = os.path.dirname(sys.executable)
    for name in _BUNDLED_NAMES:
        candidate = os.path.join(interpreter_dir, name)
        if os.path.exists(candidate):
            return candidate

    # Nothing bundled either. A broken PATH hit is still the best answer we
    # have -- callers already handle rg invocation failures downstream.
    return on_path
