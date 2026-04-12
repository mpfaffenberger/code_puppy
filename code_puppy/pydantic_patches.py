"""Monkey patches for pydantic-ai.

This module contains all monkey patches needed to customize pydantic-ai behavior.
These patches MUST be applied before any other pydantic-ai imports to work correctly.

Usage:
    from code_puppy.pydantic_patches import apply_all_patches
    apply_all_patches()
"""

import importlib.metadata
from typing import Any


def _get_code_puppy_version() -> str:
    """Get the current code-puppy version."""
    try:
        return importlib.metadata.version("code-puppy")
    except Exception:
        return "0.0.0-dev"


def _import_tool_manager():
    """Import ToolManager from the correct module path.

    pydantic-ai 1.80+ moved ToolManager to the public ``pydantic_ai.tool_manager``
    module. Older versions use the private ``pydantic_ai._tool_manager`` path.
    """
    try:
        from pydantic_ai.tool_manager import ToolManager

        return ToolManager
    except ImportError:
        from pydantic_ai._tool_manager import ToolManager  # type: ignore[no-redef]

        return ToolManager


def patch_user_agent() -> None:
    """Patch pydantic-ai's User-Agent to use Code-Puppy's version.

    pydantic-ai sets its own User-Agent ('pydantic-ai/x.x.x') via a @cache-decorated
    function. We replace it with a dynamic function that returns:
    - 'KimiCLI/0.63' for Kimi models
    - 'Code-Puppy/{version}' for all other models

    This MUST be called before any pydantic-ai models are created.
    """
    try:
        import pydantic_ai.models as pydantic_models

        version = _get_code_puppy_version()

        # Clear cache if already called
        if hasattr(pydantic_models.get_user_agent, "cache_clear"):
            pydantic_models.get_user_agent.cache_clear()

        def _get_dynamic_user_agent() -> str:
            """Return User-Agent based on current model selection."""
            try:
                from code_puppy.config import get_global_model_name

                model_name = get_global_model_name()
                if model_name and "kimi" in model_name.lower():
                    return "KimiCLI/0.63"
            except Exception:
                pass
            return f"Code-Puppy/{version}"

        pydantic_models.get_user_agent = _get_dynamic_user_agent
    except Exception:
        pass  # Don't crash on patch failure


def patch_message_history_cleaning() -> None:
    """Disable overly strict message history cleaning in pydantic-ai."""
    try:
        from pydantic_ai import _agent_graph

        _agent_graph._clean_message_history = lambda messages: messages
    except Exception:
        pass


def patch_process_message_history() -> None:
    """Patch _process_message_history to skip strict ModelRequest validation.

    Pydantic AI added a validation that history must end with ModelRequest,
    but this breaks valid conversation flows. We patch it to skip that validation.
    """
    try:
        from pydantic_ai import _agent_graph

        async def _patched_process_message_history(messages, processors, run_context):
            """Patched version that doesn't enforce ModelRequest at end."""
            from pydantic_ai._agent_graph import (
                _HistoryProcessorAsync,
                _HistoryProcessorSync,
                _HistoryProcessorSyncWithCtx,
                cast,
                exceptions,
                is_async_callable,
                is_takes_ctx,
                run_in_executor,
            )

            for processor in processors:
                takes_ctx = is_takes_ctx(processor)

                if is_async_callable(processor):
                    if takes_ctx:
                        messages = await processor(run_context, messages)
                    else:
                        async_processor = cast(_HistoryProcessorAsync, processor)
                        messages = await async_processor(messages)
                else:
                    if takes_ctx:
                        sync_processor_with_ctx = cast(
                            _HistoryProcessorSyncWithCtx, processor
                        )
                        messages = await run_in_executor(
                            sync_processor_with_ctx, run_context, messages
                        )
                    else:
                        sync_processor = cast(_HistoryProcessorSync, processor)
                        messages = await run_in_executor(sync_processor, messages)

            if len(messages) == 0:
                raise exceptions.UserError("Processed history cannot be empty.")

            # NOTE: We intentionally skip the "must end with ModelRequest" validation
            # that was added in newer Pydantic AI versions.

            return messages

        _agent_graph._process_message_history = _patched_process_message_history
    except Exception:
        pass


