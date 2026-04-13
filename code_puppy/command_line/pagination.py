"""Shared pagination helpers for command-line TUIs.

These helpers keep page math consistent across menus so selection and
page navigation behave the same way everywhere.
"""

from typing import Tuple


def get_total_pages(total_items: int, page_size: int) -> int:
    """Return the total number of pages for a paginated list."""
    if page_size <= 0:
        raise ValueError("page_size must be greater than 0")
    if total_items <= 0:
        return 1
    return (total_items + page_size - 1) // page_size


def get_page_bounds(page: int, total_items: int, page_size: int) -> Tuple[int, int]:
    """Return the inclusive start and exclusive end index for a page."""
    start = max(0, page) * page_size
    end = min(start + page_size, max(0, total_items))
    return start, end


def get_page_for_index(index: int, page_size: int) -> int:
    """Return the page containing the given absolute index."""
    if page_size <= 0:
        raise ValueError("page_size must be greater than 0")
    return max(0, index) // page_size


def ensure_visible_page(
    selected_index: int,
    current_page: int,
    total_items: int,
    page_size: int,
) -> int:
    """Return the page that keeps the selected item visible."""
    start, end = get_page_bounds(current_page, total_items, page_size)
    if selected_index < start or selected_index >= end:
        return get_page_for_index(selected_index, page_size)
    return current_page
