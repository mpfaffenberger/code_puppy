"""Small shared command-line helpers: page math and the command registry."""

from __future__ import annotations

import pytest

from code_puppy.command_line.command_registry import get_all_commands
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_total_pages,
)


@pytest.mark.parametrize(
    "total, size, pages",
    [(0, 10, 1), (-3, 10, 1), (1, 10, 1), (10, 10, 1), (11, 10, 2), (25, 5, 5)],
)
def test_total_pages(total, size, pages):
    assert get_total_pages(total, size) == pages


@pytest.mark.parametrize("size", [0, -1])
def test_total_pages_rejects_non_positive_page_size(size):
    with pytest.raises(ValueError):
        get_total_pages(5, size)


@pytest.mark.parametrize(
    "page, total, bounds",
    [(0, 25, (0, 10)), (2, 25, (20, 25)), (-1, 25, (0, 10)), (0, -5, (0, 0))],
)
def test_page_bounds_are_clamped(page, total, bounds):
    assert get_page_bounds(page, total, 10) == bounds


@pytest.mark.parametrize(
    "selected, current, expected",
    [(5, 0, 0), (15, 0, 1), (3, 2, 0)],  # stay put, jump forward, jump back
)
def test_selection_stays_visible(selected, current, expected):
    assert (
        ensure_visible_page(selected, current, total_items=25, page_size=10) == expected
    )


def test_get_all_commands_returns_a_copy_callers_cannot_corrupt():
    commands = get_all_commands()
    assert commands, "core registers built-in commands at import"
    commands.clear()
    assert get_all_commands()
