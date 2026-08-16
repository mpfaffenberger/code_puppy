"""Monkey patches for third-party libraries.

Historically pydantic-ai focused, this module now collects all runtime
monkey patches code-puppy applies to its dependencies.  Each patch is
idempotent and fails silently if the target library is absent.

Usage:
    from code_puppy.pydantic_patches import apply_all_patches
    apply_all_patches()
"""

import functools
import importlib.metadata
from typing import Any

_JSON_REPAIR_PATCH_MARKER = "__code_puppy_json_repair_patch_v1__"
_TOOL_CALLBACK_PATCH_MARKER = "__code_puppy_tool_callbacks_patch_v2__"


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


def _repair_tool_call_args(call: Any) -> None:
    """Repair string JSON in place before hooks or tool validation inspect it."""
    if not isinstance(call.args, str) or not call.args:
        return
    try:
        import json_repair

        repaired = json_repair.repair_json(call.args)
        if repaired != call.args:
            call.args = repaired
    except Exception:
        pass


def patch_tool_call_json_repair() -> None:
    """Patch pydantic-ai's _call_tool to auto-repair malformed JSON arguments.

    LLMs sometimes produce slightly broken JSON in tool calls (trailing commas,
    missing quotes, etc.). This patch intercepts tool calls and runs json_repair
    on the arguments before validation, preventing unnecessary retries.
    """
    try:
        import json_repair  # noqa: F401  # availability gate for this optional patch
        from pydantic_ai._tool_manager import ToolManager

        if getattr(ToolManager._call_tool, _JSON_REPAIR_PATCH_MARKER, False):
            return
        _original_call_tool = ToolManager._call_tool

        @functools.wraps(_original_call_tool)
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
            _repair_tool_call_args(call)

            # Call the original method
            return await _original_call_tool(
                self,
                call,
                allow_partial=allow_partial,
                wrap_validation_errors=wrap_validation_errors,
                approved=approved,
                metadata=metadata,
            )

        setattr(_patched_call_tool, _JSON_REPAIR_PATCH_MARKER, True)
        ToolManager._call_tool = _patched_call_tool

    except ImportError:
        pass  # json_repair or pydantic_ai not available
    except Exception:
        pass  # Don't crash on patch failure


def _writeback_tool_args(call: Any, tool_args: dict, mode: str | None) -> None:
    """Persist pre_tool_call mutations of ``tool_args`` back onto ``call.args``.

    pydantic-ai's ``ToolCallPart.args`` is usually a JSON *string* (what the
    LLM emitted). The pre_tool_call hook contract gives plugins a *dict* view
    to mutate. Without this writeback, mutations vanish before the real tool
    runs and the model sees nothing changed.

    Args:
        call: The ``ToolCallPart`` (or compatible) whose ``args`` we update.
        tool_args: The dict view that hooks may have mutated.
        mode: ``"str"`` to re-serialize as JSON, ``"dict"`` to assign directly,
              or ``None`` to skip (unparseable input — don't corrupt it).

    Failures are swallowed: writeback must never block tool execution.
    """
    if mode is None:
        return
    try:
        if mode == "str":
            import json

            call.args = json.dumps(tool_args)
        elif mode == "dict":
            call.args = tool_args
    except Exception:
        pass  # never block tool execution on writeback failure


def _compose_hook_result_envelope(
    tool_name: str,
    result: Any,
    hook_context_messages: tuple[str, ...],
) -> dict[str, str]:
    """Serialize result privacy-safely and compose context off the agent loop."""
    from pydantic_ai.messages import ToolReturnPart

    return {
        "hook_context": "\n\n".join(
            f"[hook context]\n{message}" for message in hook_context_messages
        ),
        "tool_result": ToolReturnPart(
            tool_name=tool_name,
            content=result,
        ).model_response_str(),
    }


