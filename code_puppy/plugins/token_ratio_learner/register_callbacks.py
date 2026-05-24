"""Register callbacks for the token-ratio-learner plugin.

On startup we monkeypatch four things:

1. ``_history.estimate_tokens`` — replaces the hardcoded
   ``max(1, floor(len(text)/2.5))`` with a learned-ratio lookup, falling
   back to ``_DEFAULT_RATIO`` (2.5) which matches the classic heuristic.

2. ``_history.estimate_tokens_for_message`` — replaces per-part char/2.5
   summing + ``model_token_multiplier`` with direct
   ``ratios.count_tokens(part_str, model=model_name)`` per part.  The
   learned ratio is already model-calibrated, so the multiplier becomes
   redundant.

3. ``_runtime.run_with_mcp`` — wraps the orchestration so that after every
   successful agent run we extract ``result.usage().input_tokens`` and
   the character count of the input, then call
   ``ratios._record_token_ratio()`` to update the running average.

4. ``subagent_stream_handler._estimate_tokens`` — same replacement as
   (1) so that subagent streaming token counts use learned ratios.

We do **not** touch ``event_stream_handler`` inlining — that code is for
progress display only, not for compaction decisions.
"""

import logging
from typing import Any, Optional, Union

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# References to originals (set during startup)
# ---------------------------------------------------------------------------

_original_estimate_tokens = None
_original_estimate_tokens_for_message = None
_original_run_with_mcp = None
_original_subagent_estimate_tokens = None


# ---------------------------------------------------------------------------
# Patched ``estimate_tokens`` (root text-level)
# ---------------------------------------------------------------------------


def _patched_estimate_tokens(text: str) -> int:
    """Drop-in replacement that uses learned char/token ratios.

    No model argument — uses the default ratio.  Callers that need
    model-specific calibration go through ``estimate_tokens_for_message``.
    """
    from code_puppy.plugins.token_ratio_learner.ratios import count_tokens

    return count_tokens(text, model=None)


# ---------------------------------------------------------------------------
# Patched ``estimate_tokens_for_message``
# ---------------------------------------------------------------------------


def _patched_estimate_tokens_for_message(
    message: Any,
    model_name: Optional[str] = None,
) -> int:
    """Per-message token estimation using learned model-specific ratios.

    Iterates over ``message.parts``, stringifying each with
    ``stringify_part``, then calls ``ratios.count_tokens(part_str, model)``.
    Bypasses the old ``estimate_tokens`` + ``model_token_multiplier`` chain
    entirely — the learned ratio *is* the calibration.
    """
    # Import stringify_part from the same module the original lives in
    from code_puppy.agents._history import stringify_part
    from code_puppy.plugins.token_ratio_learner.ratios import count_tokens

    total = 0
    for part in getattr(message, "parts", []) or []:
        part_str = stringify_part(part)
        if part_str:
            total += count_tokens(part_str, model=model_name)
    return max(1, total)


# ---------------------------------------------------------------------------
# Patched ``run_with_mcp`` — records token ratios after each API call
# ---------------------------------------------------------------------------


def _compute_input_char_count(
    agent: Any, prompt: Union[str, list], attachments: Any, link_attachments: Any
) -> int:
    """Compute a reasonable character count for the input to the model.

    Counts the prompt text (or list items) plus the stringified message
    history.  Binary/URL attachments aren't tokenized as text so they're
    skipped.
    """
    char_count = 0

    if isinstance(prompt, str):
        char_count += len(prompt)
    elif isinstance(prompt, list):
        for item in prompt:
            if isinstance(item, str):
                char_count += len(item)

    try:
        history = agent._message_history
        from code_puppy.agents._history import stringify_part

        for msg in history:
            for part in getattr(msg, "parts", []) or []:
                part_str = stringify_part(part)
                if part_str:
                    char_count += len(part_str)
    except Exception:
        pass

    return char_count


async def _patched_run_with_mcp(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Any] = None,
    link_attachments: Optional[Any] = None,
    output_type: Optional[Any] = None,
    **kwargs: Any,
) -> Any:
    """Wrap ``run_with_mcp`` to learn token ratios from real API responses."""
    global _original_run_with_mcp

    input_char_count = _compute_input_char_count(
        agent, prompt, attachments, link_attachments
    )

    result = await _original_run_with_mcp(
        agent,
        prompt,
        attachments=attachments,
        link_attachments=link_attachments,
        output_type=output_type,
        **kwargs,
    )

    # Try to extract token usage from the result
    try:
        usage = result.usage()  # AgentRunResult.usage() → RunUsage
        input_tokens = getattr(usage, "input_tokens", 0) or getattr(
            usage, "request_tokens", 0
        )
        if input_tokens > 0 and input_char_count > 0:
            from code_puppy.plugins.token_ratio_learner.ratios import (
                _record_token_ratio,
            )

            model = agent.get_model_name()
            if model:
                _record_token_ratio(model, input_char_count, input_tokens)
    except Exception:
        pass  # Never let ratio recording break the agent run

    return result


# ---------------------------------------------------------------------------
# Patched subagent ``_estimate_tokens``
# ---------------------------------------------------------------------------


def _patched_subagent_estimate_tokens(content: str) -> int:
    """Drop-in replacement for subagent token estimation."""
    from code_puppy.plugins.token_ratio_learner.ratios import count_tokens

    return count_tokens(content, model=None)


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


def _on_startup() -> None:
    """Apply all monkeypatches on startup."""
    global _original_estimate_tokens, _original_estimate_tokens_for_message
    global _original_run_with_mcp, _original_subagent_estimate_tokens

    # 1. Patch _history.estimate_tokens (root text-level)
    from code_puppy.agents import _history

    _original_estimate_tokens = _history.estimate_tokens
    _history.estimate_tokens = _patched_estimate_tokens
    logger.info("token_ratio_learner: patched _history.estimate_tokens")

    # 2. Patch _history.estimate_tokens_for_message
    _original_estimate_tokens_for_message = _history.estimate_tokens_for_message
    _history.estimate_tokens_for_message = _patched_estimate_tokens_for_message
    logger.info("token_ratio_learner: patched _history.estimate_tokens_for_message")

    # 3. Patch _runtime.run_with_mcp
    from code_puppy.agents import _runtime

    _original_run_with_mcp = _runtime.run_with_mcp
    _runtime.run_with_mcp = _patched_run_with_mcp
    logger.info("token_ratio_learner: patched _runtime.run_with_mcp")

    # 4. Patch subagent_stream_handler._estimate_tokens
    # NOTE: ``code_puppy.agents.subagent_stream_handler`` re-exports the
    # *function* ``subagent_stream_handler``, not the module.  We must
    # reach the actual module via ``importlib``.
    import importlib

    ssh_mod = importlib.import_module("code_puppy.agents.subagent_stream_handler")

    _original_subagent_estimate_tokens = ssh_mod._estimate_tokens
    ssh_mod._estimate_tokens = _patched_subagent_estimate_tokens
    logger.info("token_ratio_learner: patched subagent_stream_handler._estimate_tokens")


# Register the startup callback
register_callback("startup", _on_startup)
