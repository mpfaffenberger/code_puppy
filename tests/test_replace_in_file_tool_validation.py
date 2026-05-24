"""Tests for the replace_in_file *tool wrapper* error handling.

These specifically target the registered agent tool (not the bare helper),
because that's where malformed payloads from a model would arrive.
"""

from typing import Callable, Dict, Any

from code_puppy.tools.file_modifications import register_replace_in_file


class _CapturingAgent:
    """Tiny fake agent that captures @agent.tool decorated functions."""

    def __init__(self) -> None:
        self.captured: Dict[str, Callable[..., Any]] = {}

    def tool(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self.captured[func.__name__] = func
        return func


def _get_replace_in_file_tool() -> Callable[..., Dict[str, Any]]:
    agent = _CapturingAgent()
    register_replace_in_file(agent)
    return agent.captured["replace_in_file"]


def test_replace_in_file_missing_new_str_returns_error(tmp_path):
    """A replacement missing 'new_str' must NOT raise — return a clean error."""
    path = tmp_path / "x.txt"
    path.write_text("hello")

    tool = _get_replace_in_file_tool()
    result = tool(
        None,
        file_path=str(path),
        replacements=[{"old_str": "hello"}],  # oops, no new_str
    )

    assert isinstance(result, dict)
    assert "error" in result
    assert "new_str" in result["error"]
    # File untouched
    assert path.read_text() == "hello"


def test_replace_in_file_missing_old_str_returns_error(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("hello")

    tool = _get_replace_in_file_tool()
    result = tool(
        None,
        file_path=str(path),
        replacements=[{"new_str": "world"}],
    )

    assert "error" in result
    assert "old_str" in result["error"]
    assert path.read_text() == "hello"


def test_replace_in_file_non_dict_replacement_returns_error(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("hello")

    tool = _get_replace_in_file_tool()
    result = tool(
        None,
        file_path=str(path),
        replacements=["not a dict"],  # type: ignore[list-item]
    )

    assert "error" in result
    assert path.read_text() == "hello"


def test_replace_in_file_happy_path_still_works(tmp_path):
    """Sanity: the validation layer didn't break the normal flow."""
    path = tmp_path / "x.txt"
    path.write_text("hello world")

    tool = _get_replace_in_file_tool()
    result = tool(
        None,
        file_path=str(path),
        replacements=[{"old_str": "world", "new_str": "biscuit"}],
    )

    assert "error" not in result
    assert path.read_text() == "hello biscuit"


def test_replace_in_file_repairs_stringified_item(tmp_path):
    """Per-item json_repair: a JSON-string replacement gets healed in place."""
    path = tmp_path / "x.txt"
    path.write_text("hello world")

    tool = _get_replace_in_file_tool()
    result = tool(
        None,
        file_path=str(path),
        replacements=['{"old_str": "world", "new_str": "biscuit"}'],  # type: ignore[list-item]
    )

    assert "error" not in result, result
    assert path.read_text() == "hello biscuit"


def test_replace_in_file_repairs_malformed_json_item(tmp_path):
    """json_repair can handle slightly broken JSON (e.g. missing quote/brace)."""
    path = tmp_path / "x.txt"
    path.write_text("hello world")

    tool = _get_replace_in_file_tool()
    # Missing closing brace — json_repair fixes this.
    result = tool(
        None,
        file_path=str(path),
        replacements=['{"old_str": "world", "new_str": "biscuit"'],  # type: ignore[list-item]
    )

    assert "error" not in result, result
    assert path.read_text() == "hello biscuit"
