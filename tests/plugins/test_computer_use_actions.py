from __future__ import annotations

from unittest.mock import Mock

import pytest

from code_puppy.plugins.computer_use.backend import MacOSBackend
from code_puppy.plugins.computer_use.backend_types import ComputerUseError


class ActionAPI:
    kAXErrorSuccess = 0
    kAXValueAttribute = "AXValue"
    kAXSelectedTextRangeAttribute = "AXSelectedTextRange"
    kAXValueCFRangeType = "CFRange"

    def __init__(self, actions=()):
        self.actions = list(actions)
        self.performed = []
        self.values = []

    def AXUIElementCopyActionNames(self, element, placeholder):
        del element, placeholder
        return self.kAXErrorSuccess, self.actions

    def AXUIElementPerformAction(self, element, action):
        self.performed.append((element, action))
        return self.kAXErrorSuccess

    def AXValueCreate(self, value_type, value):
        return value_type, value

    def AXUIElementSetAttributeValue(self, element, attribute, value):
        self.values.append((element, attribute, value))
        return self.kAXErrorSuccess


def test_perform_action_only_allows_element_advertised_actions(monkeypatch):
    api = ActionAPI(["AXPress", "AXShowMenu"])
    backend = MacOSBackend()
    monkeypatch.setattr(backend, "_element", lambda *args, **kwargs: (api, "button"))
    monkeypatch.setattr(backend, "require_state", Mock())

    result = backend.perform_action("revision", 7, "axshowmenu")
    assert result["action"] == "AXShowMenu"
    assert api.performed == [("button", "AXShowMenu")]

    with pytest.raises(ComputerUseError, match="not exposed"):
        backend.perform_action("revision", 7, "AXDelete")


def test_select_text_disambiguates_and_places_cursor(monkeypatch):
    api = ActionAPI()
    backend = MacOSBackend()
    monkeypatch.setattr(backend, "_element", lambda *args, **kwargs: (api, "editor"))
    monkeypatch.setattr(backend, "require_state", Mock())
    monkeypatch.setattr(
        backend,
        "_copy_attribute",
        lambda quartz, element, attribute: "red dog, blue dog",
    )

    result = backend.select_text(
        "revision",
        3,
        "dog",
        mode="cursor_after",
        prefix="blue ",
    )
    assert result["range"] == {"location": 17, "length": 0}
    assert api.values[-1] == (
        "editor",
        "AXSelectedTextRange",
        ("CFRange", (17, 0)),
    )

    with pytest.raises(ComputerUseError, match="ambiguous"):
        backend.select_text("revision", 3, "dog")
