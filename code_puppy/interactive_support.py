"""Interactive-only support seams for the CLI runner.

Owns prompt UI (persistent bottom-bar vs classic), the baseline SIGINT
guard, agent-task shutdown on quit, turn-exception rendering, and the
interactive autosave snapshot wrapper. Split out of ``cli_runner.py`` to
keep each module under 600 lines; this module has no cross-module
imports within the runner split.

Called by: interactive_runner.py :: interactive_mode() for the loop that
calls these seams; cli_entry.py :: main() for ``_save_autosave_snapshot``.
Not imported directly by callers that need patched pydantic-ai -- go
through ``code_puppy.cli_runner`` first so ``apply_all_patches()`` runs.
"""

import asyncio
import os
import sys

from code_puppy.i18n import t
from code_puppy.messaging import emit_info


def _save_autosave_snapshot() -> None:
    """Persist the current autosave snapshot if autosave is enabled.

    No caller needs the success/failure signal (yet) -- keep it YAGNI.
    """
    from code_puppy.config import auto_save_session_if_enabled

    auto_save_session_if_enabled()


def _render_turn_exception(exc: Exception) -> None:
    """Render a turn-level exception without ever taking down the REPL.

    Transient model/connection failures (a dropped socket, a VPN/WiFi blip, a
    provider rate limit) are environment hiccups, not Code Puppy bugs. They get
    a friendly one-liner instead of a 60-line traceback, because a wall of
    stack frames makes a recoverable blip look fatal. Genuine errors still get
    the full traceback so they stay debuggable.

    The transient/not-transient decision reuses the same classifier that drives
    streaming auto-retries, so the two stay in lock-step by construction.

    Either way -- friendly one-liner OR full traceback -- the exception is
    persisted to ``~/.code_puppy/logs/errors.log`` so SRE / support can still
    see what actually happened upstream. The friendly UI is for the human,
    not for the audit trail.
    """
    from code_puppy.agents.base_agent import should_retry_streaming_exception
    from code_puppy.error_logging import log_error

    if should_retry_streaming_exception(exc):
        log_error(
            exc,
            context=(
                "interactive_support._render_turn_exception: transient model/connection "
                "error reached the REPL after auto-retry exhaustion (or from a "
                "non-streaming code path). User saw the friendly one-liner."
            ),
        )
        from code_puppy.messaging import emit_error

        emit_error(t("cli.error.model_transient", error_type=type(exc).__name__))
        return

    log_error(
        exc,
        context=(
            "interactive_support._render_turn_exception: non-transient turn exception "
            "reached the REPL. User saw the full traceback in the console."
        ),
    )
    from code_puppy.messaging.queue_console import get_queue_console

    get_queue_console().print_exception()


def _use_persistent_prompt() -> bool:
    """Should the REPL use the persistent bottom-bar prompt (Phase A)?

    False (-> classic plain-input path) when:
      * rollback flag: env CODE_PUPPY_CLASSIC_PROMPT=1 or config
        ``classic_prompt`` truthy — protects the eyeball-testing period;
      * CODE_PUPPY_NO_TUI=1 (tests / pexpect harnesses);
      * stdin/stdout isn't a real TTY (pipes, CI) — automatic degrade,
        not just the env flag;
      * the console can't be confirmed VT-capable (legacy Windows
        conhost) — the bar writes raw escapes to ``__stdout__``, so
        without VT it would render as escape soup at spinner speed.
    """
    truthy = {"1", "true", "yes", "on"}
    if os.environ.get("CODE_PUPPY_CLASSIC_PROMPT", "").strip().lower() in truthy:
        return False
    if os.environ.get("CODE_PUPPY_NO_TUI", "").strip() == "1":
        return False
    try:
        from code_puppy.config import get_value

        if str(get_value("classic_prompt") or "").strip().lower() in truthy:
            return False
    except Exception:
        pass
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except Exception:
        return False
    # Raw-VT gate: verify Windows VT processing up front (no-op on POSIX);
    # unconfirmed VT → classic prompt (bar never starts, no spinner tickers).
    try:
        from code_puppy.terminal_utils import ensure_windows_vt_processing

        if not ensure_windows_vt_processing():
            return False
    except Exception:
        pass  # the gate itself must never kill the persistent UI
    return True


