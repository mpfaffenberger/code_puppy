"""Fallback rendering for agent runs where streaming didn't emit text.

Some backends buffer responses and never emit SSE text deltas. In that case
``event_stream_handler`` runs the tool/thinking paths but never prints the
final answer, so the user sees a silent agent. This module provides:

* ``StreamingTextDetector`` — a thin wrapper around ``event_stream_handler``
  that records whether a ``TextPart`` / ``TextPartDelta`` ever appeared.
* ``render_result_without_streaming`` — a one-shot renderer that walks
  ``result.all_messages()`` and prints thinking + final text via the
  non-streaming markdown path.

The detector is async-safe and forwards every event untouched; it only
observes. The renderer is best-effort: a render failure must never kill the
run because the caller still has the raw result.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from pydantic_ai import PartDeltaEvent, PartStartEvent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    TextPartDelta,
    ThinkingPart,
)

from code_puppy.tools.display import display_non_streamed_result


class StreamingTextDetector:
    """Wraps an ``event_stream_handler`` and records TextPart activity."""

    def __init__(self, inner: Callable[..., Any]) -> None:
        self._inner = inner
        self.streamed_text: bool = False

    async def __call__(self, ctx: Any, events: Any) -> Any:
        detector = self

        async def _tee() -> Any:
            async for event in events:
                if isinstance(event, PartStartEvent) and isinstance(
                    getattr(event, "part", None), TextPart
                ):
                    part = event.part
                    content = getattr(part, "content", "") or ""
                    if content.strip():
                        detector.streamed_text = True
                elif isinstance(event, PartDeltaEvent) and isinstance(
                    getattr(event, "delta", None), TextPartDelta
                ):
                    delta = event.delta
                    if getattr(delta, "content_delta", ""):
                        detector.streamed_text = True
                yield event

        return await self._inner(ctx, _tee())


def _collect_thinking_from_messages(result: Any) -> str:
    """Concatenate ``ThinkingPart`` content from intermediate ModelResponses.

    "Intermediate" means every ModelResponse except the final one — the final
    response's text is the answer we render separately.
    """
    try:
        messages = list(result.all_messages())
    except Exception:
        return ""

    model_responses = [m for m in messages if isinstance(m, ModelResponse)]
    if len(model_responses) <= 1:
        return ""

    chunks: List[str] = []
    for response in model_responses[:-1]:
        for part in getattr(response, "parts", []) or []:
            if isinstance(part, ThinkingPart):
                content = getattr(part, "content", "") or ""
                if content.strip():
                    chunks.append(content)
    return "\n\n".join(chunks)


def _collect_final_text_from_messages(result: Any) -> str:
    """Concatenate ``TextPart`` content from the final ModelResponse only."""
    try:
        messages = list(result.all_messages())
    except Exception:
        return ""

    for message in reversed(messages):
        if isinstance(message, ModelResponse):
            chunks = [
                getattr(p, "content", "") or ""
                for p in getattr(message, "parts", []) or []
                if isinstance(p, TextPart)
            ]
            return "".join(chunks)
    return ""


def render_result_without_streaming(result: Any) -> None:
    """Render ``result`` via the non-streaming markdown path.

    Emits the thinking banner (if any intermediate thinking was captured) and
    the final agent response. Guarded so a render failure can't kill the run.
    """
    try:
        thinking = _collect_thinking_from_messages(result)
        if thinking.strip():
            display_non_streamed_result(
                thinking,
                banner_text="THINKING",
                banner_name="thinking",
            )

        final_text = _collect_final_text_from_messages(result)
        if final_text.strip():
            display_non_streamed_result(final_text)
    except Exception:
        # Rendering is best-effort: the caller still gets the raw result.
        pass


def should_render_fallback(
    detector: Optional[StreamingTextDetector],
    *,
    skip: bool,
) -> bool:
    """Return True if we should render the final result ourselves.

    ``skip`` is honoured unconditionally (e.g. DBOS renders its own output).
    Otherwise: render if there was no detector (streaming disabled) or the
    detector never saw a TextPart fire.
    """
    if skip:
        return False
    return detector is None or not detector.streamed_text


__all__ = [
    "StreamingTextDetector",
    "render_result_without_streaming",
    "should_render_fallback",
]
