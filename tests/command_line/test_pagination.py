"""Tests for shared command-line pagination helpers."""

import pytest

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)


def test_get_total_pages_handles_empty_list():
    assert get_total_pages(0, 15) == 1


def test_get_total_pages_rounds_up():
    assert get_total_pages(16, 15) == 2


def test_get_page_bounds_for_middle_page():
    assert get_page_bounds(1, 40, 15) == (15, 30)


def test_get_page_for_index_clamps_negative_index():
    assert get_page_for_index(-5, 15) == 0


def test_ensure_visible_page_keeps_current_page_when_selection_visible():
    assert ensure_visible_page(5, 0, 40, 15) == 0


def test_ensure_visible_page_moves_to_selected_page_when_needed():
    assert ensure_visible_page(18, 0, 40, 15) == 1


@pytest.mark.parametrize(
    "func,args",
    [
        (get_total_pages, (10, 0)),
        (get_page_for_index, (1, 0)),
    ],
)
def test_page_size_must_be_positive(func, args):
    with pytest.raises(ValueError):
        func(*args)
