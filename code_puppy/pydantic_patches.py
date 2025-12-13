"""Monkey patches for pydantic-ai.

This module contains all monkey patches needed to customize pydantic-ai behavior.
These patches MUST be applied before any other pydantic-ai imports to work correctly.

Usage:
    from code_puppy.pydantic_patches import apply_all_patches
    apply_all_patches()
"""

import importlib.metadata


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


def apply_all_patches() -> None:
    """Apply all pydantic-ai monkey patches.

    Call this at the very top of main.py, before any other imports.
    """
    patch_user_agent()
    patch_message_history_cleaning()
    patch_process_message_history()
