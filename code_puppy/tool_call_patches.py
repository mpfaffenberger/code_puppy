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


def _repair_json_args(call: Any, json_repair: Any) -> None:
    raw_args = call.args
    if type(raw_args) is not str or not raw_args:
        return
    try:
        from_json(raw_args)
        return
    except ValueError:
        pass
    try:
        repaired = json_repair.repair_json(raw_args)
        parsed = from_json(repaired)
        if type(parsed) is dict:
            call.args = repaired
    except Exception:
        pass


def patch_tool_call_json_repair() -> bool:
    """Repair malformed JSON before final regular/output-tool validation."""
    try:
        import json_repair
    except ImportError as exc:
        return optional_lib_missing("patch_tool_call_json_repair", exc)

    try:
        from pydantic_ai.tool_manager import ToolManager

        def make_wrapper(original, *, partial_aware: bool):
            @functools.wraps(original)
            async def patched(self, call, **kwargs):
                if not partial_aware or kwargs.get("allow_partial") is not True:
                    _repair_json_args(call, json_repair)
                return await original(self, call, **kwargs)

            setattr(patched, _JSON_REPAIR_PATCH_MARKER, True)
            return patched

        regular = ToolManager.validate_tool_call
        output = getattr(ToolManager, "validate_output_tool_call", None)
        if not getattr(regular, _JSON_REPAIR_PATCH_MARKER, False):
            regular = make_wrapper(regular, partial_aware=False)
            ToolManager.validate_tool_call = regular
        if output is not None and not getattr(output, _JSON_REPAIR_PATCH_MARKER, False):
            output = make_wrapper(output, partial_aware=True)
            ToolManager.validate_output_tool_call = output
        assert ToolManager.validate_tool_call is regular
        if output is not None:
            assert ToolManager.validate_output_tool_call is output
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


def _tool_args(validated: Any, call: Any) -> tuple[dict, str, bytes]:
    """Isolate hook mutations and snapshot their model-facing JSON form."""
    execution_args = validated.validated_args
    if type(execution_args) is not dict:
        raise TypeError("tool callbacks require a built-in argument dictionary")
    hook_args = copy.deepcopy(execution_args)
    before = to_json(execution_args)
    if type(call.args) is dict:
        mode = "dict"
    elif type(call.args) is str:
        mode = "str"
    elif call.args is None:
        mode = "none"
    else:
        mode = "unsupported"
    return hook_args, mode, before


def _apply_tool_arg_changes(
    validated: Any,
    call: Any,
    hook_args: dict,
    mode: str,
    before: bytes,
) -> None:
    """Atomically publish detached, serializable execution and history values."""
    after = to_json(hook_args)
    if after == before:
        return
    if mode == "unsupported":
        raise TypeError("unsupported model-history argument representation")
    execution_args = copy.deepcopy(hook_args)
    history_args = from_json(after)
    if type(execution_args) is not dict or type(history_args) is not dict:
        raise TypeError("tool argument mutation did not produce a dictionary")
    history_value = after.decode("utf-8") if mode == "str" else history_args
    original_execution = validated.validated_args
    original_history = call.args
    try:
        call.args = history_value
        validated.validated_args = execution_args
    except Exception:
        call.args = original_history
        validated.validated_args = original_execution
        raise


_MISSING = object()


def _exact_dict_get(mapping: Any, name: str) -> Any:
    if type(mapping) is not dict:
        return _MISSING
    for key in dict.__iter__(mapping):
        if type(key) is str and key == name:
            return dict.__getitem__(mapping, key)
    return _MISSING


def _requests_block(callback_result: Any) -> bool:
    value = _exact_dict_get(callback_result, "blocked")
    return value is not _MISSING and value is not False and value is not None


def _blocking_reason(callback_results: list[Any]) -> str | None:
    """Latch a block decision without evaluating callback-owned diagnostics."""
    for callback_result in callback_results:
        if not _requests_block(callback_result):
            continue
        raw_reason = _exact_dict_get(callback_result, "error_message")
        if raw_reason is _MISSING:
            raw_reason = _exact_dict_get(callback_result, "reason")
        if raw_reason is _MISSING:
            raw_reason = None
        if type(raw_reason) is not str:
            return "Tool execution blocked by hook"
        marker_index = str.find(raw_reason, "[BLOCKED]")
        if marker_index >= 0:
            marked = str.strip(raw_reason[marker_index:])
            return marked or "Tool execution blocked by hook"
        return str.strip(raw_reason) or "Tool execution blocked by hook"
    return None


def _context_messages(callback_results: list[Any]) -> list[str]:
    messages: list[str] = []
    for callback_result in callback_results:
        if type(callback_result) is not dict or _requests_block(callback_result):
            continue
        message = _exact_dict_get(callback_result, "context_message")
        if type(message) is str:
            stripped = str.strip(message)
            if stripped:
                messages.append(stripped)
    return messages


