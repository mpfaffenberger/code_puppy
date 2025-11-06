"""Unit tests for macOS accessibility helpers using heavy mocking.
Covers find_accessible_element and list_accessible_elements with role filters and fuzzy matching.
"""

from __future__ import annotations

from unittest.mock import patch


import code_puppy.tools.gui_cub.accessibility as acc
from code_puppy.tools.gui_cub.result_types import ElementSearchResult, ElementListResult


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

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="submit", fuzzy=True, fuzzy_threshold=0.6
    )
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


@patch("sys.platform", "darwin")
def test_find_accessible_element_exact_match(monkeypatch):
    """Test finding element with exact matching (no fuzzy)."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem:
        AXRole = "AXButton"
        AXTitle = "Submit"
        AXDescription = "Submit button"
        AXPosition = (50, 100)
        AXSize = (80, 40)

    class DummyApp:
        def findAllR(self, **kwargs):
            return [DummyElem()]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="Submit", fuzzy=False
    )
    assert res.success is True
    assert res.found is True
    assert res.best_match.title == "Submit"


@patch("sys.platform", "linux")
def test_find_accessible_element_not_macos(monkeypatch):
    """Test that accessibility functions fail gracefully on non-macOS."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", False)

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="Submit"
    )
    assert res.success is False
    assert "not available" in res.error.lower() or "macos" in res.error.lower()


@patch("sys.platform", "darwin")
def test_list_accessible_elements_empty(monkeypatch):
    """Test listing elements when none are found."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyApp:
        def findAllR(self, **kwargs):
            return []

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    res: ElementListResult = acc.list_accessible_elements(role="AXButton")
    assert res.success is True
    assert res.total_elements == 0


@patch("sys.platform", "darwin")
def test_find_accessible_element_in_frontmost_app(monkeypatch):
    """Test finding element in frontmost app."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem:
        AXRole = "AXButton"
        AXTitle = "OK"
        AXDescription = "Confirm action"
        AXPosition = (100, 200)
        AXSize = (60, 30)

    class DummyApp:
        def findAllR(self, **kwargs):
            return [DummyElem()]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="OK", fuzzy=False, in_frontmost_app=True
    )
    assert res.success is True
    assert res.found is True
    assert res.best_match.title == "OK"


@patch("sys.platform", "darwin")
def test_find_accessible_element_multiple_matches_fuzzy(monkeypatch):
    """Test fuzzy matching returns best match when multiple candidates exist."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem1:
        AXRole = "AXButton"
        AXTitle = "Submit Form"
        AXDescription = ""
        AXPosition = (10, 20)
        AXSize = (100, 40)

    class DummyElem2:
        AXRole = "AXButton"
        AXTitle = "Submit"
        AXDescription = ""
        AXPosition = (120, 20)
        AXSize = (100, 40)

    class DummyApp:
        def findAllR(self, **kwargs):
            return [DummyElem1(), DummyElem2()]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    # Patch the fuzzy_match import and explain_match in accessibility module
    def fake_fuzzy_match(search_text, candidates, attribute_names, threshold):
        # Return elem2 as best match (exact match)
        if len(candidates) >= 2:
            return [(candidates[1], 1.0), (candidates[0], 0.7)]
        return [(candidates[0], 0.9)] if candidates else []

    import code_puppy.tools.gui_cub.fuzzy_matching as fm

    monkeypatch.setattr(fm, "fuzzy_match", fake_fuzzy_match)
    monkeypatch.setattr(fm, "explain_match", lambda a, b, s: f"{a}~{b}")

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="Submit", fuzzy=True, fuzzy_threshold=0.6
    )
    assert res.success is True
    assert res.found is True


@patch("sys.platform", "darwin")
def test_list_accessible_elements_multiple(monkeypatch):
    """Test listing multiple elements."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    class DummyElem:
        AXRole = "AXButton"
        AXTitle = "Button"
        AXDescription = "A button"

    class DummyApp:
        def findAllR(self, **kwargs):
            # Return 3 elements
            return [DummyElem() for _ in range(3)]

    monkeypatch.setattr(acc, "get_frontmost_app", lambda: DummyApp())

    res: ElementListResult = acc.list_accessible_elements(role="AXButton")
    assert res.success is True
    assert res.total_elements == 3


@patch("sys.platform", "darwin")
def test_find_accessible_element_app_exception(monkeypatch):
    """Test handling of exceptions when getting frontmost app."""
    monkeypatch.setattr(acc, "ACCESSIBILITY_AVAILABLE", True)

    def raise_exception():
        raise Exception("Failed to get app")

    monkeypatch.setattr(acc, "get_frontmost_app", raise_exception)

    res: ElementSearchResult = acc.find_accessible_element(
        role="AXButton", title="Submit"
    )
    assert res.success is False
    assert "error" in res.error.lower() or "failed" in res.error.lower()
