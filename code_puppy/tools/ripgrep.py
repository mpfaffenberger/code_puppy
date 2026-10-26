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
import sys

# Bare ``rg`` also covers Windows-without-extension installs; ``rg.exe`` is the
# wheel's Windows binary.
_BUNDLED_NAMES = ("rg", "rg.exe")


def find_ripgrep() -> str | None:
    """Path to ``rg``: PATH first, then the copy bundled beside the interpreter."""
    on_path = shutil.which("rg")
    if on_path:
        return on_path
    interpreter_dir = os.path.dirname(sys.executable)
    for name in _BUNDLED_NAMES:
        candidate = os.path.join(interpreter_dir, name)
        if os.path.exists(candidate):
            return candidate
    return None