def patch_tool_call_json_repair() -> None:
    """Patch pydantic-ai to auto-repair malformed JSON arguments in tool calls.

    LLMs sometimes produce slightly broken JSON in tool calls (trailing commas,
    missing quotes, etc.). This patch intercepts tool calls and runs json_repair
    on the arguments before validation, preventing unnecessary retries.

    Supports pydantic-ai >=1.80 (validate_tool_call) and legacy (_call_tool).
    """
    try:
        import json_repair

        ToolManager = _import_tool_manager()

        # Modern path: patch validate_tool_call to fix args before validation
        _original_validate = getattr(ToolManager, "validate_tool_call", None)
        # Legacy path: patch _call_tool
        _original_call_tool = getattr(ToolManager, "_call_tool", None)

        def _repair_call_args(call: Any) -> None:
            """Repair malformed JSON in call.args in-place."""
            if isinstance(call.args, str) and call.args:
                try:
                    repaired = json_repair.repair_json(call.args)
                    if repaired != call.args:
                        call.args = repaired
                except Exception:
                    pass

        if _original_validate:
            _prev_validate = _original_validate

            async def _patched_validate(self, call, **kwargs):
                _repair_call_args(call)
                return await _prev_validate(self, call, **kwargs)

            ToolManager.validate_tool_call = _patched_validate

        elif _original_call_tool:
            _prev_call_tool = _original_call_tool

            async def _patched_call_tool(
                self,
                call,
                *,
                allow_partial: bool,
                wrap_validation_errors: bool,
                approved: bool,
                metadata: Any = None,
            ):
                _repair_call_args(call)
                return await _prev_call_tool(
                    self,
                    call,
                    allow_partial=allow_partial,
                    wrap_validation_errors=wrap_validation_errors,
                    approved=approved,
                    metadata=metadata,
                )

            ToolManager._call_tool = _patched_call_tool

    except ImportError:
        pass  # json_repair or pydantic_ai not available
    except Exception:
        pass  # Don't crash on patch failure


