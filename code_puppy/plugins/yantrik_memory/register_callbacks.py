"""Register yantrik_memory with Code Puppy's callback system.

Hooks wired:
* ``load_prompt``          -> passive recall block in the system prompt
* ``user_prompt_submit``   -> log user turn (episodic) + distill durable facts
* ``agent_run_end``        -> record the agent's response (episodic)
* ``register_tools``       -> defines yantrik tools in ``TOOL_REGISTRY``
* ``register_agent_tools`` -> advertises yantrik tools to every agent's list
* ``custom_command``       -> handles ``/yantrik`` and subcommands
* ``custom_command_help``  -> advertises ``/yantrik`` in the /help menu

Fail-soft and opt-in:
* If ``YANTRIK_MEMORY_DISABLED`` is set, NO callbacks register.
* If YantrikDB (the ONNX-backed engine) isn't importable, the plugin is
  silently inert — no callbacks register, boot is untouched.
* Memory itself defaults OFF; the user opts in via ``/yantrik enable``.
"""

from __future__ import annotations

from code_puppy.callbacks import register_callback
from code_puppy.messaging.bus import emit_debug

from . import commands, substrate, tools
from .config import DISABLED
from .recorder import distill_user_message, record_response
from .retriever import build_recall_block
from .state import is_enabled


def _initialize_once() -> bool:
    """Confirm the YantrikDB engine is importable. Idempotent + fail-soft.

    We don't open the store here (that happens lazily per turn, scoped to the
    cwd namespace). We only verify the dependency is present — if it isn't, the
    plugin stays inert.
    """
    if not substrate.MEMORY_AVAILABLE:
        emit_debug(
            f"[yantrik_memory] YantrikDB unavailable, plugin inert: "
            f"{substrate.IMPORT_ERROR!r}"
        )
        return False
    return True


def _on_load_prompt() -> str | None:
    """Sync hook — returns a passive recall fragment or None."""
    try:
        return build_recall_block()
    except Exception as exc:  # noqa: BLE001
        emit_debug(f"[yantrik_memory] load_prompt skipped: {exc!r}")
        return None


async def _on_user_prompt_submit(
    prompt: str, session_id: str | None = None
) -> None:
    """Async hook — log + distill the user turn. Never modifies the prompt."""
    try:
        distill_user_message(prompt, session_id)
    except Exception as exc:  # noqa: BLE001
        emit_debug(f"[yantrik_memory] user_prompt_submit skipped: {exc!r}")
    return None


def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Sync-bodied hook — record the agent response as episodic memory."""
    record_response(
        agent_name=agent_name,
        model_name=model_name,
        session_id=session_id,
        success=success,
        error=error,
        response_text=response_text,
        metadata=metadata,
    )


_YANTRIK_TOOL_NAMES = (
    "yantrik_recall",
    "yantrik_remember",
    "yantrik_stats",
)


def _advertise_tools_to_agent(agent_name: str | None = None) -> list[str]:
    """``register_agent_tools`` callback — advertise yantrik tools when enabled.

    When memory is toggled off (or never opted into), advertise NO tools so the
    agent doesn't see (and try to call) memory tools that would just bounce.
    """
    if not is_enabled():
        return []
    return list(_YANTRIK_TOOL_NAMES)


if not DISABLED and _initialize_once():
    register_callback("load_prompt", _on_load_prompt)
    register_callback("user_prompt_submit", _on_user_prompt_submit)
    register_callback("agent_run_end", _on_agent_run_end)
    register_callback("register_tools", tools.register_tools_callback)
    register_callback("register_agent_tools", _advertise_tools_to_agent)
    register_callback("custom_command", commands.handle)
    register_callback("custom_command_help", commands.help_entries)
