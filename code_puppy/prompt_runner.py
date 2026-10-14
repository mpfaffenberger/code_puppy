"""Prompt execution and headless (-p/-r) dispatch for the CLI runner.

Owns attachment-resolved agent execution (shared by interactive turns and
headless prompts), headless usage-file serialization, and the headless
autonomy system-prompt addition. Split out of ``cli_runner.py`` to keep
each module under 600 lines; this module has no cross-module imports
within the runner split.

Called by: cli_entry.py :: main() for headless dispatch selection;
interactive_runner.py :: interactive_mode() reuses
``run_prompt_with_attachments`` for interactive turns. Not imported
directly by callers that need patched pydantic-ai -- go through
``code_puppy.cli_runner`` first so ``apply_all_patches()`` runs.
"""

import asyncio
import json
import os
from pathlib import Path

from code_puppy.agents import get_current_agent
from code_puppy.command_line.attachments import (
    parse_prompt_attachments,
    resolve_user_prompt,
)
from code_puppy.i18n import t
from code_puppy.messaging import emit_info


_HEADLESS_AUTONOMY_PROMPT = """\
This is an unattended, non-interactive run. Never ask for confirmation, approval,
clarification, or manual verification, including through tools or MCP servers. Use
reasonable defaults, proceed autonomously, and validate with the tools available to
you. State any assumptions or optional manual checks only in the final response.\
"""


async def run_prompt_with_attachments(
    agent,
    raw_prompt: str,
    *,
    display_console=None,
    use_run_ui: bool = True,
):
    """Run the agent after parsing CLI attachments for image, video, and document support.

    Returns:
        tuple: (result, task) where result is the agent response and task is the asyncio task
    """
    import asyncio

    from code_puppy.messaging import emit_warning

    # Shared resolver: file paths, URLs, and pending clipboard images.
    # (Same helper powers mid-run steering injection — keep them in sync.)
    resolved = resolve_user_prompt(raw_prompt)

    for warning in resolved.warnings:
        emit_warning(warning)

    cleaned_prompt = resolved.text
    if not cleaned_prompt:
        emit_warning(t("cli.attachments.empty_prompt"))
        return None, None

    attachments = resolved.attachments
    link_attachments = resolved.link_attachments

    # IMPORTANT: shared console for all streams (markdown/thinking/tool tokens)
    # so output scrolls inside the bottom bar's scroll region.
    from code_puppy.agents.event_stream_handler import set_streaming_console

    set_streaming_console(display_console)

    # Create the agent task first so we can track and cancel it
    agent_task = asyncio.create_task(
        agent.run_with_mcp(
            cleaned_prompt,  # Use cleaned prompt (clipboard placeholders removed)
            attachments=attachments,
            link_attachments=link_attachments,
        )
    )

    # Escape hatch: a cancelled run can wedge mid-unwind (sub-agent/MCP
    # cancel-scope teardown). Racing the task against a detach event keeps
    # the REPL recoverable — repeated cancel gestures escalate to a detach
    # (see _run_signals.make_schedule_cancel) and we abandon the zombie.
    from code_puppy.agents._run_signals import (
        clear_detach_event,
        install_detach_event,
    )

    detach_event = asyncio.Event()
    install_detach_event(detach_event)

    async def _await_agent():
        detach_wait = asyncio.create_task(detach_event.wait())
        try:
            try:
                done, _ = await asyncio.wait(
                    {agent_task, detach_wait}, return_when=asyncio.FIRST_COMPLETED
                )
            except asyncio.CancelledError:
                # The waiter itself was cancelled (shutdown teardown) — same
                # contract as the old bare ``await agent_task`` path.
                emit_info(t("cli.agent.task_cancelled"))
                return None, agent_task
            if agent_task not in done:
                # Escalated cancel: abandon the stuck unwind, free the REPL.
                emit_warning(t("cli.agent.detached"))
                return None, agent_task
            if agent_task.cancelled():
                emit_info(t("cli.agent.task_cancelled"))
                return None, agent_task
            exc = agent_task.exception()
            if exc is not None:
                raise exc
            return agent_task.result(), agent_task
        finally:
            detach_wait.cancel()
            clear_detach_event()

    if use_run_ui:
        # Interactive run: bottom bar stays up while the agent works. run_ui() is
        # idempotent + exception-safe (no-ops on non-TTY), restoring the terminal.
        from code_puppy.messaging.run_ui import run_ui

        with run_ui():
            return await _await_agent()
    return await _await_agent()


