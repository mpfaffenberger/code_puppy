"""``/fork`` — spawn a sub-agent in the background and keep working.

Unlike the ``invoke_agent`` tool (where the *agent* delegates and awaits),
``/fork`` lets the *user* launch a sub-agent as a fire-and-forget asyncio
task. It works at the idle prompt AND mid-run: both command dispatch paths
execute on the main thread with the event loop running, so the fork runs
concurrently with whatever the foreground agent is doing.

Commands:
    /fork <prompt>              fork the current agent with the prompt
    /fork @<agent> <prompt>     fork a named agent
    /fork @<agent> @<model> <prompt>  fork with a specific model
    /fork cancel <id>           cancel a running fork
    /forks                      show status of all forks this session

Results are explicitly bridged onto the interactive transcript queue when
the fork completes. Forks suppress ``_invoke_agent_impl``'s generic structured
response and emit one fork-specific, theme-aware banner plus Markdown body;
detached tasks cannot rely on the invocation renderer still owning the active
transcript. The completion banner then adds duration and resumable session id.

Note: Ctrl+C's cancel sweep clears ``_active_subagent_tasks``, which
includes forked runs — cancelling the agent takes forks down with it.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback

_FORK = "fork"
_FORKS = "forks"
_PROMPT_PREVIEW_LEN = 60


@dataclass
class _ForkRecord:
    """Bookkeeping for one background sub-agent run."""

    fork_id: int
    agent_name: str
    prompt: str
    task: asyncio.Task
    started_at: float = field(default_factory=time.monotonic)
    status: str = "running"  # running | done | failed | cancelled
    elapsed: Optional[float] = None
    session_id: Optional[str] = None


_forks: Dict[int, _ForkRecord] = {}
_fork_ids = itertools.count(1)


# ---------------------------------------------------------------------------
# Messaging shims (lazy imports keep plugin load cheap and cycle-free)
# ---------------------------------------------------------------------------
def _emit_info(content) -> None:
    from code_puppy.messaging import emit_info

    emit_info(content)


def _emit_success(content) -> None:
    from code_puppy.messaging import emit_success

    emit_success(content)


def _emit_agent_response(content) -> None:
    from code_puppy.messaging import emit_agent_response

    emit_agent_response(content)


def _emit_warning(content) -> None:
    from code_puppy.messaging import emit_warning

    emit_warning(content)


def _emit_error(content) -> None:
    from code_puppy.messaging import emit_error

    emit_error(content)


def _started_message(fork_id: int, agent_name: str):
    """Build a Rich, theme-aware acknowledgement for a newly started fork."""
    from rich.text import Text

    from code_puppy.messaging.messages import MessageLevel
    from code_puppy.messaging.rich_renderer import DEFAULT_STYLES

    message = Text(f"fork #{fork_id}: ", style=DEFAULT_STYLES[MessageLevel.INFO])
    message.append(agent_name, style="bold")
    message.append(" started in the background — results land when it finishes (")
    message.append("/forks", style=DEFAULT_STYLES[MessageLevel.DEBUG])
    message.append(" for status)")
    return message


def _response_message(fork_id: int, agent_name: str, response: str):
    """Build the distinct, theme-aware banner and Markdown body for a fork."""
    from rich.console import Group
    from rich.markdown import Markdown
    from rich.text import Text

    from code_puppy.config import get_banner_color
    from code_puppy.messaging.messages import MessageLevel
    from code_puppy.messaging.rich_renderer import DEFAULT_STYLES

    header = Text(
        f" FORK #{fork_id} RESPONSE ",
        style=f"bold white on {get_banner_color('subagent_response')}",
    )
    header.append(" ")
    header.append(agent_name, style=f"bold {DEFAULT_STYLES[MessageLevel.INFO]}")
    return Group(Text(""), header, Markdown(response))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_fork_args(
    args: str,
) -> Tuple[Optional[str], Optional[str], str]:
    """Split ``@agent [@model] prompt...`` into (agent_name, model_name, prompt).

    Returns (None, None, args) when no ``@agent`` prefix is present, meaning
    "fork the current agent".
    """
    if args.startswith("@"):
        head, _, rest = args.partition(" ")
        agent_name = head[1:]
        rest = rest.strip()
        # Check for a second @ as model prefix
        if rest.startswith("@"):
            model_head, _, prompt = rest.partition(" ")
            return agent_name, model_head[1:], prompt.strip()
        return agent_name, None, rest
    return None, None, args


def _resolve_agent_name(requested: Optional[str]) -> Optional[str]:
    """Validate the requested agent (or default to the current one).

    Returns the resolved name, or ``None`` after emitting a warning.
    """
    from code_puppy.agents.agent_manager import (
        get_available_agents,
        get_current_agent_name,
    )

    if requested is None:
        return get_current_agent_name()

    available = get_available_agents()
    if requested in available:
        return requested

    _emit_warning(
        f"Unknown agent '@{requested}'. Available: " + ", ".join(sorted(available)),
    )
    return None


# ---------------------------------------------------------------------------
# Fork lifecycle
# ---------------------------------------------------------------------------
async def _run_fork(agent_name: str, prompt: str, model_name: str | None = None):
    """Run the sub-agent and publish its tool-equivalent completion signal."""
    from code_puppy.callbacks import on_post_tool_call
    from code_puppy.tools.subagent_invocation import _invoke_agent_impl

    started_at = time.monotonic()
    result = None
    try:
        # ``context`` is unused by the implementation; forks have no RunContext.
        result = await _invoke_agent_impl(
            context=None,
            agent_name=agent_name,
            prompt=prompt,
            model_name=model_name,
            emit_response_message=False,
        )
        return result
    finally:
        # /fork deliberately calls the shared implementation directly rather than
        # entering through pydantic-ai's tool wrapper. Publish the same completion
        # lifecycle event so observers (notably the sub-agent panel) can retire
        # the row instead of displaying "writing response" forever.
        if result is not None:
            await on_post_tool_call(
                "invoke_agent",
                {"agent_name": agent_name, "prompt": prompt},
                result,
                (time.monotonic() - started_at) * 1000,
                {"detached_fork": True},
            )


def _on_fork_done(fork_id: int, task: asyncio.Task) -> None:
    """Done-callback (runs in-loop): record outcome + emit a banner."""
    record = _forks.get(fork_id)
    if record is None:  # pragma: no cover - defensive
        return
    record.elapsed = time.monotonic() - record.started_at
    tag = f"fork #{fork_id} ({record.agent_name})"

    try:
        if task.cancelled():
            record.status = "cancelled"
            _emit_warning(f"{tag} cancelled after {record.elapsed:.1f}s")
            return
        exc = task.exception()
        if exc is not None:
            record.status = "failed"
            _emit_error(f"{tag} crashed after {record.elapsed:.1f}s: {exc}")
            return
        result = task.result()
        record.session_id = getattr(result, "session_id", None)
        if getattr(result, "error", None):
            record.status = "failed"
            first_line = str(result.error).strip().splitlines()[0]
            _emit_error(f"{tag} failed after {record.elapsed:.1f}s: {first_line}")
            return
        record.status = "done"
        response = getattr(result, "response", None)
        if response:
            _emit_agent_response(
                _response_message(fork_id, record.agent_name, response)
            )
        _emit_success(
            f"{tag} finished in {record.elapsed:.1f}s"
            + (f" — session '{record.session_id}'" if record.session_id else "")
        )
    except Exception:  # pragma: no cover - banner must never break the loop
        record.status = "failed"


def _start_fork(agent_name: str, prompt: str, model_name: str | None = None) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _emit_warning("/fork needs a running event loop — can't fork here.")
        return

    fork_id = next(_fork_ids)
    task = loop.create_task(
        _run_fork(agent_name, prompt, model_name), name=f"fork-{fork_id}"
    )
    _forks[fork_id] = _ForkRecord(
        fork_id=fork_id, agent_name=agent_name, prompt=prompt, task=task
    )
    task.add_done_callback(lambda t, fid=fork_id: _on_fork_done(fid, t))
    _emit_info(_started_message(fork_id, agent_name))


def _cancel_fork(raw_id: str) -> None:
    try:
        fork_id = int(raw_id)
    except ValueError:
        _emit_warning(f"Usage: /fork cancel <id> — '{raw_id}' isn't a fork id.")
        return
    record = _forks.get(fork_id)
    if record is None:
        _emit_warning(f"No fork #{fork_id}. Try /forks.")
        return
    if record.task.done():
        _emit_info(f"fork #{fork_id} already {record.status}.")
        return
    record.task.cancel()
    _emit_info(f"cancelling fork #{fork_id} ({record.agent_name})...")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
def _handle_fork(command: str) -> bool:
    args = command.split(" ", 1)[1].strip() if " " in command else ""
    if not args:
        _emit_info(
            "Usage: /fork [@agent] [@model] <prompt> — run a sub-agent in the background.\n"
            "       /fork cancel <id>              — stop a running fork.\n"
            "       /forks                         — list forks."
        )
        return True

    head, _, rest = args.partition(" ")
    if head == "cancel":
        _cancel_fork(rest.strip())
        return True

    requested_agent, requested_model, prompt = _parse_fork_args(args)
    if not prompt:
        _emit_warning("Fork what, exactly? Usage: /fork [@agent] [@model] <prompt>")
        return True

    agent_name = _resolve_agent_name(requested_agent)
    if agent_name is None:
        return True

    _start_fork(agent_name, prompt, requested_model)
    return True


def _handle_forks(command: str) -> bool:
    if not _forks:
        _emit_info("No forks yet — /fork [@agent] [@model] <prompt> to start one.")
        return True

    from rich.table import Table

    table = Table(title="Forks", show_lines=False)
    table.add_column("id", justify="right")
    table.add_column("agent", style="cyan")
    table.add_column("status")
    table.add_column("time", justify="right")
    table.add_column("prompt", overflow="ellipsis", max_width=_PROMPT_PREVIEW_LEN)

    style_by_status = {
        "running": "yellow",
        "done": "green",
        "failed": "red",
        "cancelled": "dim",
    }
    for record in _forks.values():
        elapsed = (
            record.elapsed
            if record.elapsed is not None
            else time.monotonic() - record.started_at
        )
        status_style = style_by_status.get(record.status, "")
        table.add_row(
            str(record.fork_id),
            record.agent_name,
            f"[{status_style}]{record.status}[/{status_style}]"
            if status_style
            else record.status,
            f"{elapsed:.1f}s",
            record.prompt.replace("\n", " "),
        )
    _emit_info(table)
    return True


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name == _FORK:
        return _handle_fork(command)
    if name == _FORKS:
        return _handle_forks(command)
    return None


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            _FORK,
            "Spawn a sub-agent in the background: /fork [@agent] [@model] <prompt>",
        ),
        (_FORKS, "Show status of background forks"),
    ]


register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_cancel_fork",
    "_custom_help",
    "_handle_custom_command",
    "_handle_fork",
    "_handle_forks",
    "_on_fork_done",
    "_parse_fork_args",
    "_resolve_agent_name",
    "_start_fork",
]
