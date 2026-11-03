"""Pre-import startup hooks for in-tree plugins.

``code_puppy/main.py`` calls :func:`run_early_startup` while the splash is on
screen and BEFORE the heavy ``cli_runner`` import (pydantic-ai, prompt_toolkit,
rich, ...). It exists for setup that has to happen before those imports, such
as sanitising proxy or certificate environment variables that would otherwise
break them.

A plugin opts in by shipping ``code_puppy/plugins/<name>/early_startup.py``
with a zero-argument ``run()``. The rules:

* Keep the hook, and the plugin's package ``__init__``, light. Everything here
  runs before the app is ready, so stdlib-only is the goal.
* Only in-tree plugin directories are scanned. User and project plugins are
  untrusted code and go through the trust-gated loader later, never from here.
* The plugin enable/disable list is not consulted (configuration is not loaded
  yet), so a hook that needs a kill switch should read its own environment
  variable.
* A hook that raises is logged at debug level and skipped; startup continues.
  ``KeyboardInterrupt`` and ``SystemExit`` still propagate.

This module is stdlib-only by design, like ``code_puppy.splash`` -- do not
import anything else from ``code_puppy`` here.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

HOOK_FILE = "early_startup.py"
_PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"
_PLUGINS_PACKAGE = "code_puppy.plugins"


def discover() -> list[str]:
    """Names of in-tree plugins that ship an ``early_startup.py``, sorted."""
    try:
        with os.scandir(_PLUGINS_DIR) as entries:
            return sorted(
                entry.name
                for entry in entries
                if not entry.name.startswith(("_", "."))
                and entry.is_dir()
                and os.path.isfile(os.path.join(entry.path, HOOK_FILE))
            )
    except OSError:
        return []


def run_early_startup() -> None:
    """Run every discovered plugin's ``run()``, in name order. Never raises."""
    for name in discover():
        try:
            module = importlib.import_module(f"{_PLUGINS_PACKAGE}.{name}.early_startup")
            module.run()
        except Exception:
            logger.debug("early startup hook of plugin %r failed", name, exc_info=True)
