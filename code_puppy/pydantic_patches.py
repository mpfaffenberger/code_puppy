"""Monkey patches for third-party libraries.

Historically pydantic-ai focused, this module now collects all runtime
monkey patches code-puppy applies to its dependencies.  Each patch is
idempotent and NEVER raises, but failures are not silent:

- A missing OPTIONAL third-party lib (json_repair, wcwidth, prompt_toolkit,
  termflow) is genuinely fine and only logged at DEBUG level.
- Failure to locate/patch a pydantic-ai (or other patched-lib) internal —
  missing module, missing attribute, changed shape detected at apply time —
  is logged LOUDLY via ``logger.error``, because it means a security or
  correctness layer silently degraded (e.g. tool-call hooks not firing).

Logging uses the stdlib ``logging`` module, NOT ``code_puppy.messaging``:
patches apply at the very top of ``cli_runner`` before the messaging
system is up (see cli_runner.py lines 6-9).

Usage:
    from code_puppy.pydantic_patches import apply_all_patches
    apply_all_patches()
"""

import importlib.metadata
import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)

# Loud failures recorded during the current apply_all_patches() run, so the
# summary line can distinguish real breakage from skipped optional deps.
_LOUD_FAILURES: list[str] = []


def _patch_failed(
    patch_name: str,
    exc: BaseException,
    consequence: str,
    target: str = "pydantic-ai",
) -> bool:
    """Log a loud, actionable error for a patch that failed to apply."""
    _LOUD_FAILURES.append(patch_name)
    logger.error(
        "pydantic_patches: %s FAILED to apply (%s internals changed?): %r — %s",
        patch_name,
        target,
        exc,
        consequence,
    )
    return False


def _optional_lib_missing(patch_name: str, exc: ImportError) -> bool:
    """Quietly skip a patch whose optional third-party dependency is absent."""
    logger.debug(
        "pydantic_patches: %s skipped (optional dependency missing): %r",
        patch_name,
        exc,
    )
    return False


def _get_code_puppy_version() -> str:
    """Get the current code-puppy version."""
    try:
        return importlib.metadata.version("code-puppy")
    except Exception:
        return "0.0.0-dev"


def patch_user_agent() -> bool:
    """Patch pydantic-ai's User-Agent to use Code-Puppy's version.

    pydantic-ai sets its own User-Agent ('pydantic-ai/x.x.x') via a @cache-decorated
    function. We replace it with a dynamic function that returns:
    - 'KimiCLI/0.63' for Kimi models
    - 'Code-Puppy/{version}' for all other models

    This MUST be called before any pydantic-ai models are created.
    """
    try:
        import pydantic_ai.models as pydantic_models

        if not hasattr(pydantic_models, "get_user_agent"):
            raise AttributeError("pydantic_ai.models.get_user_agent not found")

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
        assert pydantic_models.get_user_agent is _get_dynamic_user_agent
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_user_agent",
            exc,
            "the Code-Puppy User-Agent is DISABLED; requests use pydantic-ai's default.",
        )


def patch_message_history_cleaning() -> bool:
    """Disable overly strict message history cleaning in pydantic-ai."""
    try:
        from pydantic_ai import _agent_graph

        if not hasattr(_agent_graph, "_clean_message_history"):
            raise AttributeError(
                "pydantic_ai._agent_graph._clean_message_history not found"
            )

        # v2 signature: _clean_message_history(messages, *, repair_last_response=False)
        _identity = lambda messages, **_kwargs: messages  # noqa: E731
        _agent_graph._clean_message_history = _identity
        assert _agent_graph._clean_message_history is _identity
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_message_history_cleaning",
            exc,
            "strict history cleaning is ACTIVE and may drop valid messages.",
        )


