"""Interactive REPL loop: input, slash commands, cancel/continuation,
autosave ordering, signal/renderer lifecycle. Depends on:
interactive_support.py; prompt_runner.py::run_prompt_with_attachments().
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from code_puppy.command_line.attachments import parse_prompt_attachments
from code_puppy.config import (
    AUTOSAVE_DIR,
    finalize_autosave_session,
    get_current_session_name,
    record_terminal_session,
    save_command_to_history,
)
from code_puppy.i18n import t
from code_puppy.interactive_support import (
    _interactive_sigint_guard,
    _persistent_prompt_parts,
    _prompt_echo_text,
    _render_turn_exception,
    _save_autosave_snapshot,
    _shutdown_agent_task,
    _use_persistent_prompt,
)
from code_puppy.prompt_runner import run_prompt_with_attachments
from code_puppy.terminal_utils import (
    print_truecolor_warning,
    reset_windows_terminal_ansi,
    reset_windows_terminal_full,
)


async def interactive_mode(message_renderer, initial_command: str = None) -> None:
    """Run the agent in interactive mode."""
    from code_puppy.command_line.command_handler import handle_command

    display_console = message_renderer.console
    from rich.text import Text

    from code_puppy.messaging import emit_info, emit_system_message

    # Pass a Text object (not a plain str): the SYSTEM renderer escapes Rich
    # markup in plain strings before printing (see renderers.py), so inline
    # "[bold]...[/bold]" in the i18n string would show up as literal
    # brackets. A Text object bypasses that string branch entirely and
    # renders as one line, actually bold.
    emit_system_message(Text(t("cli.help.press_tab"), style="bold"))
    # Tell the user how relentless the puppy is configured to be.
    from code_puppy.config import get_agency_level, get_speculative_code_mode_enabled

    emit_info(t("cli.agency.status", level=get_agency_level().upper()))
    # Advertise the chord: the feature is invisible until someone presses it.
    speculation_key = (
        "cli.speculation.on"
        if get_speculative_code_mode_enabled()
        else "cli.speculation.off"
    )
    emit_info(t(speculation_key))
    # Print truecolor warning LAST so it's the most visible thing on startup
    # Big ugly red box should be impossible to miss!
    print_truecolor_warning(display_console)

    # Shell pass-through for initial_command: !<cmd> bypasses the agent
    if initial_command:
        from code_puppy.command_line.shell_passthrough import (
            execute_shell_passthrough,
            is_shell_passthrough,
        )

        if is_shell_passthrough(initial_command):
            execute_shell_passthrough(initial_command)
            initial_command = None

    # Initialize the runtime agent manager
    if initial_command:
        from code_puppy.agents import get_current_agent
        from code_puppy.messaging import emit_info, emit_success, emit_system_message

        agent = get_current_agent()
        emit_info(t("cli.initial_command.processing", command=initial_command))

        try:
            # Skip the run UI if a tool is already waiting for user input
            # (the input prompt owns the terminal in that case).
            try:
                from code_puppy.tools.command_runner import is_awaiting_user_input

                awaiting_input = is_awaiting_user_input()
            except ImportError:
                awaiting_input = False

            response, agent_task = await run_prompt_with_attachments(
                agent,
                initial_command,
                display_console=display_console,
                use_run_ui=not awaiting_input,
            )
            if response is not None:
                agent_response = response.output

                # Update agent history with the complete conversation (incl. final response).
                if hasattr(response, "all_messages"):
                    agent.set_message_history(list(response.all_messages()))

                # Emit structured message for proper markdown rendering
                from code_puppy.messaging import get_message_bus
                from code_puppy.messaging.messages import AgentResponseMessage

                response_msg = AgentResponseMessage(
                    content=agent_response,
                    is_markdown=True,
                )
                get_message_bus().emit(response_msg)

                emit_success(t("cli.initial_command.continuing"))
                emit_system_message(t("cli.initial_command.preserved"))

        except Exception as e:
            from code_puppy.messaging import emit_error

            emit_error(t("cli.initial_command.error", error=str(e)))

    # Autosave loading is now manual - use /autosave_load command

    record_terminal_session(get_current_session_name(), overwrite=False)
    # Track the current agent task for cancellation on quit
    current_agent_task = None
    # Classic prompt: timestamp of the last idle Ctrl+C, for the
    # double-tap-to-quit gesture (persistent mode tracks its own in run_ui).
    last_idle_ctrl_c = 0.0

    # Baseline SIGINT guard for the REPL's whole life: Ctrl+C = cancel (Ctrl+D
    # quits); without it, a fast double-tap in the handler gap raises
    # KeyboardInterrupt and exits the process. Deliberately never restored.
    try:
        signal.signal(signal.SIGINT, _interactive_sigint_guard)
    except (ValueError, OSError):
        pass

    # Field diagnostics: `kill -USR2 <pid>` dumps thread + asyncio-task
    # stacks to ~/.code_puppy/stackdumps/ — the conviction kit for wedged
    # cancellations (a frozen REPL can't be introspected any other way).
    try:
        from code_puppy.diagnostics import install_stack_dump_handler

        install_stack_dump_handler(asyncio.get_running_loop())
    except Exception:
        pass  # diagnostics must never block the REPL

    # ------------------------------------------------------------------
    # Persistent-prompt mode: the bottom-bar editor is THE prompt (idle AND
    # running) — pinned input row, output scrolls above. Classic path behind
    # rollback flag / non-TTY auto-degrade (see _use_persistent_prompt).
    # ------------------------------------------------------------------
    persistent_prompt = False
    if _use_persistent_prompt():
        try:
            from code_puppy.messaging.run_ui import start_persistent_ui

            _prefix, _prefix_sgrs = _persistent_prompt_parts()
            persistent_prompt = start_persistent_ui(
                prompt_prefix=_prefix, prefix_sgrs=_prefix_sgrs
            )
        except Exception:
            persistent_prompt = False  # degrade to classic on any failure

    while True:
        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        # Get the custom prompt from the current agent, or use default
        current_agent = get_current_agent()
        user_prompt = current_agent.get_user_prompt() or t("cli.prompt.enter_task")

        if not persistent_prompt:
            # Persistent path drops the per-iteration banner — the pinned
            # prompt row + transcript echo replace it.
            emit_info(f"{user_prompt}\n")

        try:
            if persistent_prompt:
                from code_puppy.messaging.run_ui import (
                    set_idle_prompt_prefix,
                    wait_for_idle_submission,
                )

                # Model/agent may have changed since last turn.
                prompt_prefix, prompt_prefix_sgrs = _persistent_prompt_parts()
                set_idle_prompt_prefix(prompt_prefix, prompt_prefix_sgrs)
                # Idle + queued prompts (/queue or cancelled-run leftovers): consume
                # the oldest now; mid-run steers drain in _runtime's loop instead.
                from code_puppy.messaging.pause_controller import (
                    get_pause_controller as _get_pc,
                )

                queued_task = _get_pc().pop_next_steer_queued()
                if queued_task is not None:
                    task = queued_task
                    emit_info(_prompt_echo_text(task))
                    emit_info(t("cli.queue.running"))
                else:
                    # Raises EOFError on Ctrl+D-with-empty-buffer, which the
                    # existing quit branch below handles.
                    task = await wait_for_idle_submission()
                    # Echo the user's text (bold, '> ') into scrollback — the editor
                    # clears its row on submit, and repainting the full prompt chrome
                    # doubled every line's noise. Text() so bracket-y input renders as-is.
                    emit_info(_prompt_echo_text(task))
            else:
                # Classic (non-TTY / rollback) prompt: plain blocking input.
                # No completion here -- the persistent bottom-bar editor is
                # the featured path; this branch exists for pipes, CI, and
                # the CODE_PUPPY_CLASSIC_PROMPT escape hatch.
                reset_windows_terminal_ansi()
                task = input(">>> ")
                # Classic input has no editor: capture history here, even for
                # shell/slash/exit commands that return before agent dispatch.
                save_command_to_history(task)

        except (KeyboardInterrupt, asyncio.CancelledError) as cancel_exc:
            # Ctrl+C: cancel input and continue. Reset terminal state on Windows
            # so it doesn't become unresponsive.
            reset_windows_terminal_full()
            from code_puppy.callbacks import on_interactive_turn_cancel
            from code_puppy.messaging import emit_success, emit_warning
            from code_puppy.messaging.run_ui import DOUBLE_CTRL_C_WINDOW_S

            # Double Ctrl+C at the idle prompt quits like Ctrl+D.
            # CancelledError never counts.
            was_plain_ctrl_c = isinstance(cancel_exc, KeyboardInterrupt)
            now = time.monotonic()
            if was_plain_ctrl_c and now - last_idle_ctrl_c <= DOUBLE_CTRL_C_WINDOW_S:
                emit_success("\n" + t("cli.goodbye_ctrld"))
                await _shutdown_agent_task(current_agent_task)
                break
            last_idle_ctrl_c = now if was_plain_ctrl_c else 0.0

            await on_interactive_turn_cancel("", reason="Ctrl+C")
            emit_warning("\n" + t("cli.input.cancelled"))
            continue
        except EOFError:
            # Handle Ctrl+D - exit the application
            from code_puppy.messaging import emit_success

            emit_success("\n" + t("cli.goodbye_ctrld"))

            # Cancel any running agent task for clean shutdown (bounded — a
            # stuck unwind must not freeze Ctrl+D).
            await _shutdown_agent_task(current_agent_task)

            break

        # Shell pass-through: !<command> executes directly, bypassing the agent
        from code_puppy.command_line.shell_passthrough import (
            execute_shell_passthrough,
            is_shell_passthrough,
        )

        if is_shell_passthrough(task):
            # The shell owns the terminal — release the bar + key listener
            # (no-op in classic mode where neither is active at idle).
            from code_puppy.messaging.run_ui import suspended_run_ui

            with suspended_run_ui():
                execute_shell_passthrough(task)
            continue

        # Check for exit commands (plain text or command form)
        if task.strip().lower() in ["exit", "quit"] or task.strip().lower() in [
            "/exit",
            "/quit",
        ]:
            from code_puppy.messaging import emit_success

            emit_success(t("cli.goodbye"))

            # Cancel any running agent task for clean shutdown (bounded — a
            # stuck unwind must not freeze `exit`).
            await _shutdown_agent_task(current_agent_task)

            # The renderer is stopped in the finally block of main().
            break

        # Backward-compat: bare `clear` → `/clear` so session_commands' handler
        # stays the single source of truth.
        if task.strip().lower() == "clear":
            task = "/clear"

        # Parse attachments first so leading paths aren't misread as commands
        processed_for_commands = parse_prompt_attachments(task)
        cleaned_for_commands = (processed_for_commands.prompt or "").strip()

        # Handle / commands based on cleaned prompt (after stripping attachments)
        if cleaned_for_commands.startswith("/"):
            try:
                # Commands may open menus; release the bar for the duration
                # (no-op in classic mode).
                from code_puppy.messaging.run_ui import suspended_run_ui

                with suspended_run_ui():
                    command_result = handle_command(cleaned_for_commands)
            except Exception as e:
                from code_puppy.messaging import emit_error

                emit_error(t("cli.command.error", error=e))
                # Continue interactive loop instead of exiting
                continue
            if command_result is True:
                continue
            elif isinstance(command_result, str):
                if command_result == "__AUTOSAVE_LOAD__":
                    # Handle async autosave loading
                    try:
                        # Check if we're in a real interactive terminal
                        # (not pexpect/tests) - interactive picker requires proper TTY
                        use_interactive_picker = (
                            sys.stdin.isatty() and sys.stdout.isatty()
                        )

                        # Allow environment variable override for tests
                        if os.getenv("CODE_PUPPY_NO_TUI") == "1":
                            use_interactive_picker = False

                        if use_interactive_picker:
                            # Use interactive picker for terminal sessions
                            from code_puppy.agents.agent_manager import (
                                get_current_agent,
                            )
                            from code_puppy.command_line.autosave_menu import (
                                interactive_autosave_picker,
                            )
                            from code_puppy.config import (
                                pin_current_session_name,
                            )
                            from code_puppy.messaging import (
                                emit_error,
                                emit_success,
                                emit_warning,
                            )
                            from code_puppy.session_storage import load_session

                            from code_puppy.messaging.run_ui import (
                                suspended_run_ui,
                            )

                            with suspended_run_ui():
                                chosen_session = await interactive_autosave_picker()

                            if not chosen_session:
                                emit_warning(t("cli.autosave.load_cancelled"))
                                continue

                            # Load the session
                            base_dir = Path(AUTOSAVE_DIR)
                            history = load_session(chosen_session, base_dir)

                            agent = get_current_agent()
                            agent.set_message_history(history)

                            # Set current autosave session
                            pin_current_session_name(chosen_session)

                            total_tokens = sum(
                                agent.estimate_tokens_for_message(msg)
                                for msg in history
                            )
                            session_path = base_dir / f"{chosen_session}.json"

                            emit_success(
                                t(
                                    "cli.autosave.loaded",
                                    messages=len(history),
                                    tokens=total_tokens,
                                )
                            )
                            emit_info(t("cli.autosave.loaded_path", path=session_path))

                            # Display recent message history for context
                            from code_puppy.command_line.autosave_menu import (
                                display_resumed_history,
                            )

                            display_resumed_history(history)
                        else:
                            # No TTY, no picker: the old text-prompt fallback
                            # was an interactive prompt in a non-interactive
                            # environment. Point at the explicit flag instead.
                            from code_puppy.messaging import emit_warning

                            emit_warning(t("cli.autosave.tui_required"))

                    except Exception as e:
                        from code_puppy.messaging import emit_error

                        emit_error(t("cli.autosave.load_failed", error=e))
                    continue
                else:
                    # The raw slash command was captured by the input owner;
                    # its expansion is a distinct newly created prompt.
                    task = command_result
                    save_command_to_history(task)
            elif command_result is False:
                # Command not recognized, continue with normal processing
                pass

        if task.strip():
            # History belongs to input capture (editor/classic/queue insertion),
            # not dispatch: queued or deferred inputs may already be recorded.
            turn_result = None
            turn_success = False
            turn_error = None

            try:
                # No need to get agent directly - use manager's run methods

                # Use our custom helper to enable attachment handling with
                # the bottom-bar run UI active for the duration.
                result, current_agent_task = await run_prompt_with_attachments(
                    current_agent,
                    task,
                    display_console=message_renderer.console,
                )
                # Check if the task was cancelled (but don't show message if we just killed processes)
                if result is None:
                    # Windows-specific: Reset terminal state after cancellation
                    reset_windows_terminal_ansi()
                    # Windows: re-clamp raw-Ctrl+C mode after terminal reset
                    try:
                        from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                        ensure_ctrl_c_disabled()
                    except ImportError:
                        pass
                    from code_puppy.callbacks import on_interactive_turn_cancel

                    await on_interactive_turn_cancel(task, reason="cancellation")
                    _save_autosave_snapshot()
                    continue
                # Get the structured response
                agent_response = result.output

                # Emit structured message for proper markdown rendering
                from code_puppy.messaging import get_message_bus
                from code_puppy.messaging.messages import AgentResponseMessage

                response_msg = AgentResponseMessage(
                    content=agent_response,
                    is_markdown=True,
                )
                get_message_bus().emit(response_msg)

                # Update history with the complete conversation — history_processors
                # may miss the final message, so use result.all_messages().
                if hasattr(result, "all_messages"):
                    current_agent.set_message_history(list(result.all_messages()))

                turn_result = result
                turn_success = True

                # Flush so the next prompt isn't swallowed behind the agent response.
                if hasattr(display_console.file, "flush"):
                    display_console.file.flush()

                await asyncio.sleep(
                    0.1
                )  # Brief pause to ensure all messages are rendered

            except KeyboardInterrupt:
                # Defense-in-depth: a bare KeyboardInterrupt mid-unwind must not
                # escape to main_entry — treat as turn cancel (Ctrl+D exits only).
                if current_agent_task is not None and not current_agent_task.done():
                    current_agent_task.cancel()
                from code_puppy.callbacks import on_interactive_turn_cancel
                from code_puppy.messaging import emit_warning

                await on_interactive_turn_cancel(task, reason="Ctrl+C")
                emit_warning("\n" + t("cli.turn.cancelled"))
                _save_autosave_snapshot()
                continue
            except Exception as e:
                turn_error = e
                _render_turn_exception(e)

            # Auto-save session if enabled (moved outside the try block to avoid being swallowed)
            _save_autosave_snapshot()

            # ================================================================
            # CONTINUATION LOOP: plugins may request follow-up prompt runs.
            # ================================================================
            from code_puppy.callbacks import (
                on_interactive_turn_cancel,
                on_interactive_turn_end,
            )
            from code_puppy.messaging import emit_system_message

            continuation_prompt = task
            continuation_result = turn_result
            continuation_success = turn_success
            continuation_error = turn_error

            while True:
                continuation_requests = await on_interactive_turn_end(
                    current_agent,
                    continuation_prompt,
                    continuation_result,
                    success=continuation_success,
                    error=continuation_error,
                )
                continuation = next(
                    (r for r in continuation_requests if isinstance(r, dict)),
                    None,
                )
                if not continuation:
                    break

                next_prompt = str(continuation.get("prompt") or "").strip()
                if not next_prompt:
                    break

                if continuation.get("clear_context", False):
                    new_session_id = finalize_autosave_session()
                    current_agent.clear_message_history()
                    emit_system_message(
                        t("cli.context.cleared", session=new_session_id)
                    )

                delay = float(continuation.get("delay") or 0)
                if delay > 0:
                    await asyncio.sleep(delay)

                continuation_prompt = next_prompt
                continuation_result = None
                continuation_success = False
                continuation_error = None

                try:
                    result, current_agent_task = await run_prompt_with_attachments(
                        current_agent,
                        next_prompt,
                        display_console=message_renderer.console,
                    )

                    if result is None:
                        await on_interactive_turn_cancel(
                            next_prompt, reason="cancellation"
                        )
                        _save_autosave_snapshot()
                        break

                    agent_response = result.output
                    response_msg = AgentResponseMessage(
                        content=agent_response,
                        is_markdown=True,
                    )
                    get_message_bus().emit(response_msg)

                    if hasattr(result, "all_messages"):
                        current_agent.set_message_history(list(result.all_messages()))

                    if hasattr(display_console.file, "flush"):
                        display_console.file.flush()
                    await asyncio.sleep(0.1)

                    _save_autosave_snapshot()
                    continuation_result = result
                    continuation_success = True

                except KeyboardInterrupt:
                    await on_interactive_turn_cancel(next_prompt, reason="Ctrl+C")
                    _save_autosave_snapshot()
                    break
                except Exception as e:
                    continuation_error = e
                    _render_turn_exception(e)
                    _save_autosave_snapshot()

            # Windows: re-clamp raw-Ctrl+C mode after each iteration, as
            # various operations may restore console mode
            try:
                from code_puppy.terminal_utils import ensure_ctrl_c_disabled

                ensure_ctrl_c_disabled()
            except ImportError:
                pass

    # REPL over: tear down the persistent prompt here; main()'s finally is the
    # belt-and-braces for exception paths.
    if persistent_prompt:
        try:
            from code_puppy.messaging.run_ui import stop_persistent_ui

            stop_persistent_ui()
        except Exception:
            pass
