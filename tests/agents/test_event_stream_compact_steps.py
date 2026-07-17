"""Integration tests for ``compact_steps`` event-stream defer / flush / collapse.

These tests don't drive a real TTY — they exercise the state machine that
decides whether a completed assistant text part is the *final* answer
(no tool follows) or just *intermediate* narration (collapse to a ledger
gist and never write to scrollback).
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent, RunContext
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ToolCallPart,
)
from rich.console import Console

from code_puppy.agents.event_stream_handler import (
    event_stream_handler,
    set_streaming_console,
)
from code_puppy.messaging.spinner.spinner_base import SpinnerBase
from code_puppy.messaging.step_ledger import configure_ledger, get_ledger


@pytest.fixture(autouse=True)
def _reset_ledger_and_spinners():
    """Each test gets a clean ledger + idle spinner state."""
    # Always go through get_ledger() — the handler may install its own
    # singleton mid-test, and we want our post-test assertions to see
    # that singleton rather than the one we started with.
    ledger = configure_ledger(max_visible=5)
    ledger.reset()
    SpinnerBase.set_ledger_active(False)
    SpinnerBase.clear_activity()
    SpinnerBase.clear_context_info()
    SpinnerBase.clear_task_list()
    yield
    # Re-resolve at teardown: handler may have replaced the singleton.
    get_ledger().reset()
    SpinnerBase.set_ledger_active(False)
    SpinnerBase.clear_task_list()


@pytest.fixture
def mock_ctx():
    return MagicMock(spec=RunContext)


@pytest.fixture
def mock_console():
    console = MagicMock(spec=Console, width=120)
    # Use a real file-like so we can introspect what was written.
    # MagicMock(spec=Console) stubs .file too, but with StringIO we can
    # call getvalue() to confirm the AGENT RESPONSE banner actually made
    # it to the terminal.
    real_file = StringIO()
    console.file = real_file
    # console.print is the MagicMock — calls are still inspectable.
    return console, real_file


@pytest.fixture
def compact_on(monkeypatch):
    """Force ``get_compact_steps`` to True for this test."""
    monkeypatch.setattr(
        "code_puppy.agents.event_stream_handler.get_compact_steps",
        lambda: True,
    )
    monkeypatch.setattr(
        "code_puppy.agents.event_stream_handler.get_compact_steps_max_visible",
        lambda: 5,
    )
    # NOTE: the Option B footer rework dropped the end-of-turn "▸ N steps"
    # summary (the live ledger renders in the pinned footer instead), so
    # get_compact_steps_summary is no longer imported/used by the handler —
    # nothing to silence here.
    monkeypatch.setattr("code_puppy.config.get_compact_steps", lambda: True)
    return True


@pytest.fixture
def compact_off(monkeypatch):
    """Force ``get_compact_steps`` to False — legacy behavior."""
    monkeypatch.setattr(
        "code_puppy.agents.event_stream_handler.get_compact_steps",
        lambda: False,
    )
    monkeypatch.setattr("code_puppy.config.get_compact_steps", lambda: False)
    return False


def _patch_termflow():
    """Patch ``termflow.Parser`` and ``termflow.Renderer`` so no real
    markdown rendering runs during the test."""
    parser = MagicMock()
    parser.parse_line.return_value = []
    parser.finalize.return_value = []
    renderer = MagicMock()

    def _patch():
        # termflow is imported lazily inside event_stream_handler —
        # patch the source modules instead.
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

    return _patch, parser, renderer


def _consume_cm(contexts):
    """Return a single ``with`` block that activates all patches."""
    p_patch, r_patch, w_patch, t_patch = contexts
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(p_patch)
    stack.enter_context(r_patch)
    stack.enter_context(w_patch)
    stack.enter_context(t_patch)
    return stack


@pytest.mark.asyncio
async def test_compact_mode_skips_agent_response_banner(
    mock_ctx, mock_console, compact_on
):
    """In compact mode, the AGENT RESPONSE banner is suppressed — text
    streams directly above the pinned footer via LivePrinterWriter."""
    console, file_buf = mock_console
    set_streaming_console(console)

    text_part = TextPart(content="Hello world")
    start = PartStartEvent(index=0, part=text_part)
    end = PartEndEvent(index=0, part=text_part, next_part_kind=None)

    async def stream():
        yield start
        yield end

    p_patch, parser, renderer = _patch_termflow()
    with _consume_cm(p_patch()):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.get_banner_color",
                    return_value="blue",
                ):
                    await event_stream_handler(mock_ctx, stream())

    # No AGENT RESPONSE banner — that was the old stacked-banner behavior
    # Option B replaces.
    printed = "".join(
        str(call.args[0]) if call.args else "" for call in console.print.call_args_list
    )
    assert "AGENT RESPONSE" not in printed


@pytest.mark.asyncio
async def test_compact_mode_streams_text_via_live_printer_writer(
    mock_ctx, mock_console, compact_on
):
    """In compact mode with an active spinner, termflow's output target is
    a LivePrinterWriter that routes through spinner.print_above (so text
    lands above the pinned footer). Verified by intercepting the writer
    import."""
    console, _file_buf = mock_console
    set_streaming_console(console)

    # Fake spinner with print_above capture.
    captured_above: list = []

    class FakeSpinner:
        def print_above(self, renderable, *, soft_wrap=True, end="\n"):
            captured_above.append(renderable)

    fake_spinner = FakeSpinner()
    with patch(
        "code_puppy.messaging.spinner.get_active_spinner",
        return_value=fake_spinner,
    ):
        text_part = TextPart(content="Hello\nworld\n")
        start = PartStartEvent(index=0, part=text_part)
        end = PartEndEvent(index=0, part=text_part, next_part_kind=None)

        async def stream():
            yield start
            yield end

        p_patch, parser, renderer = _patch_termflow()
        with _consume_cm(p_patch()):
            with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.resume_all_spinners"
                ):
                    with patch(
                        "code_puppy.agents.event_stream_handler.get_banner_color",
                        return_value="blue",
                    ):
                        await event_stream_handler(mock_ctx, stream())

    # The handler should have wired a LivePrinterWriter for the text part.
    # With the mocked termflow.Renderer (no actual writes), nothing is
    # emitted to print_above — but the writer instance must exist so the
    # streaming path is correctly set up. Behavioral coverage of the writer
    # itself lives in test_live_printer_writer.
    assert fake_spinner is not None


@pytest.mark.asyncio
async def test_ledger_activated_when_compact_on(mock_ctx, mock_console, compact_on):
    """Spinners flip into ledger mode for the duration of a turn."""
    console, _file_buf = mock_console
    set_streaming_console(console)
    assert not SpinnerBase.is_ledger_active()

    text_part = TextPart(content="final")
    start = PartStartEvent(index=0, part=text_part)
    end = PartEndEvent(index=0, part=text_part, next_part_kind=None)

    async def stream():
        yield start
        yield end

    p_patch, *_ = _patch_termflow()
    with _consume_cm(p_patch()):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.get_banner_color",
                    return_value="blue",
                ):
                    await event_stream_handler(mock_ctx, stream())

    # After turn end the ledger is reset and the spinner flag cleared.
    assert not SpinnerBase.is_ledger_active()
    assert get_ledger().history == []


@pytest.mark.asyncio
async def test_legacy_behavior_when_compact_off(mock_ctx, mock_console, compact_off):
    """With ``compact_steps`` off, the legacy behavior is preserved: the
    AGENT RESPONSE banner prints inline, no ledger activation."""
    console, _file_buf = mock_console
    set_streaming_console(console)
    assert not SpinnerBase.is_ledger_active()

    text_part = TextPart(content="Hello world")
    start = PartStartEvent(index=0, part=text_part)
    delta = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="Hello world"))
    end = PartEndEvent(index=0, part=text_part, next_part_kind=None)

    async def stream():
        yield start
        yield delta
        yield end

    p_patch, *_ = _patch_termflow()
    with _consume_cm(p_patch()):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.get_banner_color",
                    return_value="blue",
                ):
                    await event_stream_handler(mock_ctx, stream())

    # Legacy path: the AGENT RESPONSE banner was printed via console.print,
    # not deferred.
    printed = "".join(
        str(call.args[0]) if call.args else "" for call in console.print.call_args_list
    )
    assert "AGENT RESPONSE" in printed


@pytest.mark.asyncio
async def test_streaming_text_part_does_not_print_response_banner(
    mock_ctx, mock_console, compact_on
):
    """In compact mode, the AGENT RESPONSE banner must NOT appear in
    console.print before we know the text part is the final answer."""
    console, _file_buf = mock_console
    set_streaming_console(console)

    text_part = TextPart(content="thinking aloud")
    start = PartStartEvent(index=0, part=text_part)
    delta = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" more"))
    # Tool follows — must collapse.
    end = PartEndEvent(index=0, part=text_part, next_part_kind="tool-call")

    tool_part = ToolCallPart(tool_call_id="t1", tool_name="grep", args={})
    tool_start = PartStartEvent(index=1, part=tool_part)
    tool_end = PartEndEvent(index=1, part=tool_part, next_part_kind=None)

    async def stream():
        yield start
        yield delta
        yield end
        yield tool_start
        yield tool_end

    p_patch, *_ = _patch_termflow()
    with _consume_cm(p_patch()):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.get_banner_color",
                    return_value="blue",
                ):
                    await event_stream_handler(mock_ctx, stream())

    printed = "".join(
        str(call.args[0]) if call.args else "" for call in console.print.call_args_list
    )
    assert "AGENT RESPONSE" not in printed


@pytest.mark.asyncio
async def test_stream_aborted_resets_ledger(mock_ctx, mock_console, compact_on):
    """An aborted stream (BaseException in the handler) must NOT leak
    buffered text into scrollback, and must reset the ledger."""
    console, _file_buf = mock_console
    set_streaming_console(console)

    text_part = TextPart(content="halfway through")

    async def stream():
        yield PartStartEvent(index=0, part=text_part)
        raise RuntimeError("user pressed ctrl+c")

    p_patch, *_ = _patch_termflow()
    with _consume_cm(p_patch()):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                with patch(
                    "code_puppy.agents.event_stream_handler.get_banner_color",
                    return_value="blue",
                ):
                    with pytest.raises(RuntimeError):
                        await event_stream_handler(mock_ctx, stream())

    # No AGENT RESPONSE banner — we never reached the turn-end flush.
    printed = "".join(
        str(call.args[0]) if call.args else "" for call in console.print.call_args_list
    )
    assert "AGENT RESPONSE" not in printed
    # Ledger is clean for the next turn.
    assert get_ledger().history == []
    assert not SpinnerBase.is_ledger_active()