def patch_tool_call_json_repair() -> bool:
    """Patch pydantic-ai's tool-call validation to auto-repair malformed JSON.

    LLMs sometimes produce slightly broken JSON in tool calls (trailing commas,
    missing quotes, etc.). This patch intercepts ``validate_tool_call`` (the
    single validation entry point since pydantic-ai split validation from
    execution in the public ``pydantic_ai.tool_manager`` module) and runs
    json_repair on the raw arguments before validation, preventing
    unnecessary retries.
    """
    try:
        import json_repair
    except ImportError as exc:
        return _optional_lib_missing("patch_tool_call_json_repair", exc)

    try:
        from pydantic_ai.tool_manager import ToolManager

        # Store the original method (resolved at APPLY time so a changed
        # pydantic-ai surface is detected immediately, not on first run).
        _original_validate_tool_call = ToolManager.validate_tool_call

        async def _patched_validate_tool_call(self, call, **kwargs):
            """Repair malformed JSON args before pydantic-ai validates them."""
            # Only attempt repair if args is a string (JSON)
            if isinstance(call.args, str) and call.args:
                try:
                    repaired = json_repair.repair_json(call.args)
                    if repaired != call.args:
                        # Update the call args with repaired JSON
                        call.args = repaired
                except Exception:
                    pass  # If repair fails, let original validation handle it

            return await _original_validate_tool_call(self, call, **kwargs)

        # Apply the patch
        ToolManager.validate_tool_call = _patched_validate_tool_call
        assert ToolManager.validate_tool_call is _patched_validate_tool_call
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_tool_call_json_repair",
            exc,
            "automatic JSON repair of malformed tool-call arguments is DISABLED.",
        )


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


def patch_tool_call_callbacks() -> bool:
    """Patch pydantic-ai tool handling to support callbacks and Claude Code tool names.

    Claude Code OAuth prefixes tool names with ``cp_`` on the wire.  pydantic-ai
    classifies tool calls *before* ``_call_tool`` runs, so unprefixing only in
    ``_call_tool`` is too late: prefixed tools get marked as ``unknown`` and can
    burn through result retries, eventually raising ``UnexpectedModelBehavior``.

    This patch normalizes Claude Code tool names early (during lookup and
    validation, before classification) and wraps ``execute_tool_call`` (the
    single execution entry point since pydantic-ai split validation from
    execution in the public ``pydantic_ai.tool_manager`` module) so every tool
    invocation also triggers the ``pre_tool_call`` and ``post_tool_call``
    callbacks defined in ``code_puppy.callbacks``.

    Why not the v2 ``Hooks`` capability? Evaluated against pydantic-ai
    2.31.0 and rejected:

    - ``cp_`` normalization must run BEFORE tool classification:
      ``ToolManager._resolve_tool`` marks unknown names as unclassified
      before any ``before_tool_validate`` hook fires, so a capability hook
      is structurally too late — exactly the bug this patch fixes.
    - Hook arg-rewrites feed execution only (``validated_args``); they never
      write back to ``call.args``, so mutations would vanish from message
      history (see ``_writeback_tool_args``).
    - Capabilities are per-``Agent`` wiring; this patch is process-global and
      covers every construction site (builder, sub-agents, summarizer,
      plugin-created agents) with one mechanism instead of two.
    """
    import time

    try:
        from pydantic_ai.tool_manager import ToolManager

        _original_execute_tool_call = ToolManager.execute_tool_call
        _original_get_tool_def = ToolManager.get_tool_def
        _original_validate_tool_call = ToolManager.validate_tool_call

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

        async def _patched_validate_tool_call(self, call, **kwargs):
            """Normalize the tool name before pydantic-ai classifies the call."""
            _normalize_call_tool_name(call)
            return await _original_validate_tool_call(self, call, **kwargs)

        # -- execute_tool_call wrapper with callbacks ----------------------------

        async def _patched_execute_tool_call(self, validated, **kwargs):
            call = validated.call
            tool_name, call = _normalize_call_tool_name(call)

            # Give hooks a dict view of the args. Prefer the already-validated
            # dict — execution passes it to the tool, so in-place mutations
            # flow through automatically. Remember the original call.args shape
            # so mutations also land in message history. Mode: "str"/"dict"/None.
            tool_args: dict = {}
            _args_writeback_mode: str | None = None
            if isinstance(validated.validated_args, dict):
                tool_args = validated.validated_args
                if isinstance(call.args, dict):
                    _args_writeback_mode = "dict"
                elif isinstance(call.args, str):
                    _args_writeback_mode = "str"
            elif isinstance(call.args, dict):
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

            # Write pre_tool_call mutations back to call.args so message
            # history sees them (execution itself reads validated.validated_args,
            # which IS ``tool_args`` when validation succeeded).
            _writeback_tool_args(call, tool_args, _args_writeback_mode)

            start = time.perf_counter()
            error: Exception | None = None
            result = None
            try:
                result = await _original_execute_tool_call(self, validated, **kwargs)
                # Prepend collected hook stdout (PreToolUse "additional
                # context") so the model sees it as part of the tool result.
                if hook_context_messages:
                    prefix = (
                        "\n\n".join(
                            f"[hook context]\n{m}" for m in hook_context_messages
                        )
                        + "\n\n"
                    )
                    if isinstance(result, str):
                        result = prefix + result
                    else:
                        result = prefix + str(result)
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

        ToolManager.get_tool_def = _patched_get_tool_def
        ToolManager.validate_tool_call = _patched_validate_tool_call
        ToolManager.execute_tool_call = _patched_execute_tool_call
        assert ToolManager.get_tool_def is _patched_get_tool_def
        assert ToolManager.validate_tool_call is _patched_validate_tool_call
        assert ToolManager.execute_tool_call is _patched_execute_tool_call
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_tool_call_callbacks",
            exc,
            "pre/post tool hooks and hook-blocking are DISABLED.",
        )


