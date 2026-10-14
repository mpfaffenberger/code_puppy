"""CLI runner for Code Puppy: compatibility facade and process entrypoint.

The actual implementation lives in ``cli_entry.py`` (startup/main dispatch),
``interactive_runner.py`` (REPL loop), ``interactive_support.py`` (prompt
UI/signal/shutdown seams), and ``prompt_runner.py`` (prompt execution +
headless dispatch). This module re-exports their public entrypoints for
backwards compatibility and owns ``main_entry()`` -- the installed console
script's actual entrypoint (see ``code_puppy/main.py``).

Export policy: ``__all__`` lists the public entrypoints (``main``,
``interactive_mode``, ``execute_single_prompt``, ``run_prompt_with_attachments``,
``apply_quick_resume``, ``main_entry``) plus four selected legacy private
aliases that existing tests/callers still import or patch directly
(``_HEADLESS_AUTONOMY_PROMPT``, ``_save_autosave_snapshot``,
``_use_persistent_prompt``, ``_write_usage_file``). It is not an exhaustive
list of this module's retained attributes: ``plugins``,
``reset_unix_terminal``, ``apply_all_patches``, and ``_force_utf8_stdio``
remain importable/patchable here too, just outside ``__all__``. Other
formerly-private helpers moved to their owning module without any facade
alias because nothing in this repo or the official plugin bundle
references them.
"""

# Apply pydantic-ai patches BEFORE any pydantic-ai imports
from code_puppy.pydantic_patches import apply_all_patches

apply_all_patches()

import asyncio
import sys
import traceback

from code_puppy import plugins
from code_puppy.cli_entry import apply_quick_resume, main
from code_puppy.interactive_runner import interactive_mode
from code_puppy.interactive_support import (
    _save_autosave_snapshot,
    _use_persistent_prompt,
)
from code_puppy.malloc_noise_guard import install_malloc_noise_guard
from code_puppy.prompt_runner import (
    _HEADLESS_AUTONOMY_PROMPT,
    _write_usage_file,
    execute_single_prompt,
    run_prompt_with_attachments,
)
from code_puppy.terminal_utils import reset_unix_terminal

plugins.load_plugin_callbacks()

__all__ = [
    "_HEADLESS_AUTONOMY_PROMPT",
    "_save_autosave_snapshot",
    "_use_persistent_prompt",
    "_write_usage_file",
    "apply_quick_resume",
    "execute_single_prompt",
    "interactive_mode",
    "main",
    "main_entry",
    "run_prompt_with_attachments",
]


def _force_utf8_stdio():
    """Ensure stdout/stderr can encode non-ASCII output (e.g. emoji prompts).

    On Windows the console often defaults to a legacy code page (e.g. cp1252),
    so writing UTF-8 characters crashes the very first run. Reconfigure the
    streams to UTF-8 where the runtime supports it; no-op otherwise.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main_entry():
    """Entry point for the installed CLI tool."""
    _force_utf8_stdio()
    # Before anything spawns: fork children inherit fd 2 (see the module).
    install_malloc_noise_guard()
    try:
        # Capture main()'s return so plugins / normal paths set the exit status
        # (None -> 0 or an int exit code).
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        # Note: Using sys.stderr for crash output - messaging system may not be available
        sys.stderr.write(traceback.format_exc())
        return 0
    finally:
        # Reset terminal on Unix-like systems (not Windows)
        reset_unix_terminal()
    # Guard None -> 0 and propagate to the process exit status.
    sys.exit(rc if rc is not None else 0)
