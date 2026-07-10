"""``/fork`` — spawn a sub-agent in the background and keep working.

Unlike the ``invoke_agent`` tool (where the *agent* delegates and awaits),
``/fork`` lets the *user* launch a sub-agent as a fire-and-forget asyncio
task. It works at the idle prompt AND mid-run: both command dispatch paths
execute on the main thread with the event loop running, so the fork runs
concurrently with whatever the foreground agent is doing.

Commands:
    /fork <prompt>            fork the current agent with the prompt
    /fork @<agent> <prompt>   fork a named agent
    /fork cancel <id>         cancel a running fork
    /forks                    show status of all forks this session

Results: ``_invoke_agent_impl`` already emits a ``SubAgentResponseMessage``
which the renderer displays as a full "AGENT RESPONSE" markdown panel, so
this plugin only adds a compact completion banner (id, agent, duration,
session) rather than re-printing the response.

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


def _emit_warning(content) -> None:
    from code_puppy.messaging import emit_warning

    emit_warning(content)


def _emit_error(content) -> None:
    from code_puppy.messaging import emit_error

    emit_error(content)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_fork_args(args: str) -> Tuple[Optional[str], str]:
    """Split ``@agent prompt...`` into (agent_name, prompt).

    Returns (None, args) when no ``@agent`` prefix is present, meaning
    "fork the current agent".
    """
    if args.startswith("@"):
        head, _, rest = args.partition(" ")
        return head[1:], rest.strip()
    return None, args


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
async def _run_fork(agent_name: str, prompt: str):
    """Run the sub-agent. Reuses the invoke_agent implementation wholesale."""
    from code_puppy.tools.subagent_invocation import _invoke_agent_impl

    # ``context`` is unused by the implementation; forks have no RunContext.
    return await _invoke_agent_impl(
        context=None,
        agent_name=agent_name,
        prompt=prompt,
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
        # The response itself was already rendered via SubAgentResponseMessage.
        _emit_success(
            f"{tag} finished in {record.elapsed:.1f}s"
            + (f" — session '{record.session_id}'" if record.session_id else "")
        )
    except Exception:  # pragma: no cover - banner must never break the loop
        record.status = "failed"


def _start_fork(agent_name: str, prompt: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _emit_warning("/fork needs a running event loop — can't fork here.")
        return

    fork_id = next(_fork_ids)
    task = loop.create_task(_run_fork(agent_name, prompt), name=f"fork-{fork_id}")
    _forks[fork_id] = _ForkRecord(
        fork_id=fork_id, agent_name=agent_name, prompt=prompt, task=task
    )
    task.add_done_callback(lambda t, fid=fork_id: _on_fork_done(fid, t))
    _emit_info(
        f"fork #{fork_id}: [bold cyan]{agent_name}[/bold cyan] started in the "
        f"background — results land when it finishes ([dim]/forks[/dim] for status)"
    )


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
            "Usage: /fork [@agent] <prompt> — run a sub-agent in the background.\n"
            "       /fork cancel <id>      — stop a running fork.\n"
            "       /forks                 — list forks."
        )
        return True

    head, _, rest = args.partition(" ")
    if head == "cancel":
        _cancel_fork(rest.strip())
        return True

    requested_agent, prompt = _parse_fork_args(args)
    if not prompt:
        _emit_warning("Fork what, exactly? Usage: /fork [@agent] <prompt>")
        return True

    agent_name = _resolve_agent_name(requested_agent)
    if agent_name is None:
        return True

    _start_fork(agent_name, prompt)
    return True


def _handle_forks(command: str) -> bool:
    if not _forks:
        _emit_info("No forks yet — /fork [@agent] <prompt> to start one.")
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
        (_FORK, "Spawn a sub-agent in the background: /fork [@agent] <prompt>"),
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