def patch_prompt_toolkit_emoji_width() -> bool:
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
    except ImportError as exc:
        return _optional_lib_missing("patch_prompt_toolkit_emoji_width", exc)

    try:
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
        assert pt_utils.get_cwidth is _patched_get_cwidth
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_prompt_toolkit_emoji_width",
            exc,
            "emoji cursor alignment fixes are DISABLED.",
            target="prompt_toolkit",
        )


def patch_termflow_clipboard() -> bool:
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
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_clipboard", exc)

    try:
        if not hasattr(Renderer, "_copy_to_clipboard"):
            raise AttributeError("termflow Renderer._copy_to_clipboard not found")
        Renderer._copy_to_clipboard = lambda self, text: None  # type: ignore[method-assign]
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_clipboard",
            exc,
            "OSC 52 clipboard hijacking is ACTIVE; code blocks may silently "
            "overwrite the user's clipboard.",
            target="termflow",
        )


def _no_pad_render_code_line(_line, highlighted, width, margin, style, pretty_pad=True):
    """Drop-in for ``render_code_line`` minus the ``' ' * padding`` suffix."""
    return f"{margin}{highlighted}"


def patch_termflow_code_padding() -> bool:
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
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_code_padding", exc)

    try:
        if not hasattr(_termflow_code, "render_code_line") or not hasattr(
            _termflow_renderer, "render_code_line"
        ):
            raise AttributeError("termflow render_code_line not found")
        _termflow_code.render_code_line = _no_pad_render_code_line
        _termflow_renderer.render_code_line = _no_pad_render_code_line
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_code_padding",
            exc,
            "code lines keep invisible trailing-space padding (copy/paste corruption).",
            target="termflow",
        )


def patch_silence_anthropic_sampling_warnings() -> bool:
    """Silence pydantic-ai's unsupported-sampling-parameter UserWarning.

    Some Claude models (e.g. Fable 5) reject sampling params like
    ``temperature``; pydantic-ai already drops them before sending, then
    warns on every single request:

        Sampling parameters ['temperature'] are not supported by
        'claude-fable-5'. These settings will be ignored.

    We avoid sending those params in the first place (see
    ``make_model_settings``), so any residual warning is pure console noise
    in the TUI. The filter is scoped to this exact message shape — NOT a
    blanket UserWarning ignore. Module-based scoping is intentionally
    omitted: warnings' module matching keys off the stacklevel-adjusted
    frame and is unreliable here.
    """
    warnings.filterwarnings(
        "ignore",
        message=r"Sampling parameters .* are not supported by .*",
        category=UserWarning,
    )
    return True


_ALL_PATCHES = (
    patch_silence_anthropic_sampling_warnings,
    patch_user_agent,
    patch_message_history_cleaning,
    patch_tool_call_json_repair,
    patch_tool_call_callbacks,
    patch_prompt_toolkit_emoji_width,
    patch_termflow_clipboard,
    patch_termflow_code_padding,
)


def apply_all_patches() -> dict[str, bool]:
    """Apply all monkey patches.

    Call this at the very top of main.py, before any other imports.

    Returns a mapping of patch name -> whether it applied. Never raises:
    failures are logged (loudly for real breakage, quietly for missing
    optional dependencies) and reflected as ``False`` in the result.
    """
    _LOUD_FAILURES.clear()
    results: dict[str, bool] = {}
    for patch in _ALL_PATCHES:
        try:
            results[patch.__name__] = bool(patch())
        except Exception as exc:  # pragma: no cover - patches must not raise
            _LOUD_FAILURES.append(patch.__name__)
            logger.error(
                "pydantic_patches: %s raised unexpectedly: %r", patch.__name__, exc
            )
            results[patch.__name__] = False
    if _LOUD_FAILURES:
        logger.error(
            "pydantic_patches: %d patch(es) FAILED to apply: %s — "
            "behavior may be degraded.",
            len(_LOUD_FAILURES),
            ", ".join(_LOUD_FAILURES),
        )
    return results
