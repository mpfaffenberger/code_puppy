"""Regression test for the post-tool-call spinner heartbeat.

Screenshot bug: when an ``ask_user_question`` (or any tool) returns and the
agent is about to start its next response, there was a visible gap where
no spinner animated and no banner had been printed yet — the user thought
the agent had stalled.

Fix: the ``PartEndEvent`` handler in ``event_stream_handler`` now calls
``resume_all_spinners()`` unconditionally. The very next banner
(``_print_response_banner`` / ``_print_thinking_banner``) pauses the
spinner again with a 100ms settle delay, so there's no visible flash —
but a long model "thinking" gap now shows the live spinner.

This test locks that contract: the resume must fire on every PartEndEvent,
not be gated on ``next_part_kind``. If a future refactor reintroduces the
old conditional, this test fails.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import PartEndEvent, PartStartEvent
from pydantic_ai.messages import (
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models import RunContext
from rich.console import Console

from code_puppy.agents.event_stream_handler import (
    event_stream_handler,
    set_streaming_console,
)
from code_puppy.messaging.spinner.spinner_base import SpinnerBase


@pytest.fixture(autouse=True)
def _clean_spinner_state():
    SpinnerBase.clear_activity()
    SpinnerBase.set_ledger_active(False)
    SpinnerBase.clear_context_info()
    yield
    SpinnerBase.clear_activity()
    SpinnerBase.set_ledger_active(False)


@pytest.fixture
def mock_ctx():
    return MagicMock(spec=RunContext)


@pytest.fixture
def mock_console():
    return MagicMock(spec=Console, width=120)


def _patch_termflow():
    """No real markdown rendering — stub ``termflow.Parser`` / ``Renderer``."""
    parser = MagicMock()
    parser.parse_line.return_value = []
    parser.finalize.return_value = []
    renderer = MagicMock()

    return (
        patch("termflow.Parser", MagicMock(return_value=parser)),
        patch("termflow.Renderer", MagicMock(return_value=renderer)),
        patch(
            "code_puppy.agents.event_stream_handler.make_smooth_termflow_writer",
            return_value=None,
        ),
        patch(
            "code_puppy.agents.event_stream_handler.make_thinking_smoother",
            return_value=None,
        ),
    )


@pytest.mark.parametrize(
    "next_kind",
    ["tool-call", "text", "thinking", None, "tool_call"],
    ids=[
        "next-tool-call",
        "next-text",
        "next-thinking",
        "end-of-turn",
        "tool-call-underscore",
    ],
)
@pytest.mark.asyncio
async def test_part_end_resumes_spinner_for_every_next_kind(
    mock_ctx, mock_console, next_kind
):
    """The heartbeat must resume regardless of what comes next.

    Previously the handler skipped the resume when ``next_part_kind`` was
    ``text`` / ``thinking`` / ``tool-call`` — leaving a blank gap during
    the model "thinking" time. That gap read as stalled.
    """
    console = mock_console
    set_streaming_console(console)

    tool_part = ToolCallPart(tool_call_id="t1", tool_name="grep", args={})
    start = PartStartEvent(index=0, part=tool_part)
    end = PartEndEvent(index=0, part=tool_part, next_part_kind=next_kind)

    async def stream():
        yield start
        yield end

    with (
        patch(
            "code_puppy.agents.event_stream_handler.resume_all_spinners"
        ) as resume_mock,
        patch(
            "code_puppy.agents.event_stream_handler.get_banner_color",
            return_value="blue",
        ),
    ):
        patches = _patch_termflow()
        for p in patches:
            p.start()
        try:
            await event_stream_handler(mock_ctx, stream())
        finally:
            for p in patches:
                p.stop()

    # The heartbeat: PartEndEvent must unconditionally resume the spinner,
    # so a long model "thinking" gap after the tool returns shows the
    # live indicator instead of a blank screen.
    assert resume_mock.called, (
        "resume_all_spinners() must fire on PartEndEvent for every "
        f"next_part_kind={next_kind!r} — without it the user sees a blank "
        "gap and thinks the agent is stalled."
    )


@pytest.mark.asyncio
async def test_heartbeat_fires_after_multiple_tool_parts(mock_ctx, mock_console):
    """Multi-tool turn — heartbeat must fire after each tool, not just the
    last one, otherwise intermediate gaps still read as stalled."""
    console = mock_console
    set_streaming_console(console)

    parts = []
    for i in range(3):
        tool = ToolCallPart(tool_call_id=f"t{i}", tool_name="grep", args={})
        parts.append(PartStartEvent(index=i, part=tool))
        parts.append(PartEndEvent(index=i, part=tool, next_part_kind="tool-call"))

    async def stream():
        for ev in parts:
            yield ev

    with (
        patch("code_puppy.agents.event_stream_handler.pause_all_spinners"),
        patch(
            "code_puppy.agents.event_stream_handler.resume_all_spinners"
        ) as resume_mock,
        patch(
            "code_puppy.agents.event_stream_handler.get_banner_color",
            return_value="blue",
        ),
    ):
        patches = _patch_termflow()
        for p in patches:
            p.start()
        try:
            await event_stream_handler(mock_ctx, stream())
        finally:
            for p in patches:
                p.stop()

    # Three tool parts → three PartEndEvents → at least three resumes
    # (more is fine — banners pause + resume in some paths).
    assert resume_mock.call_count >= 3


@pytest.mark.asyncio
async def test_text_part_end_also_resumes(mock_ctx, mock_console):
    """Even after a text-only part, the spinner should resume so a
    subsequent long model pause shows the live indicator."""
    console = mock_console
    set_streaming_console(console)

    text_part = TextPart(content="all done")
    start = PartStartEvent(index=0, part=text_part)
    end = PartEndEvent(index=0, part=text_part, next_part_kind=None)

    async def stream():
        yield start
        yield end

    with (
        patch("code_puppy.agents.event_stream_handler.pause_all_spinners"),
        patch(
            "code_puppy.agents.event_stream_handler.resume_all_spinners"
        ) as resume_mock,
        patch(
            "code_puppy.agents.event_stream_handler.get_banner_color",
            return_value="blue",
        ),
    ):
        patches = _patch_termflow()
        for p in patches:
            p.start()
        try:
            await event_stream_handler(mock_ctx, stream())
        finally:
            for p in patches:
                p.stop()

    assert resume_mock.called
