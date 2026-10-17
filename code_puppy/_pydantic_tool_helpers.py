"""Small, dependency-light helpers for Code Puppy's pydantic-ai tool patch."""

from __future__ import annotations

from typing import Any

_CLAUDE_CODE_TOOL_PREFIX = "cp_"
_CLAUDE_CODE_MODEL_PREFIX = "claude-code"


def _writeback_tool_args(call: Any, tool_args: dict, mode: str | None) -> None:
    """Persist pre-tool callback argument mutations onto ``call.args``.

    Failures are swallowed because writeback must never block tool execution.
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
        pass


def _tool_args_for_pre_tool_call(call_args: Any) -> tuple[dict, str | None]:
    """Build a best-effort repaired dict view for pre-tool callbacks."""
    if isinstance(call_args, dict):
        return call_args, "dict"
    if not isinstance(call_args, str):
        return {}, None

    try:
        import json
        import json_repair

        parsed = json.loads(json_repair.repair_json(call_args))
        if isinstance(parsed, dict):
            return parsed, "str"
    except Exception:
        pass

    return {"raw": call_args}, None


def _normalize_claude_code_tool_name(tool_manager: Any, name: Any) -> Any:
    """Resolve a wire-prefixed name against this run's actual tool registry."""
    if not isinstance(name, str) or not name.startswith(_CLAUDE_CODE_TOOL_PREFIX):
        return name

    unprefixed = name[len(_CLAUDE_CODE_TOOL_PREFIX) :]
    tools = getattr(tool_manager, "tools", None)
    if isinstance(tools, dict):
        # A real ``cp_*`` tool wins. Otherwise, normalize when the unprefixed
        # name exists in this run — including private agents whose model may
        # differ from the globally selected interactive model.
        if name in tools:
            return name
        if unprefixed in tools:
            return unprefixed

    # Compatibility fallback for the brief window before a ToolManager has a
    # prepared registry. Keep this scoped so unrelated providers can own
    # legitimate ``cp_*`` names.
    try:
        from code_puppy.config import get_global_model_name

        model_name = get_global_model_name() or ""
        if model_name.startswith(_CLAUDE_CODE_MODEL_PREFIX):
            return unprefixed
    except Exception:
        pass
    return name


_GENERIC_BLOCK_REASON = "Tool execution blocked by hook"


def _block_reason(callback_result: dict) -> str:
    """Render a hook's deny reason without ever turning a deny into an allow."""
    try:
        raw = (
            callback_result.get("error_message") or callback_result.get("reason") or ""
        )
        if not isinstance(raw, str):
            raw = str(raw)
        marker = raw.find("[BLOCKED]")
        if marker != -1:
            return raw[marker:].strip() or _GENERIC_BLOCK_REASON
        return raw.strip() or _GENERIC_BLOCK_REASON
    except Exception:
        return _GENERIC_BLOCK_REASON


def _handled_tool_result(callback_result: dict) -> str | None:
    """Return the result a blocking hook supplies in place of the tool's.

    A ``pre_tool_call`` hook that has *handled* the call itself -- e.g. an
    editor client that shows ``ask_user_question`` as its own question UI --
    blocks the tool and passes ``tool_result``: the text the model receives
    as the tool's return value. Anything that is not a non-blank string is
    ignored, so the block falls back to an ordinary deny.
    """
    try:
        value = callback_result.get("tool_result")
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        pass
    return None


def _handled_result_for_blocks(callback_results: list) -> str | None:
    """Return the handled result when every blocking hook supplied one.

    ``None`` means "treat the blocks as an ordinary deny" -- including when
    any one blocking hook gave no ``tool_result``, so a policy deny from one
    hook is never overridden by another hook's handled result.
    """
    blocks = [
        result
        for result in callback_results
        if result and isinstance(result, dict) and result.get("blocked")
    ]
    handled = [_handled_tool_result(block) for block in blocks]
    if blocks and all(handled):
        return handled[0]
    return None


__all__ = [
    "_block_reason",
    "_handled_result_for_blocks",
    "_handled_tool_result",
    "_normalize_claude_code_tool_name",
    "_tool_args_for_pre_tool_call",
    "_writeback_tool_args",
]
