"""Main entry point for Code Puppy CLI.

This module re-exports the main_entry function from cli_runner for backwards
compatibility. All the actual logic lives in cli_runner.py.

The boot-trace root opens first, then the neon splash starts BEFORE the
cli_runner import below: that import pulls in pydantic-ai, prompt_toolkit,
rich, and friends (~seconds of cold start), which is exactly the window the
shimmer covers. ``code_puppy.boot_trace`` and ``code_puppy.splash`` are
stdlib-only by design -- keep both that way.
"""

import logging
import os
import sys

from code_puppy.boot_trace import begin_boot, end_boot, span
from code_puppy.splash import _NullSplash, start_splash


def _splash_skip_reason() -> str:
    """Name why start_splash() returned its no-op; mirrors the gates in splash.py."""
    if "--acp" in sys.argv:
        return "acp"
    try:
        if not sys.stdout.isatty():
            return "non_tty"
    except Exception:
        logger = logging.getLogger(__name__)
        logger.debug("stdout tty probe failed", exc_info=True)
        return "non_tty"
    if (
        os.environ.get("CODE_PUPPY_NO_SPLASH")
        or os.environ.get("NO_COLOR")
        or os.environ.get("TERM", "") == "dumb"
    ):
        return "env"
    return "disabled"


begin_boot()
with span("splash") as splash_span:
    _splash = start_splash()
    if isinstance(_splash, _NullSplash):
        splash_span.skip(_splash_skip_reason())

try:
    try:
        # Before the runner import so an import-time crash is recorded too.
        with span("error_hooks"):
            from code_puppy.error_hooks import install_error_hooks

            install_error_hooks()
    except Exception:
        logging.getLogger(__name__).debug(
            "installing the error hooks failed", exc_info=True
        )
    with span("runner.import"):
        from code_puppy.cli_runner import main_entry
except BaseException as exc:
    end_boot(exc)
    raise
finally:
    _splash.stop()

__all__ = ["main_entry"]

if __name__ == "__main__":
    main_entry()
