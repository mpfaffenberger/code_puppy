"""Pydantic-ai tool validation and execution patches."""

from __future__ import annotations

import asyncio
import functools
import json
import time
from typing import Any

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
                    repaired = json_repair.repair_json(call.args)
                    if repaired != call.args:
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


def _writeback_tool_args(call: Any, tool_args: dict, mode: str | None) -> None:
    """Persist pre-hook argument mutations into model-visible call history."""
    if mode is None:
        return
    try:
        if mode == "str":
            call.args = json.dumps(tool_args)
        elif mode == "dict":
            call.args = tool_args
    except Exception:
        pass


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


def _tool_args(validated: Any, call: Any) -> tuple[dict, str | None]:
    """Return the execution-backed dict and its model-history writeback mode."""
    if isinstance(validated.validated_args, dict):
        if isinstance(call.args, dict):
            mode = "dict"
        elif isinstance(call.args, str):
            mode = "str"
        else:
            mode = None
        return validated.validated_args, mode
    if isinstance(call.args, dict):
        return call.args, "dict"
    if isinstance(call.args, str):
        try:
            value = json.loads(call.args)
            if isinstance(value, dict):
                return value, "str"
        except Exception:
            pass
        return {"raw": call.args}, None
    return {}, None


def _blocking_reason(callback_results: list[Any]) -> str | None:
    for callback_result in callback_results:
        if not isinstance(callback_result, dict) or not callback_result.get("blocked"):
            continue
        raw_reason = (
            callback_result.get("error_message") or callback_result.get("reason") or ""
        )
        if "[BLOCKED]" in raw_reason:
            return raw_reason[raw_reason.index("[BLOCKED]") :].strip()
        return raw_reason.strip() or "Tool execution blocked by hook"
    return None


def _context_messages(callback_results: list[Any]) -> list[str]:
    messages: list[str] = []
    for callback_result in callback_results:
        if not isinstance(callback_result, dict) or callback_result.get("blocked"):
            continue
        message = callback_result.get("context_message")
        if isinstance(message, str) and message.strip():
            messages.append(message.strip())
    return messages


def patch_tool_call_callbacks() -> bool:
    """Install early name normalization and pre/post/final tool callbacks.

    The public pydantic-ai v2 validation seam classifies tools before execution,
    so Claude Code's ``cp_`` prefix is normalized during lookup and validation.
    Execution hooks then share the already-validated argument dictionary; hook
    mutations therefore affect both the actual tool and model-visible history.
    """
    try:
        from pydantic_ai.tool_manager import ToolManager

        if getattr(ToolManager.execute_tool_call, _TOOL_CALLBACK_PATCH_MARKER, False):
            return True
        original_execute = ToolManager.execute_tool_call
        original_get_tool_def = ToolManager.get_tool_def
        original_validate = ToolManager.validate_tool_call

        def claude_code_active() -> bool:
            try:
                from code_puppy.config import get_global_model_name

                return (get_global_model_name() or "").startswith("claude-code")
            except Exception:
                return False

        def normalize_name(name: Any) -> Any:
            if (
                isinstance(name, str)
                and name.startswith("cp_")
                and claude_code_active()
            ):
                return name[3:]
            return name

        def normalize_call(call: Any) -> tuple[Any, Any]:
            tool_name = getattr(call, "tool_name", None)
            normalized = normalize_name(tool_name)
            if normalized != tool_name:
                try:
                    call.tool_name = normalized
                except (AttributeError, TypeError):
                    pass
            return normalized, call

        @functools.wraps(original_get_tool_def)
        def patched_get_tool_def(self, name: str):
            return original_get_tool_def(self, normalize_name(name))

        @functools.wraps(original_validate)
        async def patched_validate(self, call, **kwargs):
            normalize_call(call)
            return await original_validate(self, call, **kwargs)

        @functools.wraps(original_execute)
        async def patched_execute(self, validated, **kwargs):
            call = validated.call
            tool_name, call = normalize_call(call)
            tool_args, writeback_mode = _tool_args(validated, call)
            hook_context_messages: list[str] = []

            try:
                from code_puppy import callbacks
                from code_puppy.messaging import emit_warning

                callback_results = await callbacks.on_pre_tool_call(
                    tool_name, tool_args
                )
                hook_context_messages = _context_messages(callback_results)
                reason = _blocking_reason(callback_results)
                if reason is not None:
                    block_message = f" Hook blocked this tool call: {reason}"
                    emit_warning(block_message)
                    return (
                        f"ERROR: {block_message}\n\n"
                        "The hook policy prevented this tool from running. "
                        "Please inform the user and do not retry this specific command."
                    )
            except Exception:
                pass

            _writeback_tool_args(call, tool_args, writeback_mode)
            start = time.perf_counter()
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
                try:
                    from code_puppy import callbacks

                    await callbacks.on_post_tool_call(
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

            try:
                from code_puppy import callbacks

                await callbacks.on_final_tool_result(
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
