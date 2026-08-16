"""Pydantic-ai tool validation and execution patches."""

from __future__ import annotations

import asyncio
import copy
import functools
import time
from typing import Any

from pydantic_core import from_json, to_json

from code_puppy.patch_support import optional_lib_missing, patch_failed

_JSON_REPAIR_PATCH_MARKER = "__code_puppy_json_repair_patch_v1__"
_TOOL_CALLBACK_PATCH_MARKER = "__code_puppy_tool_callback_patch_v2__"


def patch_tool_call_json_repair() -> bool:
    """Repair malformed JSON before pydantic-ai validates a tool call."""
    try:
        import json_repair
    except ImportError as exc:
        return optional_lib_missing("patch_tool_call_json_repair", exc)

    try:
        from pydantic_ai.tool_manager import ToolManager

        if getattr(ToolManager.validate_tool_call, _JSON_REPAIR_PATCH_MARKER, False):
            return True
        original = ToolManager.validate_tool_call

        @functools.wraps(original)
        async def patched(self, call, **kwargs):
            if isinstance(call.args, str) and call.args:
                try:
                    from_json(call.args)
                except ValueError:
                    try:
                        repaired = json_repair.repair_json(call.args)
                        parsed = from_json(repaired)
                        if type(parsed) is dict:
                            call.args = repaired
                    except Exception:
                        pass
            return await original(self, call, **kwargs)

        setattr(patched, _JSON_REPAIR_PATCH_MARKER, True)
        ToolManager.validate_tool_call = patched
        assert ToolManager.validate_tool_call is patched
        return True
    except Exception as exc:
        return patch_failed(
            "patch_tool_call_json_repair",
            exc,
            "automatic JSON repair of malformed tool-call arguments is DISABLED.",
        )


def _compose_hook_result_envelope(
    tool_name: str,
    result: Any,
    context_messages: tuple[str, ...],
) -> dict[str, str]:
    """Build a mutable envelope from pydantic-ai's model-facing serialization."""
    from pydantic_ai.messages import ToolReturnPart

    output = ToolReturnPart(
        tool_name=str(tool_name),
        content=result,
        tool_call_id="code-puppy-hook-context",
    ).model_response_str()
    context = "\n\n".join(f"[hook context]\n{message}" for message in context_messages)
    return {"hook_context": context, "tool_result": output}


def _tool_args(
    validated: Any,
    call: Any,
) -> tuple[dict, dict, str | None, bytes]:
    """Isolate hook mutations and snapshot their model-facing JSON form."""
    execution_args = validated.validated_args
    if type(execution_args) is not dict:
        raise TypeError("tool callbacks require a built-in argument dictionary")
    hook_args = copy.deepcopy(execution_args)
    before = to_json(execution_args)
    if isinstance(call.args, dict):
        mode = "dict"
    elif isinstance(call.args, str):
        mode = "str"
    else:
        mode = None
    return execution_args, hook_args, mode, before


def _apply_tool_arg_changes(
    call: Any,
    execution_args: dict,
    hook_args: dict,
    mode: str | None,
    before: bytes,
) -> None:
    """Atomically publish serializable hook mutations to execution and history."""
    after = to_json(hook_args)
    if after == before:
        return
    execution_args.clear()
    execution_args.update(hook_args)
    if mode == "str":
        call.args = after.decode("utf-8")
    elif mode == "dict":
        call.args = dict(hook_args)


def _blocking_reason(callback_results: list[Any]) -> str | None:
    """Latch a block decision without trusting its optional diagnostic fields."""
    for callback_result in callback_results:
        if type(callback_result) is not dict or not callback_result.get("blocked"):
            continue
        raw_reason = callback_result.get("error_message") or callback_result.get(
            "reason"
        )
        if type(raw_reason) is not str:
            return "Tool execution blocked by hook"
        if "[BLOCKED]" in raw_reason:
            return raw_reason[raw_reason.index("[BLOCKED]") :].strip()
        return raw_reason.strip() or "Tool execution blocked by hook"
    return None


def _context_messages(callback_results: list[Any]) -> list[str]:
    messages: list[str] = []
    for callback_result in callback_results:
        if type(callback_result) is not dict or callback_result.get("blocked"):
            continue
        message = callback_result.get("context_message")
        if isinstance(message, str) and message.strip():
            messages.append(message.strip())
    return messages


