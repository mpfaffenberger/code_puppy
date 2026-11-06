"""Main entry point for Code Puppy CLI.

This module re-exports the main_entry function from cli_runner for backwards
compatibility. All the actual logic lives in cli_runner.py.

The boot-trace root opens first, then the neon splash starts BEFORE the
cli_runner import below: that import pulls in pydantic-ai, prompt_toolkit,
rich, and friends (~seconds of cold start), which is exactly the window the
shimmer covers. ``code_puppy.boot_trace`` and ``code_puppy.splash`` are
stdlib-only by design -- keep both that way, and keep them first.

In-tree plugins that must run setup before those heavy imports (see
``code_puppy.early_startup``) are given their turn inside the same window.
"""

import logging

from code_puppy.boot_trace import begin_boot, end_boot, span
from code_puppy.splash import start_splash


begin_boot()
with span("splash") as splash_span:
    _splash = start_splash()
    skip_reason = getattr(_splash, "reason", None)
    if skip_reason:
        splash_span.skip(skip_reason)

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
    # Plugin setup that must precede the heavy imports. Failed hooks are
    # recorded in errors.log before the runner import; never raises.
    with span("early_startup"):
        from code_puppy.early_startup import report_failures, run_early_startup

        report_failures(run_early_startup())
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
