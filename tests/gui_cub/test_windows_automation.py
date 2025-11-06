"""Unit tests for Windows automation helpers with heavy mocking.
Covers find_element and click_element flows including fuzzy fallback and coordinate click fallback.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import code_puppy.tools.gui_cub.windows_automation as winauto
from code_puppy.tools.gui_cub.result_types import (
    ElementClickResult,
    ElementSearchResult,
)


class DummyRect:
    def __init__(self, left=10, top=20, width=30, height=40):
        self.left = left
        self.top = top
        self._w = width
        self._h = height

    def width(self):
        return self._w

    def height(self):
        return self._h

    def mid_point(self):
        return SimpleNamespace(x=self.left + self._w // 2, y=self.top + self._h // 2)


@patch("sys.platform", "win32")
def test_find_element_exact_match(monkeypatch):
    # Pretend automation is available
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    # Mock Application and element
    class DummyElement:
        def __init__(self):
            self.element_info = SimpleNamespace(name="OK", control_type="Button")

        def exists(self):
            return True

        def rectangle(self):
            return DummyRect(100, 200, 50, 30)

    class DummyWindow:
        def child_window(self, **criteria):
            return DummyElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, active_only=True):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    res: ElementSearchResult = winauto.find_element(title="OK", control_type="Button")
    assert res.success is True and res.found is True
    assert res.best_match.center_x == 125


@patch("sys.platform", "win32")
def test_click_element_coordinate_fallback(monkeypatch):
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    # Return an ElementSearchResult with center coords, but make native click throw
    from code_puppy.tools.gui_cub.result_types import ElementInfo

    def fake_find_element(**kwargs):
        return ElementSearchResult(
            success=True,
            found=True,
            count=1,
            matches=[],
            best_match=ElementInfo(center_x=200, center_y=300, title="Save"),
        )

    monkeypatch.setattr(winauto, "find_element", fake_find_element)

    class DummyWindow:
        def child_window(self, **criteria):
            class Crash:
                def click_input(self):
                    raise RuntimeError("boom")

            return Crash()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, active_only=True):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)
    # Mock pyautogui.click to succeed by injecting into sys.modules
    import sys

    sys.modules["pyautogui"] = SimpleNamespace(click=lambda x, y: None)

    res: ElementClickResult = winauto.click_element(title="Save", control_type="Button")
    assert res.success is True and res.clicked is True
    assert res.method == "mouse_click"


@patch("sys.platform", "win32")
def test_click_element_fuzzy_signature(monkeypatch):
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    # Make native click pass straight through
    from code_puppy.tools.gui_cub.result_types import ElementInfo

    def fake_find_element(**kwargs):
        return ElementSearchResult(
            success=True,
            found=True,
            count=1,
            matches=[],
            best_match=ElementInfo(center_x=100, center_y=200, title="OK"),
        )

    monkeypatch.setattr(winauto, "find_element", fake_find_element)

    class DummyElement:
        def click_input(self):
            return None

    class DummyWindow:
        def child_window(self, **criteria):
            return DummyElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, active_only=True):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    res: ElementClickResult = winauto.click_element(
        title="OK", control_type="Button", fuzzy=True, fuzzy_threshold=0.6
    )
    assert res.success is True and res.clicked is True


@patch("sys.platform", "win32")
def test_get_focused_element_by_pid_success(monkeypatch):
    """Test successful focused element detection."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    # Mock focused element
    class FocusedElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="Username",
                control_type="Edit",
                automation_id="txtUsername",
                class_name="TextBox",
            )

        def has_keyboard_focus(self):
            return True

        def children(self):
            return []

        def window_text(self):
            return "test_user"

    class DummyWindow:
        def wrapper_object(self):
            return FocusedElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

        def window(self, title):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_focused_element_by_pid(pid=12345)

    assert result["success"] is True
    assert result["name"] == "Username"
    assert result["control_type"] == "Edit"
    assert result["automation_id"] == "txtUsername"
    assert result["value"] == "test_user"
    assert result["focused"] is True