def patch_tool_call_callbacks() -> None:
    """Patch pydantic-ai tool handling to support callbacks and Claude Code tool names.

    Claude Code OAuth prefixes tool names with ``cp_`` on the wire.  pydantic-ai
    classifies tool calls during ``validate_tool_call``, so unprefixing must
    happen before lookup.  Prefixed tools would otherwise be marked ``unknown``
    and burn through result retries, raising ``UnexpectedModelBehavior``.

    This patch normalizes Claude Code tool names early (during validation) and
    wraps ``execute_tool_call`` so every tool invocation triggers the
    ``pre_tool_call`` and ``post_tool_call`` callbacks defined in
    ``code_puppy.callbacks``.

    Supports pydantic-ai >=1.80 (public ``pydantic_ai.tool_manager``) with
    a fallback to the legacy private ``pydantic_ai._tool_manager`` path.
    """
    import time

    try:
        ToolManager = _import_tool_manager()

        _original_get_tool_def = ToolManager.get_tool_def
        _original_validate_tool_call = getattr(ToolManager, "validate_tool_call", None)
        _original_execute_tool_call = getattr(ToolManager, "execute_tool_call", None)
        # Legacy: pydantic-ai <1.80 used handle_call + _call_tool
        _original_handle_call = getattr(ToolManager, "handle_call", None)
        _original_call_tool = getattr(ToolManager, "_call_tool", None)

        # Tool name prefix used by Claude Code OAuth - tools are prefixed on
        # outgoing requests, so we need to unprefix them when they come back.
        TOOL_PREFIX = "cp_"

        def _normalize_tool_name(name: Any) -> Any:
            """Strip the ``cp_`` prefix if present."""
            if isinstance(name, str) and name.startswith(TOOL_PREFIX):
                return name[len(TOOL_PREFIX) :]
            return name

        def _normalize_call_tool_name(call: Any) -> tuple[Any, Any]:
            """Normalize the tool_name on a call object in-place."""
            tool_name = getattr(call, "tool_name", None)
            normalized_name = _normalize_tool_name(tool_name)
            if normalized_name != tool_name:
                try:
                    call.tool_name = normalized_name
                except (AttributeError, TypeError):
                    pass
            return normalized_name, call

        def _extract_tool_args(call: Any) -> dict:
            """Extract tool args as a dict for callback contract."""
            args = getattr(call, "args", None)
            if isinstance(args, dict):
                return args
            if isinstance(args, str):
                try:
                    import json

                    return json.loads(args)
                except Exception:
                    return {"raw": args}
            return {}

        async def _fire_pre_tool_call(tool_name, tool_args):
            """Fire pre_tool_call callbacks; return block message or None."""
            from code_puppy import callbacks
            from code_puppy.messaging import emit_warning

            callback_results = await callbacks.on_pre_tool_call(tool_name, tool_args)

            for callback_result in callback_results:
                if (
                    callback_result
                    and isinstance(callback_result, dict)
                    and callback_result.get("blocked")
                ):
                    raw_reason = (
                        callback_result.get("error_message")
                        or callback_result.get("reason")
                        or ""
                    )
                    if "[BLOCKED]" in raw_reason:
                        clean_reason = raw_reason[
                            raw_reason.index("[BLOCKED]") :
                        ].strip()
                    else:
                        clean_reason = (
                            raw_reason.strip() or "Tool execution blocked by hook"
                        )
                    block_msg = (
                        f"\U0001f6ab Hook blocked this tool call: {clean_reason}"
                    )
                    emit_warning(block_msg)
                    return (
                        f"ERROR: {block_msg}\n\nThe hook policy prevented "
                        "this tool from running. Please inform the user "
                        "and do not retry this specific command."
                    )
            return None

        # -- Patch get_tool_def: normalize name before lookup --------------------

        def _patched_get_tool_def(self, name: str):
            return _original_get_tool_def(self, _normalize_tool_name(name))

        ToolManager.get_tool_def = _patched_get_tool_def

        # -- Modern path (pydantic-ai >=1.80): validate_tool_call + execute_tool_call
        if _original_validate_tool_call and _original_execute_tool_call:

            async def _patched_validate_tool_call(self, call, **kwargs):
                _normalize_call_tool_name(call)
                return await _original_validate_tool_call(self, call, **kwargs)

            async def _patched_execute_tool_call(self, validated):
                call = getattr(validated, "call", None)
                tool_name = getattr(call, "tool_name", None) if call else None
                tool_args = _extract_tool_args(call) if call else {}

                # --- pre_tool_call (with blocking support) ---
                try:
                    block_result = await _fire_pre_tool_call(tool_name, tool_args)
                    if block_result is not None:
                        return block_result
                except Exception:
                    pass  # other errors don't block tool execution

                start = time.perf_counter()
                error: Exception | None = None
                result = None
                try:
                    result = await _original_execute_tool_call(self, validated)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    final_result = result if error is None else {"error": str(error)}
                    try:
                        from code_puppy import callbacks

                        await callbacks.on_post_tool_call(
                            tool_name, tool_args, final_result, duration_ms
                        )
                    except Exception:
                        pass  # never block tool execution

            ToolManager.validate_tool_call = _patched_validate_tool_call
            ToolManager.execute_tool_call = _patched_execute_tool_call

        # -- Legacy path (pydantic-ai <1.80): handle_call + _call_tool
        elif _original_handle_call and _original_call_tool:

            async def _patched_handle_call(
                self,
                call,
                allow_partial: bool = False,
                wrap_validation_errors: bool = True,
                *,
                approved: bool = False,
                metadata: Any = None,
            ):
                _normalize_call_tool_name(call)
                return await _original_handle_call(
                    self,
                    call,
                    allow_partial=allow_partial,
                    wrap_validation_errors=wrap_validation_errors,
                    approved=approved,
                    metadata=metadata,
                )

            async def _patched_call_tool(
                self,
                call,
                *,
                allow_partial: bool,
                wrap_validation_errors: bool,
                approved: bool,
                metadata: Any = None,
            ):
                tool_name, call = _normalize_call_tool_name(call)
                tool_args = _extract_tool_args(call)

                # --- pre_tool_call (with blocking support) ---
                try:
                    block_result = await _fire_pre_tool_call(tool_name, tool_args)
                    if block_result is not None:
                        return block_result
                except Exception:
                    pass  # other errors don't block tool execution

                start = time.perf_counter()
                error: Exception | None = None
                result = None
                try:
                    result = await _original_call_tool(
                        self,
                        call,
                        allow_partial=allow_partial,
                        wrap_validation_errors=wrap_validation_errors,
                        approved=approved,
                        metadata=metadata,
                    )
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    final_result = result if error is None else {"error": str(error)}
                    try:
                        from code_puppy import callbacks

                        await callbacks.on_post_tool_call(
                            tool_name, tool_args, final_result, duration_ms
                        )
                    except Exception:
                        pass  # never block tool execution

            ToolManager.handle_call = _patched_handle_call
            ToolManager._call_tool = _patched_call_tool

    except ImportError:
        pass
    except Exception:
        pass


def apply_all_patches() -> None:
    """Apply all pydantic-ai monkey patches.

    Call this at the very top of main.py, before any other imports.
    """
    patch_user_agent()
    patch_message_history_cleaning()
    patch_process_message_history()
    patch_tool_call_json_repair()
    patch_tool_call_callbacks()