def _persistent_prompt_parts() -> tuple:
    """``(plain_prefix, per_char_sgrs)`` for the bottom-bar editor.

    Flattens ``get_prompt_with_active_model()``'s FormattedText (read-only
    use) so idle and running prompts look identical — keeping the style
    classes as an out-of-band per-char SGR list (the bar sanitizes any
    in-band escapes, so colors can't ride inside the string itself).
    """
    try:
        from code_puppy.command_line.completers import (
            PROMPT_STYLES,
            get_prompt_with_active_model,
        )
        from code_puppy.messaging.prompt_prefix_style import (
            flatten_prompt_fragments,
        )

        formatted = get_prompt_with_active_model()
        return flatten_prompt_fragments(formatted, PROMPT_STYLES)
    except Exception:
        return ">>> ", []


def _prompt_echo_text(task: str):
    """Build a transcript echo using the active prompt foreground."""
    from rich.text import Text

    from code_puppy.callbacks import on_prompt_text_color

    prompt_color = on_prompt_text_color()
    style = f"bold {prompt_color}" if prompt_color else "bold"
    return Text(f"\n> {task}\n", style=style)


def _interactive_sigint_guard(_sig, _frame):
    """Baseline SIGINT handler for the interactive REPL.

    Ctrl+C in Code Puppy is a *cancel* gesture, never a *quit* gesture
    (Ctrl+D quits). During an agent run or a shell command the runtime
    installs its own SIGINT handler that turns Ctrl+C into a task cancel /
    shell kill, saving and later restoring whatever handler was in place.

    Between those windows -- and, critically, during the brief unwind after a
    run is cancelled but before the next handler is installed -- the handler
    would otherwise be Python's default, which raises ``KeyboardInterrupt``.
    A second fast Ctrl+C landing in that gap bubbles all the way up to
    ``main_entry`` and exits the whole process. That is the
    ``Ctrl+C Ctrl+C too fast`` crash.

    Installing this no-op-ish guard for the lifetime of the REPL means the
    saved/restored ``original`` handler is always benign: a stray Ctrl+C in
    any gap is swallowed instead of killing the process. The per-run and
    per-shell handlers still own cancellation while they're active.
    """
    # No cancel-owner is active, so swallow the signal — a fast repeat tap can't
    # escape to main_entry and exit. Windows: any SIGINT reaching Python means
    # console mode regressed; re-clamp (it kills wrapper launchers otherwise).
    try:
        from code_puppy.terminal_utils import ensure_ctrl_c_disabled

        ensure_ctrl_c_disabled()
    except Exception:
        pass
    # Persistent prompt: Ctrl+C clears the buffer (readline feel; Ctrl+D
    # quits), and a second idle Ctrl+C within DOUBLE_CTRL_C_WINDOW_S quits
    # like Ctrl+D. Only out-of-band SIGINTs land here — raw \x03 goes to the
    # key listener, which also owns mid-run cancel (remapped key ->
    # buffer-first clearing).
    try:
        from code_puppy.messaging.run_ui import (
            absorb_ctrl_c_if_composing,
            is_run_active,
            note_idle_ctrl_c,
        )

        if is_run_active():
            absorb_ctrl_c_if_composing()
        else:
            note_idle_ctrl_c()
    except Exception:
        pass
    return


#: How long the quit paths (double Ctrl+C / Ctrl+D / exit) wait for a
#: lingering agent task to finish cancelling before abandoning it. A stuck
#: unwind must never freeze the exit — process teardown reaps the zombie.
_QUIT_CANCEL_TIMEOUT_S = 5.0


async def _shutdown_agent_task(agent_task) -> None:
    """Cancel a lingering agent task on quit, bounded by a timeout.

    ``asyncio.wait`` (not ``wait_for``) on purpose: ``wait_for``'s timeout
    path awaits the inner cancellation, which is exactly the await that can
    wedge. ``wait`` just stops waiting.
    """
    from code_puppy.messaging import emit_warning

    if agent_task is None or agent_task.done():
        return
    emit_info(t("cli.agent.cancelling"))
    agent_task.cancel()
    done, _ = await asyncio.wait({agent_task}, timeout=_QUIT_CANCEL_TIMEOUT_S)
    if agent_task not in done:
        emit_warning(t("cli.agent.quit_cancel_timeout", seconds=_QUIT_CANCEL_TIMEOUT_S))
        return
    try:
        agent_task.result()
    except BaseException:
        pass  # Expected when cancelling — nothing to do with it on the way out.
