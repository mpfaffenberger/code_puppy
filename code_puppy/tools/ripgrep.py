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

# Remember only the most recent failed probe. The stat fingerprint invalidates
# the entry when a shim is replaced or repaired at the same path, while keeping
# repeated calls from paying the full timeout for one unchanged broken shim.
_failed_probe: tuple[str, tuple[int, int, int, int, int, int] | None] | None = None


def _executable_fingerprint(path: str) -> tuple[int, int, int, int, int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (
        stat.st_dev,
        stat.st_ino,
        stat.st_mode,
        stat.st_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
    )


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
    global _failed_probe

    on_path = shutil.which("rg")
    if on_path:
        probe = (on_path, _executable_fingerprint(on_path))
        if probe != _failed_probe:
            if _executable_works(on_path):
                _failed_probe = None
                return on_path
            _failed_probe = probe

    interpreter_dir = os.path.dirname(sys.executable)
    for name in _BUNDLED_NAMES:
        candidate = os.path.join(interpreter_dir, name)
        if os.path.exists(candidate):
            return candidate

    # Nothing bundled either. A broken PATH hit is still the best answer we
    # have -- callers already handle rg invocation failures downstream.
    return on_path
