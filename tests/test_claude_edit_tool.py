"""Claude Code Edit-tool parity tests.

The engine semantics and error strings are ported 1:1 from Claude Code's
FileEditTool (validateInput + findActualString/preserveQuoteStyle). These
tests pin the verbatim harness behavior so the ``edit`` tool exposed to
Claude models stays inside the model's training distribution.
"""

import inspect

from code_puppy.tools import file_modifications
from code_puppy.tools.file_modifications import (
    _find_actual_string,
    _normalize_quotes,
    _preserve_quote_style,
    register_claude_edit,
)


# ---------------------------------------------------------------------------
# Engine semantics (Claude Code validateInput parity)
# ---------------------------------------------------------------------------


def test_noop_edit_refused_with_claude_message(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("hello world\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "hello", "new_str": "hello"}]
    )
    assert (
        res["error"]
        == "No changes to make: old_string and new_string are exactly the same."
    )


def test_not_found_uses_claude_message(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("hello world\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "goodbye", "new_str": "hi"}]
    )
    assert res["error"] == "String to replace not found in file.\nString: goodbye"


def test_multi_match_refused_with_claude_message(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("a spam b spam c spam\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "spam", "new_str": "eggs"}]
    )
    assert res["error"] == (
        "Found 3 matches of the string to replace, but replace_all is false. "
        "To replace all occurrences, set replace_all to true. To replace only "
        "one occurrence, please provide more context to uniquely identify the "
        "instance.\nString: spam"
    )
    assert path.read_text() == "a spam b spam c spam\n"


def test_replace_all_replaces_every_occurrence(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("a spam b spam c spam\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "spam", "new_str": "eggs", "replace_all": True}]
    )
    assert res["success"]
    assert path.read_text() == "a eggs b eggs c eggs\n"


def test_unique_match_replaces_single_occurrence(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("alpha beta gamma\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "beta", "new_str": "delta"}]
    )
    assert res["success"]
    assert path.read_text() == "alpha delta gamma\n"


def test_empty_old_string_is_not_found(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("content\n")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "", "new_str": "x"}]
    )
    assert res["error"] == "String to replace not found in file.\nString: "


# ---------------------------------------------------------------------------
# Quote normalization (findActualString / preserveQuoteStyle parity)
# ---------------------------------------------------------------------------


def test_normalize_quotes_maps_all_four_curly_quotes():
    assert _normalize_quotes("\u2018a\u2019 \u201cb\u201d") == "'a' \"b\""


def test_find_actual_string_exact_first():
    assert _find_actual_string("say 'hi'", "'hi'") == "'hi'"


def test_find_actual_string_curly_quote_fallback_returns_file_bytes():
    content = "she said \u201chello\u201d there"
    actual = _find_actual_string(content, 'said "hello" there')
    assert actual == "said \u201chello\u201d there"


def test_curly_quote_edit_applies_and_preserves_typography(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("she said \u201chello\u201d today\n")
    res = file_modifications._replace_in_file(
        None,
        str(path),
        [{"old_str": 'said "hello" today', "new_str": 'said "goodbye" today'}],
    )
    assert res["success"]
    assert path.read_text() == "she said \u201cgoodbye\u201d today\n"


def test_preserve_quote_style_contraction_uses_right_single_quote():
    old = "don't \u2018stop\u2019"
    actual = "don\u2019t \u2018stop\u2019"
    new = "don't 'go'"
    assert _preserve_quote_style(old, actual, new) == "don\u2019t \u2018go\u2019"


def test_preserve_quote_style_noop_when_exact_match():
    assert _preserve_quote_style("same", "same", 'new "text"') == 'new "text"'


# ---------------------------------------------------------------------------
# Tool schema (1:1 with the Edit tool Claude is trained on)
# ---------------------------------------------------------------------------


class _StubAgent:
    def __init__(self):
        self.registered = {}

    def tool(self, fn):
        self.registered[fn.__name__] = fn
        return fn


def test_claude_edit_schema_matches_claude_code():
    agent = _StubAgent()
    register_claude_edit(agent)
    assert "edit" in agent.registered
    params = list(inspect.signature(agent.registered["edit"]).parameters)
    assert params == [
        "context",
        "file_path",
        "old_string",
        "new_string",
        "replace_all",
    ]
    sig = inspect.signature(agent.registered["edit"])
    assert sig.parameters["replace_all"].default is False
