"""Run Code Puppy 0.0.x plugins inside 1.0.

One pydantic-ai-pax plugin that loads every 0.0.x plugin (see
``code_puppy.plugins``) and fires their callbacks at the equivalent 1.0
moments. ``code_puppy.callbacks`` documents which hooks are supported.

Tool hooks see 0.0.x tool names. A guard written as
``if tool_name == "agent_run_shell_command"`` would otherwise never match the
runtime's ``run_command`` and silently stop guarding; ``compat.tools`` holds
the name and argument translation.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import (
    AgentCapability,
    Capability,
    Hooks,
    ValidatedToolArgs,
)
from pydantic_ai.exceptions import SkipToolExecution
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai_pax.commands import Command
from pydantic_ai_pax.plugins import (
    NoSettings,
    Plugin,
    PluginHost,
    SessionEnd,
    SessionStart,
    TurnEnd,
    TurnStart,
)

from code_puppy import callbacks, identity, messaging, plugins
from code_puppy.compat import tools
from code_puppy.plugins import trust

AGENT_NAME = identity.AGENT_NAME
MANAGE_COMMAND = "puppy-plugins"
DEFAULT_BLOCK_REASON = "Blocked by a Code Puppy plugin."


def block_reason(result: object) -> str | None:
    """Why a hook result stops a tool call, or ``None`` when it allows it.

    A crashed callback normally allows the call, as in 0.0.x; one registered
    with ``fail_closed=True`` blocks instead.
    """
    if isinstance(result, callbacks.CallbackError):
        if not result.fail_closed:
            return None
        return (
            f"Blocked: a {result.phase} guard failed ({type(result.error).__name__})."
        )
    if isinstance(result, dict) and result.get("blocked"):
        for key in ("tool_result", "reason", "error_message", "reasoning"):
            if result.get(key):
                return str(result[key])
        return DEFAULT_BLOCK_REASON
    return None


def report_errors(results: Sequence[object]) -> None:
    """Tell the user which plugin's callback raised; never raise in turn."""
    for result in results:
        if isinstance(result, callbacks.CallbackError):
            owner = result.owner or "a 0.0.x plugin"
            error = f"{type(result.error).__name__}: {result.error}"
            messaging.emit_warning(
                f"{owner} failed in its {result.phase} hook: {error}"
            )


