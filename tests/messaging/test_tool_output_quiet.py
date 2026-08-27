"""Tests for TOOL_OUTPUT suppression during speculative CodeMode runs."""

from __future__ import annotations

from code_puppy.agents._code_mode import SilenceToolOutput
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    FileContentMessage,
    MessageCategory,
    MessageLevel,
    TextMessage,
)


def _drain(bus: MessageBus) -> list:
    out = []
    while True:
        try:
            out.append(bus._outgoing.get_nowait())
        except Exception:
            return out


def _bus() -> MessageBus:
    bus = MessageBus()
    bus._has_active_renderer = True
    return bus


def _tool_message() -> FileContentMessage:
    return FileContentMessage(
        path="x.py", content="print(1)", total_lines=1, num_tokens=2
    )


class TestToolOutputQuiet:
    def test_tool_output_dropped_while_quiet(self):
        bus = _bus()
        bus.push_tool_output_quiet()
        bus.emit(_tool_message())
        bus.pop_tool_output_quiet()
        bus.emit(_tool_message())

        assert len(_drain(bus)) == 1

    def test_non_tool_messages_pass_through(self):
        bus = _bus()
        bus.push_tool_output_quiet()
        bus.emit(TextMessage(level=MessageLevel.INFO, text="hello"))

        assert len(_drain(bus)) == 1

    def test_warnings_and_errors_always_pass(self):
        bus = _bus()
        bus.push_tool_output_quiet()
        bus.emit(
            TextMessage(
                level=MessageLevel.WARNING,
                text="careful",
                category=MessageCategory.TOOL_OUTPUT,
            )
        )
        bus.emit(
            TextMessage(
                level=MessageLevel.ERROR,
                text="broken",
                category=MessageCategory.TOOL_OUTPUT,
            )
        )

        assert len(_drain(bus)) == 2

    def test_quiet_nests(self):
        bus = _bus()
        bus.push_tool_output_quiet()
        bus.push_tool_output_quiet()
        bus.pop_tool_output_quiet()
        bus.emit(_tool_message())
        bus.pop_tool_output_quiet()
        bus.emit(_tool_message())

        assert len(_drain(bus)) == 1

    def test_pop_never_goes_negative(self):
        bus = _bus()
        bus.pop_tool_output_quiet()
        bus.push_tool_output_quiet()
        bus.emit(_tool_message())

        assert _drain(bus) == []


class TestSilenceToolOutput:
    async def test_wrap_run_scopes_the_quiet_window(self, monkeypatch):
        bus = _bus()
        monkeypatch.setattr("code_puppy.messaging.get_message_bus", lambda: bus)

        async def handler():
            bus.emit(_tool_message())
            return "result"

        result = await SilenceToolOutput().wrap_run(object(), handler=handler)

        assert result == "result"
        assert _drain(bus) == []
        bus.emit(_tool_message())
        assert len(_drain(bus)) == 1

    async def test_quiet_resets_when_the_run_raises(self, monkeypatch):
        bus = _bus()
        monkeypatch.setattr("code_puppy.messaging.get_message_bus", lambda: bus)

        async def handler():
            raise RuntimeError("boom")

        try:
            await SilenceToolOutput().wrap_run(object(), handler=handler)
        except RuntimeError:
            pass

        bus.emit(_tool_message())
        assert len(_drain(bus)) == 1
