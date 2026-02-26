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
    """Patch pydantic-ai's _call_tool to auto-repair malformed JSON arguments.

    LLMs sometimes produce slightly broken JSON in tool calls (trailing commas,
    missing quotes, etc.). This patch intercepts tool calls and runs json_repair
    on the arguments before validation, preventing unnecessary retries.
    """
    try:
        import json_repair
        from pydantic_ai._tool_manager import ToolManager

        # Store the original method
        _original_call_tool = ToolManager._call_tool

        async def _patched_call_tool(
            self,
            call,
            *,
            allow_partial: bool,
            wrap_validation_errors: bool,
            approved: bool,
            metadata: Any = None,
        ):
            """Patched _call_tool that repairs malformed JSON before validation."""
            # Only attempt repair if args is a string (JSON)
            if isinstance(call.args, str) and call.args:
                try:
                    repaired = json_repair.repair_json(call.args)
                    if repaired != call.args:
                        # Update the call args with repaired JSON
                        call.args = repaired
                except Exception:
                    pass  # If repair fails, let original validation handle it

            # Call the original method
            return await _original_call_tool(
                self,
                call,
                allow_partial=allow_partial,
                wrap_validation_errors=wrap_validation_errors,
                approved=approved,
                metadata=metadata,
            )

        # Apply the patch
        ToolManager._call_tool = _patched_call_tool

    except ImportError:
        pass  # json_repair or pydantic_ai not available
    except Exception:
        pass  # Don't crash on patch failure


def patch_tool_call_callbacks() -> None:
    """Patch pydantic-ai's _call_tool to fire pre/post tool callbacks.

    This wraps ToolManager._call_tool so that every tool invocation
    automatically triggers the ``pre_tool_call`` and ``post_tool_call``
    callback hooks defined in ``code_puppy.callbacks``, without needing
    to decorate each tool function individually.
    """
    import time

    try:
        from pydantic_ai._tool_manager import ToolManager

        _original_call_tool = ToolManager._call_tool

        async def _patched_call_tool(
            self,
            call,
            *,
            allow_partial: bool,
            wrap_validation_errors: bool,
            approved: bool,
            metadata: Any = None,
        ):
            tool_name = call.tool_name
            # Normalise args to a dict for the callback contract
            tool_args: dict = {}
            if isinstance(call.args, dict):
                tool_args = call.args
            elif isinstance(call.args, str):
                try:
                    import json

                    tool_args = json.loads(call.args)
                except Exception:
                    tool_args = {"raw": call.args}

            # --- pre_tool_call (with blocking support) ---
            # Returns a string tool-result on block so pydantic-ai sees a clean
            # "BLOCKED: ..." message and the agent can react gracefully, without
            # triggering UnexpectedModelBehavior crashes.
            try:
                from code_puppy import callbacks
                from code_puppy.messaging import emit_warning

                callback_results = await callbacks.on_pre_tool_call(
                    tool_name, tool_args
                )

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
                        block_msg = f"🚫 Hook blocked this tool call: {clean_reason}"
                        emit_warning(block_msg)
                        return f"ERROR: {block_msg}\n\nThe hook policy prevented this tool from running. Please inform the user and do not retry this specific command."
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
