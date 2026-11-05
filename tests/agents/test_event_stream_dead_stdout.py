"""The streaming path survives a dead terminal handle (e.g. Windows Errno 22)."""

import errno
import io
from unittest.mock import MagicMock

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent, RunContext
from pydantic_ai.messages import TextPart, TextPartDelta

from code_puppy.agents.event_stream_handler import (
    event_stream_handler,
    get_streaming_console,
    set_streaming_console,
)
from code_puppy.messaging.safe_console import SafeConsole


class _DeadTty(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self.attempts += 1
        raise OSError(errno.EINVAL, "Invalid argument")

    def flush(self) -> None:
        self.attempts += 1
        raise OSError(errno.EINVAL, "Invalid argument")


@pytest.fixture(autouse=True)
def _reset_streaming_console():
    set_streaming_console(None)
    yield
    set_streaming_console(None)


def test_fallback_console_is_dead_handle_safe():
    assert isinstance(get_streaming_console(), SafeConsole)


@pytest.mark.asyncio
@pytest.mark.parametrize("smooth", [False, True], ids=["plain", "smooth"])
async def test_text_stream_survives_dead_terminal(monkeypatch, smooth):
    monkeypatch.setattr("code_puppy.config.get_smooth_response_stream", lambda: smooth)
    dead = _DeadTty()
    set_streaming_console(SafeConsole(file=dead, force_terminal=True, width=80))

    async def events():
        yield PartStartEvent(index=0, part=TextPart(content=""))
        yield PartDeltaEvent(
            index=0, delta=TextPartDelta(content_delta="hello\nworld\n")
        )
        yield PartEndEvent(index=0, part=TextPart(content="hello\nworld\n"))

    await event_stream_handler(MagicMock(spec=RunContext), events())

    assert dead.attempts == 1