def patch_tool_call_callbacks() -> None:
    """Patch pydantic-ai tool handling to support callbacks and Claude Code tool names.

    Claude Code OAuth prefixes tool names with ``cp_`` on the wire.  pydantic-ai
    classifies tool calls *before* ``_call_tool`` runs, so unprefixing only in
    ``_call_tool`` is too late: prefixed tools get marked as ``unknown`` and can
    burn through result retries, eventually raising ``UnexpectedModelBehavior``.

    This patch normalizes Claude Code tool names early (during lookup/dispatch)
    and wraps ``_call_tool`` so every successful invocation triggers
    ``pre_tool_call``, then ``post_tool_call`` on the structured result, then
    ``final_tool_result`` after safely composing any hook-context envelope.
    """
    import asyncio
    import time

    try:
        from pydantic_ai._tool_manager import ToolManager

        if getattr(ToolManager._call_tool, _TOOL_CALLBACK_PATCH_MARKER, False):
            return
        _original_call_tool = ToolManager._call_tool
        _original_get_tool_def = ToolManager.get_tool_def
        _original_handle_call = ToolManager.handle_call

        # Strip the cp_ prefix on return only while a claude-code model is active;
        # unconditional stripping would corrupt legit ``cp_`` names from other types.
        TOOL_PREFIX = "cp_"
        # Matches claude_code_oauth's model-name convention (prompt_handler.py).
        _CLAUDE_CODE_MODEL_PREFIX = "claude-code"

        def _is_claude_code_model_active() -> bool:
            """Best-effort check: is the currently selected model a claude-code one?

            Lazy-imported so this patch stays safe to apply before config is
            initialised; any failure means "not claude-code" so we never
            accidentally strip prefixes from non-claude-code tool names.
            """
            try:
                from code_puppy.config import get_global_model_name

                model_name = get_global_model_name() or ""
                return model_name.startswith(_CLAUDE_CODE_MODEL_PREFIX)
            except Exception:
                return False

        def _normalize_tool_name(name: Any) -> Any:
            """Strip the ``cp_`` prefix if present (claude-code models only)."""
            if (
                isinstance(name, str)
                and name.startswith(TOOL_PREFIX)
                and _is_claude_code_model_active()
            ):
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

        # -- Early normalization patches -----------------------------------------
        # Run before classification so prefixed names resolve correctly.

        def _patched_get_tool_def(self, name: str):
            return _original_get_tool_def(self, _normalize_tool_name(name))

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

        # -- _call_tool wrapper with callbacks -----------------------------------

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
            _repair_tool_call_args(call)

            # Normalise args for hooks, but remember the original shape so in-place
            # mutations survive a JSON-string call.args. Mode: "str"/"dict"/None.
            tool_args: dict = {}
            _args_writeback_mode: str | None = None
            if isinstance(call.args, dict):
                tool_args = call.args
                _args_writeback_mode = "dict"
            elif isinstance(call.args, str):
                try:
                    import json

                    tool_args = json.loads(call.args)
                    _args_writeback_mode = "str"
                except Exception:
                    tool_args = {"raw": call.args}
                    # Unparseable: never write back, would corrupt the original.
                    _args_writeback_mode = None

            # Collected outside the try so it survives any callback exception.
            hook_context_messages: list[str] = []

            # --- pre_tool_call (with blocking support) ---
            # Block returns a string result so pydantic-ai sees a clean "BLOCKED: ..."
            # instead of crashing with UnexpectedModelBehavior.
            try:
                from code_puppy import callbacks
                from code_puppy.messaging import emit_warning

                callback_results = await callbacks.on_pre_tool_call(
                    tool_name, tool_args
                )

                # Collect non-blocking hook context messages (e.g. PreToolUse
                # stdout) so the model sees them — otherwise they're lost.
                for callback_result in callback_results:
                    if isinstance(callback_result, dict) and not callback_result.get(
                        "blocked"
                    ):
                        ctx_msg = callback_result.get("context_message")
                        if isinstance(ctx_msg, str) and ctx_msg.strip():
                            hook_context_messages.append(ctx_msg.strip())

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

            # Write pre_tool_call mutations back to call.args so dispatch and
            # history see them. See ``_writeback_tool_args``.
            _writeback_tool_args(call, tool_args, _args_writeback_mode)

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

            # Compose hook context only after ordinary result mutators. Use
            # pydantic-ai's model-facing serializer rather than str(result),
            # which can expose excluded or redacted Pydantic fields. A mutable
            # envelope lets finalizers bound both context and tool output.
            if hook_context_messages:
                try:
                    result = await asyncio.to_thread(
                        _compose_hook_result_envelope,
                        tool_name,
                        result,
                        tuple(hook_context_messages),
                    )
                except Exception:
                    pass  # preserving the structured result is safer than repr()

            try:
                from code_puppy import callbacks

                await callbacks.on_final_tool_result(
                    tool_name, tool_args, result, duration_ms
                )
            except Exception:
                pass  # never block tool execution
            return result

        functools.update_wrapper(_patched_call_tool, _original_call_tool)
        setattr(_patched_call_tool, _TOOL_CALLBACK_PATCH_MARKER, True)
        ToolManager.get_tool_def = _patched_get_tool_def
        ToolManager.handle_call = _patched_handle_call
        ToolManager._call_tool = _patched_call_tool

    except ImportError:
        pass
    except Exception:
        pass


