"""Agent Steering plugin — Ctrl+T to pause the agent and inject a
steering message.

Wire-up:
- Listens to the ``agent_pause_requested`` callback (fired by the
  key listener when the user presses the configured pause key).
- Pauses the agent via the bus, SUSPENDS the key listener (so it lets
  go of stdin), opens a prompt_toolkit editor in a worker thread to
  collect the steer text, then RESUMES the listener + injects + resumes.

Ctrl+T is the ONLY entry point. A typed ``/steer`` slash command used to
exist, but slash commands can only be typed at the input prompt — which
is unavailable while the agent is running. Combined with the start-of-run
drain that scrubs any pre-run steer queue (cross-run leakage protection),
the typed command was dead code, so it's been removed.
"""

from __future__ import annotations

import asyncio

from code_puppy.agents._key_listeners import get_active_handle
from code_puppy.callbacks import register_callback
from code_puppy.messaging import (
    PauseAgentCommand,
    ResumeAgentCommand,
    SteerAgentCommand,
    emit_info,
    emit_warning,
    get_message_bus,
)
from code_puppy.messaging.spinner import pause_all_spinners

from .steering_prompt import collect_steering_message


async def _on_pause_requested() -> None:
    """Triggered when the user presses the pause key while the agent runs."""
    bus = get_message_bus()
    # 1. Immediately flip the controller into paused state.
    bus.provide_response(PauseAgentCommand(reason="user steering request"))
    # Tear down the spinner immediately. ``event_stream_handler`` also
    # pauses spinners at the top of its next iteration, but if we're
    # between events (handler is awaiting the next chunk) it won't fire
    # until the model emits the next event — by which time the editor
    # is already on top of it. Bonus: with ConsoleSpinner.resume() now
    # guarded by ``PauseController.is_paused()``, nothing can accidentally
    # bring the spinner back during the pause.
    pause_all_spinners()
    # Tiny sleep so Rich's Live display actually clears the line before
    # prompt_toolkit grabs the terminal.
    await asyncio.sleep(0.05)
    emit_info(
        "⏸️  Agent paused. Type your steering message — Enter to submit, Esc to cancel."
    )

    # 2. Suspend the key-listener so prompt_toolkit has exclusive stdin.
    #    Without this, two threads fight for stdin and the terminal can
    #    end up bricked when the editor exits. ``get_active_handle()``
    #    returns None in non-TTY / test contexts; that's fine.
    handle = get_active_handle()
    if handle is not None:
        if not handle.suspend(timeout=1.0):
            emit_warning(
                "Could not suspend key listener within 1s; "
                "steering input may not work correctly."
            )

    # 3. prompt_toolkit blocks → run in a worker thread.
    # ``result`` is either ``None`` (cancelled / empty) or ``(text, mode)``.
    result: object
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, collect_steering_message)
    except Exception as exc:
        emit_warning(f"Steering prompt failed: {exc}. Resuming agent.")
        result = None
    finally:
        if handle is not None:
            handle.resume()

    # 4. Submit the steer (if any) and resume the agent.
    if result and isinstance(result, tuple) and result[0] and result[0].strip():
        text, mode = result
        stripped = text.strip()
        bus.provide_response(SteerAgentCommand(text=stripped, mode=mode))
        preview = stripped[:80] + ("..." if len(stripped) > 80 else "")
        mode_label = "🎯 STEER NOW" if mode == "now" else "📨 QUEUE"
        emit_info(
            f"✍️  Steer queued [{mode_label}] ({len(stripped)} chars): {preview!r}"
        )
        if mode == "now":
            emit_info(
                "🎯 Steering queued; agent will see it before its next model call."
            )
        else:
            emit_info(
                "📨 Steering queued; agent will see it after current turn completes."
            )
    else:
        emit_info("▶️  Resuming agent (no steering message).")
    bus.provide_response(ResumeAgentCommand())


register_callback("agent_pause_requested", _on_pause_requested)
