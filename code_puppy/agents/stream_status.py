"""Run-wide progress, independent of Markdown rendering and visibility."""

import json
from weakref import WeakKeyDictionary, proxy

from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

from code_puppy.i18n import t


_RUN_STATUSES = WeakKeyDictionary()


def get_stream_status(bar, *, reset: bool = False):
    """Keep the total across model requests; part indices remain request-local."""
    if bar is None:
        return StreamStatus(None)
    if reset or bar not in _RUN_STATUSES:
        _RUN_STATUSES[bar] = StreamStatus(proxy(bar))
    status = _RUN_STATUSES[bar]
    status.tools.clear()
    status.working()
    return status


def finish_stream_status(bar) -> None:
    status = _RUN_STATUSES.get(bar)
    if status is not None:
        status.activity = t("stream.activity.idle")
        status.paint()


class StreamStatus:
    """Accumulate characters before estimating tokens (chunk-size independent)."""

    def __init__(self, bar) -> None:
        self.bar = bar
        self.characters = 0
        self.tools: dict[int, str] = {}
        self.activity = t("stream.activity.working")
        self.active_index = None

    def working(self) -> None:
        self.active_index = None
        self.activity = t("stream.activity.working")
        self.paint()

    def paint(self) -> None:
        if self.bar is None:
            return
        tokens = max(1, int(self.characters / 2.5)) if self.characters else 0
        self.bar.set_tool_progress(
            t("stream.progress", count=tokens, activity=self.activity)
        )

    def update(self, event) -> None:
        if self.bar is None:
            return
        if isinstance(event, PartEndEvent):
            if event.index == self.active_index:
                self.working()
            return
        content = ""
        if isinstance(event, PartStartEvent):
            part = event.part
            if isinstance(part, (ThinkingPart, TextPart)):
                content = part.content
                key = "thinking" if isinstance(part, ThinkingPart) else "writing"
                self.activity = t(f"stream.activity.{key}")
            elif isinstance(part, ToolCallPart):
                self.tools[event.index] = part.tool_name or ""
                content = (
                    part.args
                    if isinstance(part.args, str)
                    else (
                        json.dumps(part.args, ensure_ascii=False) if part.args else ""
                    )
                )
                self._calling(event.index)
            else:
                return
        elif isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, (ThinkingPartDelta, TextPartDelta)):
                content = delta.content_delta or ""
                key = "thinking" if isinstance(delta, ThinkingPartDelta) else "writing"
                self.activity = t(f"stream.activity.{key}")
            elif isinstance(delta, ToolCallPartDelta):
                self.tools[event.index] = self.tools.get(event.index, "") + (
                    delta.tool_name_delta or ""
                )
                content = delta.args_delta or ""
                self._calling(event.index)
            else:
                return
        else:
            return
        self.active_index = event.index
        self.characters += len(content)
        self.paint()

    def _calling(self, index: int) -> None:
        name = self.tools[index]
        self.activity = (
            t("stream.activity.calling", tool=name)
            if name
            else t("stream.activity.tool")
        )