class LegacyPlugins(Plugin[NoSettings, Any]):
    """Loads 0.0.x plugins and fires their hooks."""

    scope = "process"

    def __init__(self, host: PluginHost[Any], settings: NoSettings) -> None:
        super().__init__(host, settings)
        messaging.set_console(host.console)
        plugins.load_plugin_callbacks()
        self._started: dict[str, float] = {}

    # --- commands ----------------------------------------------------------

    def get_commands(self) -> Sequence[Command]:
        commands = [
            Command(
                name=MANAGE_COMMAND,
                description="List 0.0.x plugins; trust NAME or revoke NAME for a project plugin",
                handler=self._manage,
            )
        ]
        seen = {MANAGE_COMMAND}
        for name, description in self._advertised_commands():
            if name not in seen:
                seen.add(name)
                commands.append(
                    Command(
                        name=name,
                        description=description,
                        handler=partial(self._run_command, name),
                        raw=True,
                    )
                )
        return commands

    def _advertised_commands(self) -> list[tuple[str, str]]:
        """``(name, description)`` pairs from ``custom_command_help`` callbacks."""
        results = callbacks.fire_sync("custom_command_help")
        report_errors(results)
        found: list[tuple[str, str]] = []
        for result in results:
            if not isinstance(result, (list, tuple)):
                continue
            for entry in result:
                if not (isinstance(entry, (list, tuple)) and len(entry) >= 2):
                    continue
                name = tools.command_name(str(entry[0]))
                if name:
                    found.append((name, str(entry[1])))
        return found

    async def _run_command(self, name: str, args: list[str]) -> str:
        command = f"/{name} {args[0]}".strip() if args else f"/{name}"
        results = await callbacks.fire("custom_command", command, name)
        report_errors(results)
        for result in results:
            if result is True:
                return ""
            if isinstance(result, str) and result:
                # 0.0.x: a string result is sent to the agent as the next prompt.
                self.host.submit_prompt(result)
                return ""
        return f"/{name}: no 0.0.x plugin handled this command."

    def _manage(self, args: list[str]) -> str:
        if not args:
            return self._list_plugins()
        if len(args) == 2 and args[0] in ("trust", "revoke"):
            return self._set_trust(args[0], args[1])
        return f"Usage: /{MANAGE_COMMAND} [trust NAME | revoke NAME]"

    def _list_plugins(self) -> str:
        records = plugins.get_plugin_records()
        if not records:
            return "No 0.0.x plugins found."
        lines = [
            f"{record.tier:<9} {record.name:<28} {record.status}"
            + (f"  ({record.detail})" if record.detail else "")
            for record in records
        ]
        for owner, phases in callbacks.inert_registrations().items():
            lines.append(
                f"{owner} registered hooks 1.0 does not run: {', '.join(phases)}"
            )
        return "\n".join(lines)

    def _set_trust(self, action: str, name: str) -> str:
        root = Path.cwd()
        folder = plugins.get_project_plugins_directory(root)
        path = None if folder is None else folder / name
        if path is None or not (path / f"{plugins.REGISTER_MODULE}.py").is_file():
            return (
                f"No project plugin named {name!r} in {identity.PROJECT_DIR}/plugins."
            )
        if action == "revoke":
            revoked = trust.revoke_plugin(root, name)
            return (
                f"Revoked {name}. It stays loaded until {identity.DISPLAY_NAME} restarts."
                if revoked
                else f"{name} was not trusted."
            )
        if not trust.trust_plugin(root, name, path):
            return f"Could not record trust for {name}."
        loaded = plugins.load_project_plugin_now(name, root)
        return (
            f"Trusted {name}. Run /plugins reload legacy_plugins to pick up its commands and tools."
            if loaded
            else f"Trusted {name}, but it failed to load; see /{MANAGE_COMMAND}."
        )

    # --- the agent run -----------------------------------------------------

    def get_capabilities(self) -> Sequence[AgentCapability[Any]]:
        capabilities: list[AgentCapability[Any]] = []
        if callbacks.count_callbacks("pre_tool_call") or callbacks.count_callbacks(
            "run_shell_command"
        ):
            hooks = Hooks[Any]()
            hooks.on.before_tool_execute(self._before_tool)
            capabilities.append(hooks)
        if callbacks.count_callbacks("post_tool_call"):
            hooks = Hooks[Any]()
            hooks.on.before_tool_execute(self._start_timer)
            hooks.on.after_tool_execute(self._after_tool)
            capabilities.append(hooks)
        prompt = self._legacy_prompt()
        if prompt:
            capabilities.append(Capability(instructions=prompt))
        toolset = tools.legacy_toolset()
        if toolset is not None:
            capabilities.append(toolset)
        return capabilities

    def _legacy_prompt(self) -> str:
        """``load_prompt`` text, read once per plugin load so the prompt stays cacheable."""
        results = callbacks.fire_sync("load_prompt")
        report_errors(results)
        return "\n\n".join(
            r.strip() for r in results if isinstance(r, str) and r.strip()
        )

    async def _before_tool(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
    ) -> ValidatedToolArgs:
        name = tools.legacy_tool_name(call.tool_name)
        legacy_args = tools.legacy_tool_args(call.tool_name, args)
        results = await callbacks.fire("pre_tool_call", name, legacy_args, None)
        report_errors(results)
        for result in results:
            reason = block_reason(result)
            if reason is not None:
                raise SkipToolExecution(reason)
        if call.tool_name not in tools.SHELL_TOOLS or "command" not in args:
            return args
        results = await callbacks.fire(
            "run_shell_command",
            None,
            args["command"],
            cwd=args.get("cwd"),
            timeout=args.get("timeout", 60),
        )
        report_errors(results)
        for result in results:
            reason = block_reason(result)
            if reason is not None:
                raise SkipToolExecution(reason)
            if isinstance(result, dict) and isinstance(result.get("rewrite"), str):
                args = {**args, "command": result["rewrite"]}
        return args

    async def _start_timer(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
    ) -> ValidatedToolArgs:
        self._started[call.tool_call_id] = time.monotonic()
        return args

    async def _after_tool(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        result: object,
    ) -> object:
        started = self._started.pop(call.tool_call_id, None)
        duration_ms = 0.0 if started is None else (time.monotonic() - started) * 1000
        results = await callbacks.fire(
            "post_tool_call",
            tools.legacy_tool_name(call.tool_name),
            tools.legacy_tool_args(call.tool_name, args),
            result,
            duration_ms,
            None,
        )
        report_errors(results)
        return result

    # --- moments -----------------------------------------------------------

    def _model_name(self) -> str:
        return str(getattr(self.host, "default_model_name", "") or "")

    def _session_id(self) -> str | None:
        session_id = getattr(self.host, "session_id", None)
        return session_id if isinstance(session_id, str) else None

    async def on_session_start(self, event: SessionStart) -> None:
        report_errors(await callbacks.fire("startup"))
        for owner, phases in callbacks.inert_registrations().items():
            messaging.emit_system_message(
                f"0.0.x plugin {owner} uses hooks 1.0 does not run: {', '.join(phases)}"
            )

    async def on_session_end(self, event: SessionEnd) -> None:
        report_errors(await callbacks.fire("session_end"))
        report_errors(await callbacks.fire("shutdown"))
        messaging.set_console(None)

    async def on_turn_start(self, event: TurnStart) -> None:
        results = await callbacks.fire(
            "user_prompt_submit", event.text, self._session_id()
        )
        report_errors(results)
        replacement = next((r for r in results if isinstance(r, str) and r), None)
        if replacement is not None:
            event.text = replacement
        report_errors(
            await callbacks.fire(
                "agent_run_start", AGENT_NAME, self._model_name(), self._session_id()
            )
        )

    async def on_turn_end(self, event: TurnEnd) -> None:
        success = event.outcome == "completed"
        output = getattr(event.result, "output", None)
        report_errors(
            await callbacks.fire(
                "agent_run_end",
                AGENT_NAME,
                self._model_name(),
                self._session_id(),
                success=success,
                error=event.error,
                response_text=output if isinstance(output, str) else None,
                metadata=None,
            )
        )
        if event.outcome == "cancelled":
            report_errors(
                await callbacks.fire(
                    "interactive_turn_cancel", event.text, reason="cancelled"
                )
            )
            return
        report_errors(
            await callbacks.fire(
                "interactive_turn_end",
                None,
                event.text,
                event.result,
                success=success,
                error=event.error,
            )
        )
