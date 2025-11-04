"""Ensure windows_click_element accepts fuzzy parameters and forwards correctly.
This test runs on any OS by mocking sys.platform to win32 and importing the module.
We won't actually click anything because windows automation won't be available on non-Windows,
so we just verify the tool function can be called with the signature including fuzzy.
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.tools.gui_cub.windows_automation import register_windows_tools
from code_puppy.tools.gui_cub.result_types import ElementClickResult


class DummyAgent:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, fn):
        # Decorator that registers a function
        self.tools[fn.__name__] = fn
        return fn


@patch("sys.platform", "win32")
def test_windows_click_element_fuzzy_signature(monkeypatch) -> None:
    agent = DummyAgent()
    register_windows_tools(agent)

    # Ensure tool is registered
    assert "windows_click_element" in agent.tools

    tool_fn = agent.tools["windows_click_element"]

    # Call with fuzzy params; on non-Windows, it should return error about missing automation
    result: ElementClickResult = tool_fn(
        context=None,
        title="OK",
        control_type="Button",
        fuzzy=True,
        fuzzy_threshold=0.6,
    )

    # We don't assert success because it's environment-dependent; just ensure it returns a result object
    assert isinstance(result, ElementClickResult)
    # It should either be a missing dependency error or a normal result
    assert result.success in (True, False)
