"""The 0.0.x plugin hook registry, kept so existing plugins load unchanged.

``register_callback("<hook>", func)`` works as it always did. What changed is
who fires the hooks: ``code_puppy.compat.bridge`` translates the runtime's
moments into these calls.

Hooks come in three tiers:

* **Supported** hooks fire at the equivalent 1.0 moment.
* **Accepted** hooks register without error but never fire. 1.0 has no
  equivalent moment, or firing them would undo what the runtime guarantees
  (rewriting model messages breaks prompt caching, for example).
* **Removed** hooks were internal plumbing between 0.0.x core and its own
  plugins. They register and never fire too, and are listed separately so the
  bridge can say which is which.

New plugins should use the pydantic-ai-pax ``Plugin`` API instead.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

CallbackFunc = Callable[..., Any]
PhaseType = str
CustomCommandResult = bool | str | None

SUPPORTED = frozenset(
    {
        "startup",
        "shutdown",
        "session_end",
        "custom_command",
        "custom_command_help",
        "load_prompt",
        "pre_tool_call",
        "post_tool_call",
        "run_shell_command",
        "register_tools",
        "user_prompt_submit",
        "agent_run_start",
        "agent_run_end",
        "interactive_turn_end",
        "interactive_turn_cancel",
    }
)

REMOVED = frozenset(
    {
        "check_claude_oauth_token_expiry",
        "refresh_claude_oauth_token",
        "load_claude_oauth_models",
        "claude_oauth_authenticate",
        "should_skip_fallback_render",
        "agent_event_stream_start",
        "version_check",
    }
)

ACCEPTED = frozenset(
    {
        # Every tool from `register_tools` is offered to the agent (deferred),
        # so there is no per-agent list for `register_agent_tools` to extend.
        "register_agent_tools",
        "register_agents",
        "invoke_agent",
        "agent_exception",
        "edit_file",
        "create_file",
        "replace_in_file",
        "delete_snippet",
        "delete_file",
        "run_shell_command_output",
        "load_model_config",
        "load_models_config",
        "load_model_descriptions",
        "agent_reload",
        "usage_status",
        "file_permission",
        "stream_event",
        "thinking_display_filter",
        "termflow_style",
        "prompt_toolkit_style",
        "termflow_highlighter",
        "prompt_text_color",
        "register_model_type",
        "register_skills",
        "register_settings",
        "register_kennel_memory",
        "register_cli_args",
        "handle_cli_args",
        "get_model_system_prompt",
        "prepare_model_prompt",
        "agent_run_result",
        "model_select",
        "provider_credential_flow",
        "register_mcp_catalog_servers",
        "register_browser_types",
        "register_model_providers",
        "register_completion_provider",
        "message_history_processor_start",
        "message_history_processor_end",
        "on_message",
        "wrap_pydantic_agent",
        "agent_run_context",
        "agent_run_cancel",
        "pre_mcp_autostart",
        "pre_compact",
        "post_autosave",
        "session_browser_open",
        "notification",
        "awaiting_user_input",
        "git_branch_provider",
        "feature_capability",
        "transform_model_messages",
        "error_logged",
        "banner_notice",
        "prompt_ready",
    }
)

ALL_PHASES = SUPPORTED | ACCEPTED | REMOVED
BLOCKING_PHASES = frozenset({"pre_tool_call", "run_shell_command"})
"""Hooks whose consumers act on the result, so ``fail_closed`` means something."""


@dataclass(frozen=True)
class Registration:
    """One registered callback and the plugin that registered it."""

    func: CallbackFunc
    fail_closed: bool = False
    owner: str | None = None


@dataclass(frozen=True)
class CallbackError:
    """A callback raised. ``fail_closed`` callbacks block when this happens."""

    phase: str
    owner: str | None
    error: BaseException
    fail_closed: bool = False


_registry: dict[str, list[Registration]] = {}
_owner: ContextVar[str | None] = ContextVar("code_puppy_plugin_owner", default=None)


@contextmanager
def owned_by(plugin: str) -> Iterator[None]:
    """Attribute callbacks registered inside the block to ``plugin``."""
    token = _owner.set(plugin)
    try:
        yield
    finally:
        _owner.reset(token)


def register_callback(
    phase: PhaseType, func: CallbackFunc, fail_closed: bool = False
) -> None:
    """Register ``func`` for ``phase``. Registering the same function twice is a no-op."""
    if phase not in ALL_PHASES:
        raise ValueError(f"Unsupported callback phase: {phase!r}")
    if not callable(func):
        raise TypeError(
            f"Callback for {phase!r} must be callable, got {type(func).__name__}"
        )
    if fail_closed and phase not in BLOCKING_PHASES:
        raise ValueError(
            "fail_closed=True is only meaningful on phases whose consumers act on "
            f"the result: {', '.join(sorted(BLOCKING_PHASES))}"
        )
    registered = _registry.setdefault(phase, [])
    if any(entry.func is func for entry in registered):
        return
    registered.append(
        Registration(func=func, fail_closed=fail_closed, owner=_owner.get())
    )


def unregister_callback(phase: PhaseType, func: CallbackFunc) -> bool:
    """Remove ``func`` from ``phase``; ``False`` when it was not registered."""
    registered = _registry.get(phase, [])
    kept = [entry for entry in registered if entry.func is not func]
    _registry[phase] = kept
    return len(kept) != len(registered)


def clear_callbacks(phase: PhaseType | None = None) -> None:
    """Forget every callback, or those of one phase."""
    if phase is None:
        _registry.clear()
    else:
        _registry.pop(phase, None)


def unregister_owner(plugin: str) -> int:
    """Remove everything ``plugin`` registered; the number of callbacks removed."""
    removed = 0
    for phase, registered in _registry.items():
        kept = [entry for entry in registered if entry.owner != plugin]
        removed += len(registered) - len(kept)
        _registry[phase] = kept
    return removed


def get_callbacks(phase: PhaseType) -> list[CallbackFunc]:
    return [entry.func for entry in _registry.get(phase, [])]


def get_callback_owner(func: CallbackFunc) -> str | None:
    """The plugin that registered ``func``, when it was loaded as one."""
    for registered in _registry.values():
        for entry in registered:
            if entry.func is func:
                return entry.owner
    return None


def count_callbacks(phase: PhaseType | None = None) -> int:
    if phase is not None:
        return len(_registry.get(phase, []))
    return sum(len(registered) for registered in _registry.values())


def registrations(phase: PhaseType) -> list[Registration]:
    return list(_registry.get(phase, []))


def inert_registrations() -> dict[str, list[str]]:
    """Plugins that registered hooks 1.0 never fires, by plugin name."""
    found: dict[str, set[str]] = {}
    for phase, registered in _registry.items():
        if phase in SUPPORTED:
            continue
        for entry in registered:
            found.setdefault(entry.owner or "(unknown)", set()).add(phase)
    return {owner: sorted(phases) for owner, phases in sorted(found.items())}


def fire_sync(phase: PhaseType, *args: object, **kwargs: object) -> list[Any]:
    """Call every callback of ``phase`` now. A failing callback yields a ``CallbackError``.

    A callback that returns an awaitable cannot be awaited here: it is closed
    and reported as an error instead of being left to warn at garbage collection.
    """
    results: list[Any] = []
    for entry in registrations(phase):
        try:
            result = entry.func(*args, **kwargs)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError(f"{phase} callbacks must be synchronous")
        except Exception as exc:  # noqa: BLE001 - one plugin must not break the rest
            result = CallbackError(phase, entry.owner, exc, entry.fail_closed)
        results.append(result)
    return results


async def fire(phase: PhaseType, *args: object, **kwargs: object) -> list[Any]:
    """Call every callback of ``phase``, awaiting the asynchronous ones."""
    results: list[Any] = []
    for entry in registrations(phase):
        try:
            result = entry.func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - one plugin must not break the rest
            result = CallbackError(phase, entry.owner, exc, entry.fail_closed)
        results.append(result)
    return results