def _write_usage_file(path: Path, usage) -> None:
    """Atomically serialize authoritative model usage for automation clients."""
    cost = getattr(usage, "cost", None)
    payload = {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_tokens", 0),
        "cache_write_tokens": getattr(usage, "cache_write_tokens", 0),
        "requests": getattr(usage, "requests", 0),
        "tool_calls": getattr(usage, "tool_calls", 0),
        "cost_usd": float(cost) if cost is not None else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


async def execute_single_prompt(
    prompt: str,
    message_renderer,
    *,
    session_name: str | None = None,
    usage_file: Path | None = None,
) -> None:
    """Execute one headless ``-p`` prompt, dispatching commands and autosaving.

    Agent turns persist under the explicitly resumed session, when supplied,
    or under this process's generated autosave session otherwise. Handled
    slash commands and shell pass-through do not create or overwrite sessions
    because they never invoke the agent.
    """
    from code_puppy.command_line.shell_passthrough import (
        execute_shell_passthrough,
        is_shell_passthrough,
    )

    if is_shell_passthrough(prompt):
        execute_shell_passthrough(prompt)
        return

    from code_puppy.command_line.command_handler import handle_command
    from code_puppy.config import (
        AUTOSAVE_DIR,
        get_current_session_name,
        record_quick_resume_sessions,
    )
    from code_puppy.messaging import (
        emit_error,
        emit_info,
        emit_warning,
        get_message_bus,
    )
    from code_puppy.messaging.messages import AgentResponseMessage
    from code_puppy.session_lifecycle import persist_named_session

    # Match interactive: strip attachments, run handled commands without an
    # agent run, let command-provided replacement text reach the agent.
    command_prompt = (parse_prompt_attachments(prompt).prompt or "").strip()
    if command_prompt.startswith("/"):
        try:
            command_result = handle_command(command_prompt)
        except Exception as command_error:
            emit_error(t("cli.command.error", error=command_error))
            return

        if command_result is True:
            return
        if command_result == "__AUTOSAVE_LOAD__":
            emit_warning(t("cli.autosave.headless_unsupported"))
            return
        if isinstance(command_result, str):
            prompt = command_result

    effective_session_name = session_name or get_current_session_name()
    agent = None
    emit_info(t("cli.headless.executing", prompt=prompt))

    try:
        agent = get_current_agent()
        # Headless -p mode: no run UI (no bottom bar, no line editor) —
        # output must stay plain for pipes/CI even when stdout is a TTY.
        with agent.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
            result, _agent_task = await run_prompt_with_attachments(
                agent,
                prompt,
                display_console=message_renderer.console,
                use_run_ui=False,
            )
        if result is None:
            return

        get_message_bus().emit(
            AgentResponseMessage(content=result.output, is_markdown=True)
        )
        if usage_file is not None:
            usage = result.usage
            _write_usage_file(usage_file, usage() if callable(usage) else usage)

        # The runtime result includes the final assistant response that the
        # incremental history can otherwise miss.
        if hasattr(result, "all_messages"):
            agent.set_message_history(list(result.all_messages()))

    except asyncio.CancelledError:
        emit_warning(t("cli.headless.cancelled"))
    except Exception as error:
        emit_error(t("cli.headless.error", error=error))
    finally:
        try:
            session_agent = agent or get_current_agent()
            persist_named_session(
                session_agent,
                effective_session_name,
                base_dir=Path(AUTOSAVE_DIR),
                auto_saved=True,
            )
            # Point quick-resume at this session (auto and -r NAME saves). Only
            # on success — persist_named_session exceptions skip this block.
            record_quick_resume_sessions(effective_session_name)
        except Exception as save_error:
            # The response has already been emitted; a persistence failure
            # must not hide the primary result.
            emit_error(
                t(
                    "cli.headless.save_failed",
                    session=effective_session_name,
                    error=save_error,
                )
            )