def patch_prompt_toolkit_emoji_width() -> None:
    """Patch prompt_toolkit's character width calculation for emojis.

    Modern terminals render most emojis as 2 cells wide, but wcwidth often
    returns 1 for many emoji codepoints. This causes cursor misalignment.

    This patch:
    1. Returns 0 for variation selectors (zero-width modifiers)
    2. Returns 2 for emoji codepoints (terminals render them wide)
    3. Falls back to wcwidth for non-emoji characters
    """
    try:
        import wcwidth
        from prompt_toolkit import utils as pt_utils

        _original_get_cwidth = pt_utils.get_cwidth

        def _patched_get_cwidth(char: str) -> int:
            """Get character width with better emoji support."""
            code = ord(char)

            # Variation selectors are zero-width
            if 0xFE00 <= code <= 0xFE0F:  # VS1-VS16
                return 0

            # Emoji codepoints - terminals render these as 2 cells wide
            # even when wcwidth says 1
            if (
                0x1F300 <= code <= 0x1F9FF  # Misc Symbols/Pictographs, Emoticons
                or 0x1F600 <= code <= 0x1F64F  # Emoticons
                or 0x1F680 <= code <= 0x1F6FF  # Transport/Map symbols
                or 0x1FA00 <= code <= 0x1FAFF  # Symbols/Pictographs Extended-A
                or 0x2600 <= code <= 0x26FF  # Misc Symbols (☀️, ⚡, etc)
                or 0x2700 <= code <= 0x27BF  # Dingbats (✂️, ✈️, etc)
                or 0x1F1E0 <= code <= 0x1F1FF  # Regional indicators (flags)
            ):
                return 2

            # Use wcwidth for non-emoji
            w = wcwidth.wcwidth(char)
            if w >= 0:
                return w

            return _original_get_cwidth(char)

        pt_utils.get_cwidth = _patched_get_cwidth

    except ImportError:
        pass  # wcwidth or prompt_toolkit not available
    except Exception:
        pass  # Don't crash on patch failure


def patch_termflow_clipboard() -> None:
    """Disable termflow's OSC 52 clipboard hijacking globally.

    termflow's ``RenderFeatures.clipboard`` defaults to ``True``.  When a
    code block finishes rendering, the renderer emits an OSC 52 escape
    sequence (``\x1b]52;c;<base64>\x07``) that modern terminals interpret
    as a silent clipboard-write command — clobbering whatever the user had.

    PR #335 added explicit ``RenderFeatures(clipboard=False)`` at the two
    known instantiation sites, but that's whack-a-mole: any future code path
    (or a new termflow version with changed defaults) reintroduces the bug.

    This patch kills the behaviour at the source by replacing
    ``Renderer._copy_to_clipboard`` with a no-op, so it does not matter
    whether any caller remembers to disable the feature flag.
    """
    try:
        from termflow.render.renderer import Renderer

        Renderer._copy_to_clipboard = lambda self, text: None  # type: ignore[method-assign]
    except ImportError:
        pass  # termflow not available
    except Exception:
        pass  # never crash on patch failure


def _no_pad_render_code_line(_line, highlighted, width, margin, style, pretty_pad=True):
    """Drop-in for ``render_code_line`` minus the ``' ' * padding`` suffix."""
    return f"{margin}{highlighted}"


def patch_termflow_code_padding() -> None:
    """Strip trailing-space padding from termflow code lines (#505).

    termflow's ``render_code_line`` right-pads to render width, but
    termflow doesn't color code backgrounds -- so the padding is pure
    invisible filler that corrupts copy/paste. Must patch both
    ``termflow.render.code`` (the definition) AND
    ``termflow.render.renderer`` (did ``from … import render_code_line``,
    so it holds a stale reference).
    """
    try:
        import termflow.render.code as _termflow_code
        import termflow.render.renderer as _termflow_renderer

        _termflow_code.render_code_line = _no_pad_render_code_line
        _termflow_renderer.render_code_line = _no_pad_render_code_line
    except ImportError:
        pass  # termflow not available
    except Exception:
        pass  # never crash on patch failure


def apply_all_patches() -> None:
    """Apply all monkey patches.

    Call this at the very top of main.py, before any other imports.
    """
    patch_user_agent()
    patch_message_history_cleaning()
    patch_process_message_history()
    patch_tool_call_json_repair()
    patch_tool_call_callbacks()
    patch_prompt_toolkit_emoji_width()
    patch_termflow_clipboard()
    patch_termflow_code_padding()