def patch_tool_call_callbacks() -> bool:
    """Install early name normalization and pre/post/final tool callbacks.

    The public pydantic-ai v2 validation seam classifies tools before execution,
    so Claude Code's ``cp_`` prefix is normalized during lookup and validation.
    Execution hooks receive an isolated copy of validated arguments; serializable
    mutations are then published atomically to execution and model-visible history.
    """
    try:
        from pydantic_ai.tool_manager import ToolManager

        if getattr(ToolManager.execute_tool_call, _TOOL_CALLBACK_PATCH_MARKER, False):
            return True
        original_execute = ToolManager.execute_tool_call
        original_get_tool_def = ToolManager.get_tool_def
        original_validate = ToolManager.validate_tool_call

        def call_uses_claude_code(self, call: Any) -> bool:
            provider_name = getattr(call, "provider_name", None)
            if isinstance(provider_name, str):
                return provider_name == "claude_code"
            try:
                return self.ctx.model.provider.name == "claude_code"
            except Exception:
                return False

        def normalize_call(self, call: Any) -> tuple[Any, Any]:
            tool_name = getattr(call, "tool_name", None)
            if not (
                isinstance(tool_name, str)
                and tool_name.startswith("cp_")
                and call_uses_claude_code(self, call)
            ):
                return tool_name, call
            tools = self.tools or {}
            stripped = tool_name[3:]
            if tool_name in tools or stripped not in tools:
                return tool_name, call
            try:
                call.tool_name = stripped
            except (AttributeError, TypeError):
                return tool_name, call
            return stripped, call

        @functools.wraps(original_get_tool_def)
        def patched_get_tool_def(self, name: str):
            exact = original_get_tool_def(self, name)
            if (
                exact is not None
                or not isinstance(name, str)
                or not name.startswith("cp_")
            ):
                return exact
            return original_get_tool_def(self, name[3:])

        @functools.wraps(original_validate)
        async def patched_validate(self, call, **kwargs):
            normalize_call(self, call)
            return await original_validate(self, call, **kwargs)

        @functools.wraps(original_execute)
        async def patched_execute(self, validated, **kwargs):
            tool = validated.tool
            if (
                self.ctx is None
                or validated.deferral is not None
                or not validated.args_valid
                or tool is None
                or validated.validated_args is None
                or tool.tool_def.kind == "external"
            ):
                return await original_execute(self, validated, **kwargs)

            call = validated.call
            tool_name, call = normalize_call(self, call)
            start = time.perf_counter()
            arg_error: str | None = None
            try:
                execution_args, tool_args, writeback_mode, before = _tool_args(
                    validated, call
                )
            except Exception:
                execution_args = validated.validated_args
                tool_args = dict(execution_args)
                writeback_mode = None
                before = b""
                arg_error = "Tool arguments could not be safely synchronized"

            callback_results: list[Any] = []
            callbacks_api = None
            try:
                from code_puppy import callbacks as callbacks_api

                callback_results = await callbacks_api.on_pre_tool_call(
                    tool_name, tool_args
                )
            except Exception:
                pass

            hook_context_messages = _context_messages(callback_results)
            reason = _blocking_reason(callback_results) or arg_error
            if reason is None:
                try:
                    _apply_tool_arg_changes(
                        call,
                        execution_args,
                        tool_args,
                        writeback_mode,
                        before,
                    )
                except Exception:
                    reason = "Hook produced arguments that cannot be serialized safely"

            if reason is not None:
                block_message = f"Hook blocked this tool call: {reason}"
                try:
                    from code_puppy.messaging import emit_warning

                    emit_warning(block_message)
                except Exception:
                    pass
                try:
                    self.ctx.usage.tool_calls += 1
                    if kwargs.get("wrap_validation_errors", True):
                        self.succeeded_tools.add(call.tool_name)
                except Exception:
                    pass
                duration_ms = (time.perf_counter() - start) * 1000
                blocked_result = {"blocked": True, "error": block_message}
                if callbacks_api is not None:
                    try:
                        await callbacks_api.on_post_tool_call(
                            tool_name,
                            tool_args,
                            blocked_result,
                            duration_ms,
                        )
                    except Exception:
                        pass
                return (
                    f"ERROR: {block_message}\n\n"
                    "The hook policy prevented this tool from running. "
                    "Please inform the user and do not retry this specific command."
                )

            error: BaseException | None = None
            result = None
            try:
                result = await original_execute(self, validated, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                post_result = result if error is None else {"error": str(error)}
                if callbacks_api is not None:
                    try:
                        await callbacks_api.on_post_tool_call(
                            tool_name, tool_args, post_result, duration_ms
                        )
                    except Exception:
                        pass

            if hook_context_messages:
                try:
                    result = await asyncio.to_thread(
                        _compose_hook_result_envelope,
                        tool_name,
                        result,
                        tuple(hook_context_messages),
                    )
                except Exception:
                    pass

            if callbacks_api is not None:
                try:
                    await callbacks_api.on_final_tool_result(
                        tool_name, tool_args, result, duration_ms
                    )
                except Exception:
                    pass
            return result

        setattr(patched_execute, _TOOL_CALLBACK_PATCH_MARKER, True)
        ToolManager.get_tool_def = patched_get_tool_def
        ToolManager.validate_tool_call = patched_validate
        ToolManager.execute_tool_call = patched_execute
        assert ToolManager.get_tool_def is patched_get_tool_def
        assert ToolManager.validate_tool_call is patched_validate
        assert ToolManager.execute_tool_call is patched_execute
        return True
    except Exception as exc:
        return patch_failed(
            "patch_tool_call_callbacks",
            exc,
            "pre/post tool hooks and hook-blocking are DISABLED; final hooks are also DISABLED.",
        )
