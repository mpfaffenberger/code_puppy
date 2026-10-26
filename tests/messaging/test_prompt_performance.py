"""Structural performance regressions: avoid machine-dependent time limits."""

import pytest

from code_puppy.messaging.bar_rendering import (
    _prompt_visual_rows,
    count_prompt_rows,
    render_prompt_block,
)
from code_puppy.messaging.editor_completion import should_autotrigger


def test_layout_shared_by_count_and_paint_and_bounded_to_latest():
    _prompt_visual_rows.cache_clear()
    text = "large pasted prompt 🐶\n" * 10000
    for _ in range(5):
        count_prompt_rows("> ", text, len(text), 80)
    render_prompt_block("> ", text, len(text), 80, 5)
    info = _prompt_visual_rows.cache_info()
    assert info.misses == 1
    assert info.hits == 5
    assert info.currsize == 1
    # Each input affecting layout must invalidate it.
    for args in [("> ", text, 0, 80), ("> ", text, 0, 40), ("🐶\n", text, 0, 40)]:
        cached = _prompt_visual_rows(*args)
        assert cached == _prompt_visual_rows.__wrapped__(*args)
        assert isinstance(cached[0], tuple)
    assert _prompt_visual_rows.cache_info().currsize == 1
    _prompt_visual_rows.cache_clear()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "hello @file",
        "hello @file  ",
        "  /model",
        "hi\u2003@path",
        "@a next",
        "🐶 @路径",
    ],
)
def test_trigger_matches_previous_semantics_for_each_cursor(text):
    for cursor in range(len(text) + 1):
        words = text[:cursor].split()
        expected = text.lstrip().startswith("/") or bool(words and "@" in words[-1])
        assert should_autotrigger(text, cursor) == expected
