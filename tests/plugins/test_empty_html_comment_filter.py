"""Tests for the stateful thinking-display HTML comment filter."""

from __future__ import annotations

import importlib

import io

import pytest
from rich.console import Console


def _plugin_module():
    return importlib.import_module(
        "code_puppy.plugins.empty_html_comment_filter.register_callbacks"
    )


def _stream(chunks: list[str], *, part_index: int = 0) -> str:
    module = _plugin_module()
    stream_id = object()
    output = [
        module._filter_thinking_display(
            chunk, stream_id=stream_id, part_index=part_index
        )
        for chunk in chunks
    ]
    output.append(
        module._filter_thinking_display(
            "", stream_id=stream_id, part_index=part_index, final=True
        )
    )
    return "".join(output)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("<!-- -->", ""),
        ("<!---->", ""),
        ("before<!-- -->after", "beforeafter"),
        ("before\n<!-- -->after", "beforeafter"),
        ("before\n\n<!-- -->after", "before\nafter"),
        ("before\r\n<!-- -->after", "beforeafter"),
        ("before<!--\t\n -->after", "beforeafter"),
        ("<!-- keep this comment -->", "<!-- keep this comment -->"),
        ("plain text", "plain text"),
        ("", ""),
    ],
)
def test_filters_only_whitespace_comments(raw: str, expected: str) -> None:
    assert _stream([raw]) == expected


def test_filters_comment_split_at_every_boundary() -> None:
    text = "before<!-- -->after"
    expected = "beforeafter"

    for boundary in range(len(text) + 1):
        assert _stream([text[:boundary], text[boundary:]]) == expected

    assert _stream(list(text)) == expected


def test_newline_before_split_comment_is_not_emitted_early() -> None:
    text = "before\n<!-- -->after"
    assert _stream(list(text)) == "beforeafter"


def test_ordinary_trailing_newline_is_released_at_end() -> None:
    assert _stream(["ordinary text\n"]) == "ordinary text\n"


def test_newline_is_preserved_when_followed_by_ordinary_text() -> None:
    assert _stream(["first line\n", "second line"]) == "first line\nsecond line"


def test_incomplete_comment_like_text_is_released_at_end() -> None:
    assert _stream(["ordinary <", "!-- unfinished"]) == "ordinary <!-- unfinished"


def test_partial_opening_marker_is_released_at_end() -> None:
    assert _stream(["hello <!"]) == "hello <!"


def test_part_indexes_keep_independent_state() -> None:
    module = _plugin_module()
    stream_id = object()

    first = module._filter_thinking_display("A<!--", stream_id=stream_id, part_index=1)
    second = module._filter_thinking_display("B", stream_id=stream_id, part_index=2)
    first += module._filter_thinking_display(
        " -->C", stream_id=stream_id, part_index=1, final=True
    )
    second += module._filter_thinking_display(
        "", stream_id=stream_id, part_index=2, final=True
    )

    assert first == "AC"
    assert second == "B"


def test_callback_runner_chains_filters_and_ignores_failures() -> None:
    from code_puppy import callbacks

    def uppercase(text: str, **_kwargs) -> str:
        return text.upper()

    def broken(_text: str, **_kwargs) -> str:
        raise RuntimeError("nope")

    callbacks.register_callback("thinking_display_filter", uppercase)
    callbacks.register_callback("thinking_display_filter", broken)
    try:
        result = callbacks.on_thinking_display_filter(
            "hello", stream_id=object(), part_index=0, final=True
        )
    finally:
        callbacks.unregister_callback("thinking_display_filter", uppercase)
        callbacks.unregister_callback("thinking_display_filter", broken)

    assert result == "HELLO"


@pytest.mark.asyncio
@pytest.mark.parametrize("smooth", [False, True])
async def test_event_stream_filters_split_comment_in_both_render_paths(
    monkeypatch, smooth: bool
) -> None:
    from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent
    from pydantic_ai.messages import ThinkingPart, ThinkingPartDelta

    from code_puppy.agents.smooth_stream import ThinkingStreamSmoother

    handler = importlib.import_module("code_puppy.agents.event_stream_handler")

    plugin = _plugin_module()
    from code_puppy import callbacks

    # Test isolation clears global callbacks between tests, so mirror plugin load.
    callbacks.register_callback(
        "thinking_display_filter", plugin._filter_thinking_display
    )
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, no_color=True, width=200)
    monkeypatch.setattr(handler, "get_streaming_console", lambda: console)
    monkeypatch.setattr(handler, "_suppress_thinking_stream", lambda: False)
    monkeypatch.setattr(handler, "erase_progress_line", lambda _console: None)
    if smooth:
        monkeypatch.setattr(
            handler,
            "make_thinking_smoother",
            lambda target: ThinkingStreamSmoother(
                target, tick_interval=0.001, catch_up_seconds=0.005
            ),
        )
    else:
        monkeypatch.setattr(handler, "make_thinking_smoother", lambda _target: None)

    part = ThinkingPart(content="")

    async def events():
        yield PartStartEvent(index=0, part=part)
        for character in "before\n<!-- -->after":
            yield PartDeltaEvent(
                index=0, delta=ThinkingPartDelta(content_delta=character)
            )
        yield PartEndEvent(index=0, part=ThinkingPart(content="before\n<!-- -->after"))

    try:
        await handler.event_stream_handler(None, events())
    finally:
        callbacks.unregister_callback(
            "thinking_display_filter", plugin._filter_thinking_display
        )

    rendered = output.getvalue()
    assert "beforeafter" in rendered
    assert "<!-- -->" not in rendered


def test_final_call_clears_retained_state() -> None:
    module = _plugin_module()
    stream_id = object()
    key = (stream_id, 7)

    module._filter_thinking_display("<!--", stream_id=stream_id, part_index=7)
    assert key in module._pending

    module._filter_thinking_display("", stream_id=stream_id, part_index=7, final=True)
    assert key not in module._pending
