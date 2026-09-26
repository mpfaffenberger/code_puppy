"""Monkey patches for third-party libraries.

Historically pydantic-ai focused, this module now collects all runtime
monkey patches code-puppy applies to its dependencies.  Each patch is
idempotent and NEVER raises, but failures are not silent:

- A missing OPTIONAL third-party lib (json_repair, wcwidth,
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
import json
import logging
import warnings
from typing import Any

from code_puppy._pydantic_tool_helpers import (
    _block_reason,
    _normalize_claude_code_tool_name,
    _tool_args_for_pre_tool_call,
    _writeback_tool_args,
)

logger = logging.getLogger(__name__)


def _repair_tool_call_json(raw: str) -> str:
    """Repair malformed object JSON without accepting a changed top-level shape."""
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass
    except Exception:
        return raw

    try:
        import json_repair

        repaired = json_repair.repair_json(raw)
        if repaired == raw:
            return raw
        parsed = json.loads(repaired)
        if not isinstance(parsed, dict):
            logger.warning(
                "json_repair changed tool-call JSON shape (dict -> %s); "
                "rejecting repair and leaving original malformed JSON in place",
                type(parsed).__name__,
            )
            return raw
        logger.debug("json_repair modified malformed tool-call JSON arguments")
        return repaired
    except Exception:
        return raw


def _resolve_tool_properties(manager: Any, call: Any) -> dict | None:
    """Best-effort lookup of a tool's declared JSON-Schema properties.

    Returns the ``properties`` mapping, or ``None`` when the tool (or its
    schema) cannot be resolved — callers must treat ``None`` as "unknown".
    Never raises: this runs on the validation hot path.
    """
    try:
        tool_def = manager.get_tool_def(getattr(call, "tool_name", None))
        schema = getattr(tool_def, "parameters_json_schema", None)
        properties = schema.get("properties") if isinstance(schema, dict) else None
        return properties if isinstance(properties, dict) else None
    except Exception:
        return None


def _unwrap_arguments_envelope(tool_args: Any, properties: dict | None) -> Any:
    """Collapse a spurious ``{"arguments": {...}}`` envelope into its payload.

    Some models encode a tool call as the function-call envelope *itself* --
    literally ``{"arguments": {}}`` -- rather than an empty argument object.
    Because pydantic-ai declares every tool schema with
    ``additionalProperties: false``, that stray key hard-fails validation and
    the tool can never be called. Zero-parameter tools (e.g. ``list_agents``)
    are hit hardest: the model has no real parameter to name, so it emits the
    envelope and every call is rejected with ``extra_forbidden``.

    Unwraps ONLY when ``arguments`` is the sole key *and* the tool does not
    declare a real ``arguments`` property, so a legitimate parameter of that
    name is never clobbered. Anything ambiguous is returned untouched.
    """
    if not isinstance(tool_args, dict) or list(tool_args) != ["arguments"]:
        return tool_args
    if isinstance(properties, dict) and "arguments" in properties:
        return tool_args  # a real parameter -- hands off

    inner = tool_args["arguments"]
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except Exception:
            return tool_args
    return inner if isinstance(inner, dict) else tool_args


def _sanitize_tool_call_args(manager: Any, call: Any) -> None:
    """Rewrite ``call.args`` in place if it carries the ``arguments`` envelope.

    ``ToolCallPart.args`` may be a dict or a JSON string, so both shapes are
    handled (and a string is re-serialized to preserve the original shape).
    Invalid JSON strings are left for :func:`_repair_tool_call_json`.
    """
    args = getattr(call, "args", None)
    properties = _resolve_tool_properties(manager, call)

    if isinstance(args, dict):
        unwrapped = _unwrap_arguments_envelope(args, properties)
        if unwrapped is not args:
            call.args = unwrapped
    elif isinstance(args, str) and args:
        try:
            parsed = json.loads(args)
        except Exception:
            return
        if not isinstance(parsed, dict):
            return
        unwrapped = _unwrap_arguments_envelope(parsed, properties)
        if unwrapped is not parsed:
            call.args = json.dumps(unwrapped)


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


def patch_openai_chat_video_url() -> bool:
    """Let OpenAI-compatible Chat Completions endpoints receive video parts.

    pydantic-ai's ``OpenAIChatModel`` raises ``NotImplementedError`` for
    ``VideoUrl`` parts and for ``BinaryContent`` with a ``video/*`` media
    type, because api.openai.com has no video content part in Chat
    Completions.  But several of the OpenAI-compatible endpoints code-puppy
    also talks to (OpenRouter, synthetic.new, self-hosted gateways) DO accept
    the OpenRouter-style ``video_url`` part -- pydantic-ai already emits it
    from ``OpenRouterModel``, so this is a model-class limitation rather than
    a protocol one.  See ``code_puppy._pydantic_video_patch`` for the full
    reasoning.

    This teaches plain ``OpenAIChatModel`` (and subclasses such as code-puppy's
    ``ZaiChatModel``) to emit the same part, gated on
    :func:`_pydantic_video_patch.chat_completions_accepts_video` so that
    first-party OpenAI/Azure keep the original -- and more informative --
    error.  ``OpenRouterModel`` overrides both mappers itself and is therefore
    untouched.
    """
    try:
        from pydantic_ai.models import download_item
        from pydantic_ai.models.openai import OpenAIChatModel

        from code_puppy._pydantic_video_patch import (
            chat_completions_accepts_video,
            inline_video_url,
            video_content_part,
        )

        # Resolved at APPLY time so a changed pydantic-ai surface is detected
        # immediately, not on first video.
        for attr in ("_map_binary_content_item", "_map_video_url_item"):
            if not hasattr(OpenAIChatModel, attr):
                raise AttributeError(f"OpenAIChatModel.{attr} not found")

        _original_map_binary_content_item = OpenAIChatModel._map_binary_content_item
        _original_map_video_url_item = OpenAIChatModel._map_video_url_item

        async def _patched_map_binary_content_item(self, item):
            """Inline a local video as a ``video_url`` part."""
            if item.is_video and chat_completions_accepts_video(self):
                return video_content_part(inline_video_url(item))
            return await _original_map_binary_content_item(self, item)

        async def _patched_map_video_url_item(self, item):
            """Pass a remote video URL through as a ``video_url`` part."""
            if not chat_completions_accepts_video(self):
                return await _original_map_video_url_item(self, item)
            url = item.url
            if item.force_download:
                downloaded = await download_item(
                    item, data_format="base64_uri", type_format="extension"
                )
                url = downloaded["data"]
            return video_content_part(url)

        OpenAIChatModel._map_binary_content_item = _patched_map_binary_content_item
        OpenAIChatModel._map_video_url_item = _patched_map_video_url_item
        assert (
            OpenAIChatModel._map_binary_content_item is _patched_map_binary_content_item
        )
        assert OpenAIChatModel._map_video_url_item is _patched_map_video_url_item
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_openai_chat_video_url",
            exc,
            "attaching a video to a non-first-party chat-completions model raises "
            "NotImplementedError; switch to an OpenRouter model for video.",
        )


def patch_tool_call_json_repair() -> bool:
    """Patch pydantic-ai's tool-call validation to auto-repair malformed JSON.

    LLMs sometimes produce slightly broken JSON in tool calls (trailing commas,
    missing quotes, etc.). This patch intercepts ``validate_tool_call`` (the
    single validation entry point since pydantic-ai split validation from
    execution in the public ``pydantic_ai.tool_manager`` module) and runs
    json_repair on the raw arguments before validation, preventing
    unnecessary retries. Repairs are attempted only after strict parsing fails,
    and are accepted only when they preserve the required object shape.
    """
    try:
        import json_repair  # noqa: F401  (optional-dependency gate)
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
                call.args = _repair_tool_call_json(call.args)

            # Drop a stray {"arguments": ...} envelope (valid JSON, so the
            # repair above never sees it) before strict validation runs.
            _sanitize_tool_call_args(self, call)

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


def patch_tool_call_callbacks() -> bool:
    """Patch pydantic-ai tool handling to support callbacks and Claude Code tool names.

    Claude Code OAuth prefixes tool names with ``cp_`` on the wire.  pydantic-ai
    classifies tool calls *before* ``_call_tool`` runs, so unprefixing only in
    ``_call_tool`` is too late: prefixed tools get marked as ``unknown`` and can
    burn through result retries, eventually raising ``UnexpectedModelBehavior``.

    This patch normalizes Claude Code tool names early (during regular and
    structured-output validation, before classification) and wraps
    ``execute_tool_call`` (the single execution entry point since pydantic-ai
    split validation from execution in the public
    ``pydantic_ai.tool_manager`` module) so every tool invocation also triggers
    the ``pre_tool_call`` and ``post_tool_call`` callbacks defined in
    ``code_puppy.callbacks``.

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
        _original_validate_output_tool_call = ToolManager.validate_output_tool_call
        _original_validate_tool_call = ToolManager.validate_tool_call

        def _normalize_call_tool_name(self: Any, call: Any) -> tuple[Any, Any]:
            """Normalize the tool_name on a call object in-place."""
            tool_name = getattr(call, "tool_name", None)
            normalized_name = _normalize_claude_code_tool_name(self, tool_name)
            if normalized_name != tool_name:
                try:
                    call.tool_name = normalized_name
                except (AttributeError, TypeError):
                    pass
            return normalized_name, call

        # -- Early normalization patches -----------------------------------------
        # Run before classification so prefixed names resolve correctly.

        def _patched_get_tool_def(self, name: str):
            normalized_name = _normalize_claude_code_tool_name(self, name)
            return _original_get_tool_def(self, normalized_name)

        async def _patched_validate_tool_call(self, call, **kwargs):
            """Normalize the tool name before pydantic-ai classifies the call."""
            _normalize_call_tool_name(self, call)
            return await _original_validate_tool_call(self, call, **kwargs)

        async def _patched_validate_output_tool_call(self, call, **kwargs):
            """Normalize names used by structured result output tools."""
            _normalize_call_tool_name(self, call)
            return await _original_validate_output_tool_call(self, call, **kwargs)

        # -- execute_tool_call wrapper with callbacks ----------------------------

        async def _patched_execute_tool_call(self, validated, **kwargs):
            call = validated.call
            tool_name, call = _normalize_call_tool_name(self, call)

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
            else:
                tool_args, _args_writeback_mode = _tool_args_for_pre_tool_call(
                    call.args
                )

            # Collected outside the try so it survives any callback exception.
            hook_context_messages: list[str] = []

            # --- pre_tool_call (with blocking support) ---
            # Block returns a string result so pydantic-ai sees a clean "BLOCKED: ..."
            # instead of crashing with UnexpectedModelBehavior.
            # Dispatching is isolated, but the block decision below is NOT: an
            # error while rendering a deny must not silently become an allow.
            callback_results: list = []
            try:
                from code_puppy import callbacks

                callback_results = await callbacks.on_pre_tool_call(
                    tool_name, tool_args
                )
            except Exception:
                pass  # import/dispatch failure leaves nothing to act on

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
                    block_msg = f"🚫 Hook blocked this tool call: {_block_reason(callback_result)}"
                    try:
                        from code_puppy.messaging import emit_warning

                        emit_warning(block_msg)
                    except Exception:
                        pass  # surfacing the warning is best-effort; the deny stands
                    return f"ERROR: {block_msg}\n\nThe hook policy prevented this tool from running. Please inform the user and do not retry this specific command."

            # Write pre_tool_call mutations back to call.args so message
            # history sees them (execution itself reads validated.validated_args,
            # which IS ``tool_args`` when validation succeeded).
            _writeback_tool_args(call, tool_args, _args_writeback_mode)

            start = time.perf_counter()
            error: Exception | None = None
            result = None
            try:
                from code_puppy.messaging.tool_output import compact_tool_output

                with compact_tool_output(tool_name, tool_args):
                    result = await _original_execute_tool_call(
                        self, validated, **kwargs
                    )
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
        ToolManager.validate_output_tool_call = _patched_validate_output_tool_call
        ToolManager.validate_tool_call = _patched_validate_tool_call
        ToolManager.execute_tool_call = _patched_execute_tool_call
        assert ToolManager.get_tool_def is _patched_get_tool_def
        assert (
            ToolManager.validate_output_tool_call is _patched_validate_output_tool_call
        )
        assert ToolManager.validate_tool_call is _patched_validate_tool_call
        assert ToolManager.execute_tool_call is _patched_execute_tool_call
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_tool_call_callbacks",
            exc,
            "pre/post tool hooks and hook-blocking are DISABLED.",
        )


def patch_termflow_clipboard() -> bool:
    """Disable termflow's OSC 52 clipboard hijacking globally.

    termflow's ``RenderFeatures.clipboard`` defaults to ``True``.  When a
    code block finishes rendering, the renderer emits an OSC 52 escape
    sequence (``\x1b]52;c;<base64>\x07``) that modern terminals interpret
    as a silent clipboard-write command — clobbering whatever the user had.

    PR #335 added explicit ``RenderFeatures(clipboard=False)`` at the two
    known instantiation sites, but that's whack-a-mole: any future code path
    (or a termflow helper like ``render.document``) reintroduces the bug.

    This patch forces ``features.clipboard`` off for every ``Renderer`` right
    after construction. It targets the public flag every termflow version
    checks, not a private helper: 0.10.0 inlined and removed
    ``_copy_to_clipboard``, which silently disarmed the previous no-op patch.
    The caller's ``RenderFeatures`` is copied, never mutated.
    """
    try:
        from dataclasses import replace

        from termflow.render.renderer import Renderer
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_clipboard", exc)

    try:
        original_init = Renderer.__init__
        if getattr(original_init, "_code_puppy_no_clipboard", False):
            return True  # already applied

        def _init_without_clipboard(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.features = replace(self.features, clipboard=False)

        _init_without_clipboard._code_puppy_no_clipboard = True  # type: ignore[attr-defined]
        Renderer.__init__ = _init_without_clipboard  # type: ignore[method-assign]
        # Fail loudly now if termflow ever stops storing a features dataclass.
        if Renderer().features.clipboard:
            raise AttributeError("termflow Renderer.features.clipboard not honored")
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


def _render_table_header_rule(state, margin, style) -> str:
    """Header/body divider using double-line chars (╞═╪═╡), mirroring
    ``termflow.render.table.render_table_separator`` but visually heavier.

    Once every body row also gets a rule (see below), a single-weight rule
    after the header is no longer enough to mark it as different from a body
    row -- bold text alone is an easy-to-miss signal. Same convention as
    Rich's ``box.SQUARE_DOUBLE_HEAD``: double line under the header, single
    lines everywhere else.
    """
    from termflow.ansi import RESET, fg_color

    fg = fg_color(style.symbol)
    parts = ["═" * (w + 2) for w in state.column_widths]
    sep = "╪".join(parts)
    return f"{margin}{fg}╞{sep}╡{RESET}"


def _render_table_complete_with_row_rules(
    header, rows, alignments, width, margin, style
):
    """Drop-in for termflow's ``render_table_complete`` with a rule after every
    row, and a heavier double-line rule marking the header/body boundary.
    """
    from termflow.ansi import visible_length
    from termflow.render.table import (
        TableRenderState,
        render_table_bottom,
        render_table_row,
        render_table_separator,
        render_table_top,
    )

    state = TableRenderState()
    state.update_widths(header)
    for row in rows:
        state.update_widths(row)
    state.set_alignments(alignments)

    margin_width = visible_length(margin)
    state.cap_widths_to_max(margin_width, available_width=width + margin_width)

    lines = [render_table_top(state, margin, style)]
    lines.extend(render_table_row(header, state, width, margin, style, is_header=True))
    lines.append(_render_table_header_rule(state, margin, style))
    state.end_header()

    last_index = len(rows) - 1
    for i, row in enumerate(rows):
        lines.extend(
            render_table_row(row, state, width, margin, style, is_header=False)
        )
        if i != last_index:
            lines.append(render_table_separator(state, margin, style))

    lines.append(render_table_bottom(state, margin, style))
    return lines


def patch_termflow_table_row_separators() -> bool:
    """Draw a rule between every table row, not just after the header.

    termflow's ``render_table_complete`` draws exactly one horizontal rule --
    right after the header -- and none between body rows, which makes wide
    tables hard to scan row-by-row. This replaces it with an otherwise-
    identical version that also draws a rule between consecutive body rows,
    using a double-line rule under the header specifically so it stays
    visually distinct from body-to-body rules.

    Must patch both ``termflow.render.table`` (the definition) AND
    ``termflow.render.renderer`` (did ``from ... import render_table_complete``,
    so it holds a stale reference) -- same reason as ``patch_termflow_code_padding``.
    """
    try:
        import termflow.render.renderer as _termflow_renderer
        import termflow.render.table as _termflow_table
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_table_row_separators", exc)

    try:
        if not hasattr(_termflow_table, "render_table_complete") or not hasattr(
            _termflow_renderer, "render_table_complete"
        ):
            raise AttributeError("termflow render_table_complete not found")
        _termflow_table.render_table_complete = _render_table_complete_with_row_rules
        _termflow_renderer.render_table_complete = _render_table_complete_with_row_rules
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_table_row_separators",
            exc,
            "table rows render without separators between them (header rule only).",
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


def patch_silence_pydantic_serializer_warnings() -> bool:
    """Silence pydantic's "Pydantic serializer warnings" UserWarning.

    pydantic-ai re-validates provider responses by round-tripping them
    through pydantic, e.g. in ``OpenAIChatModel._validate_completion``:

        return _ChatCompletion.model_validate(response.model_dump())

    Some OpenAI-compatible gateways (vLLM-style routers, weight-routing
    proxies) stuff non-string values into the ``ChatCompletion.metadata``
    object -- the OpenAI schema declares it string-valued -- so every model
    request dumps a multi-line warning to the console about data code-puppy
    neither controls nor reads:

        Pydantic serializer warnings:
          PydanticSerializationUnexpectedValue(Expected `str` - serialized
            value may not be as expected [field_name='metadata',
            input_value=[{'version': 'default', 'start': 0, 'end': 57}],
            input_type=list])

    The mismatch is harmless (the odd value is dropped from the draft) and
    the message is pure console noise in the TUI. The filter is scoped to
    pydantic's exact message prefix -- NOT a blanket UserWarning ignore, and
    NOT all pydantic warnings -- so genuine serializer mismatches raised by
    other code still surface. Delete this patch when providers stop emitting
    off-schema metadata.
    """
    warnings.filterwarnings(
        "ignore",
        message=r"Pydantic serializer warnings:",
        category=UserWarning,
    )
    return True


_ALL_PATCHES = (
    patch_silence_anthropic_sampling_warnings,
    patch_silence_pydantic_serializer_warnings,
    patch_user_agent,
    patch_message_history_cleaning,
    patch_openai_chat_video_url,
    patch_tool_call_json_repair,
    patch_tool_call_callbacks,
    patch_termflow_clipboard,
    patch_termflow_code_padding,
    patch_termflow_table_row_separators,
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
