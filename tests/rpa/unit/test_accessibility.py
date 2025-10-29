"""Unit tests for macOS accessibility helpers using heavy mocking.
Covers find_accessible_element and list_accessible_elements with role filters and fuzzy matching.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import code_puppy.tools.rpa.accessibility as acc
from code_puppy.tools.rpa.result_types import ElementSearchResult, ElementListResult


@patch("sys.platform", "darwin")
def test_find_accessible_element_fuzzy(monkeypatch):
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem:
        AXRole = "AXButton"
        AXTitle = "Submit"
        AXDescription = "Submit the form"
        AXPosition = (10, 20)
        AXSize = (100, 50)

    class DummyApp:
        def findAllR(self, **kwargs):
            return [DummyElem(), DummyElem()]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())
    # Patch fuzzy_match to return one element
    def fake_fuzzy_match(search_text, candidates, attribute_names, threshold):
        # Return the first candidate with a score
        return [(candidates[0], 0.9)]
    monkeypatch.setattr(acc, "fuzzy_match", fake_fuzzy_match)
    monkeypatch.setattr(acc, "explain_match", lambda a, b, s: f"{a}~{b} ({s})")

    res: ElementSearchResult = acc.find_accessible_element(role="AXButton", title="submit", fuzzy=True, fuzzy_threshold=0.6)
    assert res.success is True and res.found is True
    assert res.best_match is not None
    assert res.best_match.role == "AXButton"
    assert res.best_match.center_x == 60  # 10 + 100/2


@patch("sys.platform", "darwin")
def test_list_accessible_elements_role(monkeypatch):
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem:
        AXRole = "AXTextField"
        AXTitle = "Username"
        AXDescription = "Enter your username"

    class DummyApp:
        def findAllR(self, **kwargs):
            return [DummyElem(), DummyElem()]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    res: ElementListResult = acc.list_accessible_elements(role="AXTextField")
    assert res.success is True
    assert res.total_elements == 2
    assert "AXTextField" in (res.roles or [])
