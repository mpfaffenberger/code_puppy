"""Monkey patches for pydantic-ai used by code-puppy."""

import asyncio
import importlib.metadata
import inspect


def _get_code_puppy_version() -> str:
    try:
        return importlib.metadata.version("code-puppy")
    except Exception:
        return "0.0.0-dev"


def patch_user_agent() -> None:
    try:
        import pydantic_ai.models as pydantic_models
    except Exception:
        return

    version = _get_code_puppy_version()

    try:
        cache_clear = getattr(pydantic_models.get_user_agent, "cache_clear", None)
        if cache_clear:
            cache_clear()
    except Exception:
        pass

    def _get_dynamic_user_agent() -> str:
        try:
            from code_puppy.config import get_global_model_name

            model_name = get_global_model_name()
            if model_name and "kimi" in model_name.lower():
                return "KimiCLI/0.63"
        except Exception:
            pass
        return f"Code-Puppy/{version}"

    pydantic_models.get_user_agent = _get_dynamic_user_agent


def patch_message_history_cleaning() -> None:
    try:
        from pydantic_ai import _agent_graph

        _agent_graph._clean_message_history = lambda messages: messages
    except Exception:
        pass


def patch_process_message_history() -> None:
    try:
        from pydantic_ai import _agent_graph
    except Exception:
        return

    async def _run_sync(func, *args):
        return await asyncio.to_thread(func, *args)

    def _takes_ctx(processor) -> bool:
        try:
            params = [
                p
                for p in inspect.signature(processor).parameters.values()
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            return len(params) >= 2
        except Exception:
            return False

    async def _process_message_history(messages, processors, run_context):
        for processor in processors:
            if inspect.iscoroutinefunction(processor):
                messages = await (
                    processor(run_context, messages)
                    if _takes_ctx(processor)
                    else processor(messages)
                )
            else:
                messages = await (
                    _run_sync(processor, run_context, messages)
                    if _takes_ctx(processor)
                    else _run_sync(processor, messages)
                )
        if not messages:
            raise ValueError("Processed history cannot be empty")
        return messages

    _agent_graph._process_message_history = _process_message_history


def patch_tool_call_json_repair() -> None:
    try:
        from pydantic_ai._tool_manager import ToolManager
    except Exception:
        return

    original = ToolManager._call_tool
    if getattr(original, "_code_puppy_json_repair_patch", False):
        return

    async def _patched_call_tool(
        self, call, *, allow_partial, wrap_validation_errors, approved, metadata=None
    ):
        if isinstance(getattr(call, "args", None), str) and call.args:
            try:
                import json_repair

                repaired = json_repair.repair_json(call.args)
                if repaired:
                    call.args = repaired
            except Exception:
                pass
        return await original(
            self,
            call,
            allow_partial=allow_partial,
            wrap_validation_errors=wrap_validation_errors,
            approved=approved,
            metadata=metadata,
        )

    _patched_call_tool._code_puppy_json_repair_patch = True
    ToolManager._call_tool = _patched_call_tool


def patch_tool_call_callbacks() -> None:
    try:
        from pydantic_ai._tool_manager import ToolManager
    except Exception:
        return

    original_get = ToolManager.get_tool_def
    original_handle = ToolManager.handle_call
    original_call = ToolManager._call_tool

    def _normalize(name):
        if isinstance(name, str) and name.startswith("cp_"):
            return name[3:]
        return name

    def _normalize_call(call):
        tool_name = getattr(call, "tool_name", None)
        normalized = _normalize(tool_name)
        if normalized != tool_name:
            try:
                call.tool_name = normalized
            except Exception:
                pass
        return normalized

    def _patched_get_tool_def(self, name):
        return original_get(self, _normalize(name))

    async def _patched_handle_call(
        self,
        call,
        allow_partial=False,
        wrap_validation_errors=True,
        *,
        approved=False,
        metadata=None,
    ):
        _normalize_call(call)
        return await original_handle(
            self,
            call,
            allow_partial=allow_partial,
            wrap_validation_errors=wrap_validation_errors,
            approved=approved,
            metadata=metadata,
        )

    async def _patched_call_tool(
        self, call, *, allow_partial, wrap_validation_errors, approved, metadata=None
    ):
        _normalize_call(call)
        return await original_call(
            self,
            call,
            allow_partial=allow_partial,
            wrap_validation_errors=wrap_validation_errors,
            approved=approved,
            metadata=metadata,
        )

    ToolManager.get_tool_def = _patched_get_tool_def
    ToolManager.handle_call = _patched_handle_call
    ToolManager._call_tool = _patched_call_tool


def apply_all_patches() -> None:
    patch_user_agent()
    patch_message_history_cleaning()
    patch_process_message_history()
    patch_tool_call_json_repair()
    patch_tool_call_callbacks()