@patch("sys.platform", "win32")
def test_get_focused_element_by_pid_with_window_title(monkeypatch):
    """Test focused element detection with specific window title."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    called_with_title = []

    class FocusedElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="Password",
                control_type="Edit",
                automation_id="txtPassword",
                class_name="PasswordBox",
            )

        def has_keyboard_focus(self):
            return True

        def children(self):
            return []

        def window_text(self):
            return "***"

    class DummyWindow:
        def wrapper_object(self):
            return FocusedElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

        def window(self, title):
            called_with_title.append(title)
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_focused_element_by_pid(pid=12345, window_title="Login")

    assert result["success"] is True
    assert result["name"] == "Password"
    assert called_with_title == ["Login"]


@patch("sys.platform", "win32")
def test_get_focused_element_by_pid_no_focus(monkeypatch):
    """Test when no element has focus."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    class NoFocusElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="Button",
                control_type="Button",
                automation_id="btnOK",
                class_name="Button",
            )

        def has_keyboard_focus(self):
            return False

        def children(self):
            return []

    class DummyWindow:
        def wrapper_object(self):
            return NoFocusElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_focused_element_by_pid(pid=12345)

    assert result["success"] is False
    assert "No focused element found" in result["error"]


@patch("sys.platform", "win32")
def test_get_focused_element_by_pid_not_available(monkeypatch):
    """Test when Windows automation is not available."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", False)

    result = winauto.get_focused_element_by_pid(pid=12345)

    assert result["success"] is False
    assert "not available" in result["error"].lower()


@patch("sys.platform", "win32")
def test_get_element_value_by_pid_success(monkeypatch):
    """Test successful element value retrieval."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    class DummyElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="Username",
                control_type="Edit",
                automation_id="txtUsername",
                class_name="TextBox",
            )

        def exists(self):
            return True

        def window_text(self):
            return "john_doe"

    class DummyWindow:
        def child_window(self, **criteria):
            return DummyElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

        def window(self, title):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_element_value_by_pid(
        pid=12345, name="Username", control_type="Edit"
    )

    assert result["success"] is True
    assert result["value"] == "john_doe"
    assert result["name"] == "Username"
    assert result["control_type"] == "Edit"


@patch("sys.platform", "win32")
def test_get_element_value_by_pid_with_automation_id(monkeypatch):
    """Test element value retrieval using automation_id."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    called_criteria = []

    class DummyElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="Password",
                control_type="Edit",
                automation_id="txtPassword",
                class_name="PasswordBox",
            )

        def exists(self):
            return True

        def window_text(self):
            return "hidden_password"

    class DummyWindow:
        def child_window(self, **criteria):
            called_criteria.append(criteria)
            return DummyElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_element_value_by_pid(pid=12345, automation_id="txtPassword")

    assert result["success"] is True
    assert result["value"] == "hidden_password"
    assert called_criteria[0]["auto_id"] == "txtPassword"


@patch("sys.platform", "win32")
def test_get_element_value_by_pid_element_not_found(monkeypatch):
    """Test when element is not found."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    class DummyElement:
        def exists(self):
            return False

    class DummyWindow:
        def child_window(self, **criteria):
            return DummyElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_element_value_by_pid(pid=12345, name="NonExistent")

    assert result["success"] is False
    assert "not found" in result["error"].lower()


@patch("sys.platform", "win32")
def test_get_element_value_by_pid_no_criteria(monkeypatch):
    """Test when no search criteria is provided."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_element_value_by_pid(pid=12345)

    assert result["success"] is False
    assert "search criterion" in result["error"].lower()


@patch("sys.platform", "win32")
def test_get_element_value_by_pid_not_available(monkeypatch):
    """Test when Windows automation is not available."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", False)

    result = winauto.get_element_value_by_pid(pid=12345, name="Username")

    assert result["success"] is False
    assert "not available" in result["error"].lower()


@patch("sys.platform", "win32")
def test_get_focused_element_with_nested_children(monkeypatch):
    """Test focused element detection with nested children."""
    monkeypatch.setattr(winauto, "WINDOWS_AUTOMATION_AVAILABLE", True)

    class FocusedChild:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="SearchBox",
                control_type="Edit",
                automation_id="txtSearch",
                class_name="SearchBox",
            )

        def has_keyboard_focus(self):
            return True

        def children(self):
            return []

        def window_text(self):
            return "search query"

    class ParentElement:
        def __init__(self):
            self.element_info = SimpleNamespace(
                name="SearchPanel",
                control_type="Pane",
                automation_id="pnlSearch",
                class_name="Panel",
            )

        def has_keyboard_focus(self):
            return False

        def children(self):
            return [FocusedChild()]

    class DummyWindow:
        def wrapper_object(self):
            return ParentElement()

    class DummyApp:
        def __init__(self, backend):
            pass

        def connect(self, process):
            return self

        def top_window(self):
            return DummyWindow()

    monkeypatch.setattr(winauto, "Application", DummyApp)

    result = winauto.get_focused_element_by_pid(pid=12345)

    assert result["success"] is True
    assert result["name"] == "SearchBox"
    assert result["value"] == "search query"