def patch_tool_call_callbacks() -> bool:
    """Install early name normalization and pre/post/final tool callbacks.

    Pydantic-ai v2 classifies calls before validation, so its call-aware graph
    seam and both public validation APIs normalize Claude Code's ``cp_`` prefix.
    Execution hooks receive an isolated copy of validated arguments; serializable
    mutations are published as detached execution and model-history snapshots.
    """
    try:
        from pydantic_ai._agent_graph import CallToolsNode
        from pydantic_ai.tool_manager import ToolManager

        original_execute = ToolManager.execute_tool_call
        original_get_tool_def = ToolManager.get_tool_def
        original_output_validate = ToolManager.validate_output_tool_call
        original_validate = ToolManager.validate_tool_call
        original_handle_tool_calls = CallToolsNode._handle_tool_calls
        patch_targets = (
            original_execute,
            original_get_tool_def,
            original_output_validate,
            original_validate,
            original_handle_tool_calls,
        )
        if all(
            getattr(target, _TOOL_CALLBACK_PATCH_MARKER, False)
            for target in patch_targets
        ):
            return True

        def manager_uses_claude_code(self) -> bool:
            try:
                return self.ctx.model.provider.name == "claude_code"
            except Exception:
                return False

        def call_uses_claude_code(self, call: Any) -> bool:
            provider_name = getattr(call, "provider_name", None)
            if type(provider_name) is str:
                return provider_name == "claude_code"
            return manager_uses_claude_code(self)

        def normalize_call(self, call: Any) -> tuple[Any, Any]:
            tool_name = getattr(call, "tool_name", None)
            if not (
                type(tool_name) is str
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
                or type(name) is not str
                or not str.startswith(name, "cp_")
                or not manager_uses_claude_code(self)
            ):
                return exact
            return original_get_tool_def(self, name[3:])

        @functools.wraps(original_validate)
        async def patched_validate(self, call, **kwargs):
            normalize_call(self, call)
            return await original_validate(self, call, **kwargs)

        @functools.wraps(original_output_validate)
        async def patched_output_validate(self, call, **kwargs):
            normalize_call(self, call)
            return await original_output_validate(self, call, **kwargs)

        @functools.wraps(original_handle_tool_calls)
        async def patched_handle_tool_calls(self, ctx, tool_calls, **kwargs):
            manager = ctx.deps.tool_manager
            for call in tool_calls:
                normalize_call(manager, call)
            async for event in original_handle_tool_calls(
                self,
                ctx,
                tool_calls,
                **kwargs,
            ):
                yield event

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
            arg_error: str | None = None
            try:
                tool_args, writeback_mode, before = _tool_args(validated, call)
            except Exception:
                validated_args = validated.validated_args
                tool_args = (
                    dict.copy(validated_args) if type(validated_args) is dict else {}
                )
                writeback_mode = "unsupported"
                before = b""
                arg_error = "Tool arguments could not be safely synchronized"

            callback_results: list[Any] = []
            callbacks_api = None
            try:
                from code_puppy import callbacks as callbacks_api

                callback_results = await callbacks_api.on_pre_tool_call(
                    tool_name, tool_args
                )
                if type(callback_results) is not list:
                    callback_results = []
            except Exception:
                pass

            reason = _blocking_reason(callback_results)
            if reason is None:
                reason = arg_error
            hook_context_messages = (
                _context_messages(callback_results) if reason is None else []
            )
            if reason is None:
                try:
                    _apply_tool_arg_changes(
                        validated,
                        call,
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
                except Exception:
                    pass
                if kwargs.get("wrap_validation_errors", True) is True:
                    try:
                        self.succeeded_tools.add(call.tool_name)
                    except Exception:
                        pass
                duration_ms = 0.0
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
            execution_start = time.perf_counter()
            try:
                result = await original_execute(self, validated, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                duration_ms = (time.perf_counter() - execution_start) * 1000
                if error is None:
                    post_result = result
                else:
                    try:
                        error_message = str(error)
                    except Exception:
                        error_message = type(error).__name__
                    post_result = {"error": error_message}
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

        for patched in (
            patched_execute,
            patched_get_tool_def,
            patched_output_validate,
            patched_validate,
            patched_handle_tool_calls,
        ):
            setattr(patched, _TOOL_CALLBACK_PATCH_MARKER, True)
        ToolManager.get_tool_def = patched_get_tool_def
        ToolManager.validate_tool_call = patched_validate
        ToolManager.validate_output_tool_call = patched_output_validate
        ToolManager.execute_tool_call = patched_execute
        CallToolsNode._handle_tool_calls = patched_handle_tool_calls
        assert ToolManager.get_tool_def is patched_get_tool_def
        assert ToolManager.validate_tool_call is patched_validate
        assert ToolManager.validate_output_tool_call is patched_output_validate
        assert ToolManager.execute_tool_call is patched_execute
        assert CallToolsNode._handle_tool_calls is patched_handle_tool_calls
        return True
    except Exception as exc:
        return patch_failed(
            "patch_tool_call_callbacks",
            exc,
            "pre/post tool hooks and hook-blocking are DISABLED; final hooks are also DISABLED.",
        )
