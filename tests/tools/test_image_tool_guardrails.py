"""Guardrail tests for image-analysis tool descriptions."""

from __future__ import annotations


class _Agent:
    def __init__(self) -> None:
        self.registered = {}

    def tool(self, func):
        self.registered[func.__name__] = func
        return func


def test_load_image_tool_docstring_discourages_guessed_paths():
    from code_puppy.tools.image_tools import register_load_image

    agent = _Agent()
    register_load_image(agent)

    doc = agent.registered["load_image_for_analysis"].__doc__ or ""
    assert "already visible in the conversation" in doc
    assert "do not call" in doc
    assert "/tmp/screenshot.png" in doc
