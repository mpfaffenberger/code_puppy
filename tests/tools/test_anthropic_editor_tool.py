"""Command dispatch tests for the Anthropic native text-editor tool.

Each command is verified for its distinct failure modes (the same litmus as
every other tool: would flipping the boundary check make this test fail?).
``str_replace``/``create`` delegate to the already-hardened generic engine
(see ``tests/test_replace_in_file_safety.py``); these tests confirm the
delegation is real (the same typed errors surface through this tool) rather
than re-proving the underlying engine's full contract.
"""

import asyncio
from unittest.mock import patch

import pytest

from code_puppy.tools.anthropic_editor_tool import dispatch_editor_command


def _run(coro):
    return asyncio.run(coro)


def test_create_then_view_round_trips_line_numbered_content(tmp_path):
    p = tmp_path / "f.txt"

    create_result = _run(
        dispatch_editor_command(
            None, "create", str(p), file_text="alpha\nbeta\ngamma\n"
        )
    )
    assert create_result == {
        "success": True,
        "path": str(p),
        "message": f"File '{p}' created successfully.",
        "changed": True,
    }

    view_result = _run(dispatch_editor_command(None, "view", str(p)))
    assert view_result == {
        "path": str(p),
        "start_line": 1,
        "end_line": 3,
        "total_lines": 3,
        "content": "     1\talpha\n     2\tbeta\n     3\tgamma",
    }


def test_view_range_minus_one_end_means_through_end_of_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("one\ntwo\nthree\nfour\n")

    result = _run(dispatch_editor_command(None, "view", str(p), view_range=[2, -1]))

    assert result == {
        "path": str(p),
        "start_line": 2,
        "end_line": 4,
        "total_lines": 4,
        "content": "     2\ttwo\n     3\tthree\n     4\tfour",
    }


def test_view_range_out_of_bounds_is_rejected(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("one\ntwo\n")

    result = _run(dispatch_editor_command(None, "view", str(p), view_range=[5, 6]))

    assert result["error"] == "invalid_view_range"
    assert result["total_lines"] == 2


def test_view_range_with_non_integer_elements_is_rejected(tmp_path):
    """Regression: a non-integer view_range element (e.g. a model sending
    strings) used to raise an unhandled TypeError from the `<`/`>`
    comparisons below instead of a typed, retryable error."""
    p = tmp_path / "f.txt"
    p.write_text("one\ntwo\n")

    result = _run(
        dispatch_editor_command(None, "view", str(p), view_range=["a", "b"])
    )

    assert result["error"] == "invalid_view_range"


def test_view_directory_listing_is_bounded(tmp_path):
    """Regression: an unbounded directory listing (e.g. node_modules) could
    dump thousands of entries straight into context, defeating the same
    token budget the file-view branch already enforces."""
    for i in range(1500):
        (tmp_path / f"f{i}.txt").touch()

    result = _run(dispatch_editor_command(None, "view", str(tmp_path)))

    assert result["is_directory"] is True
    assert result["total_entries"] == 1500
    assert len(result["entries"]) < result["total_entries"]
    assert result["truncated"] is True


def test_view_missing_file_reports_not_found(tmp_path):
    p = tmp_path / "missing.txt"
    result = _run(dispatch_editor_command(None, "view", str(p)))
    assert result == {"error": "not_found", "path": str(p)}


def test_view_ranged_empty_file_does_not_crash_on_the_bus_message(tmp_path):
    """Regression: view_range=[1, 1] on a 0-line file used to clip `end` to
    0 while `start` stayed at 1, producing num_lines = end - start + 1 = 0
    -- which raises a pydantic ValidationError on FileContentMessage
    (num_lines requires >= 1). Must succeed with an explicitly empty range.
    """
    p = tmp_path / "f.txt"
    p.write_text("")

    result = _run(dispatch_editor_command(None, "view", str(p), view_range=[1, 1]))

    assert result == {
        "path": str(p),
        "start_line": 0,
        "end_line": 0,
        "total_lines": 0,
        "content": "",
    }


def test_view_unranged_empty_file_reports_a_consistent_zero_range(tmp_path):
    """Regression: the unranged path used to leave start_line=1 alongside
    end_line=0/total_lines=0 for an empty file -- a self-contradictory
    'starts at line 1 but ends before it' result."""
    p = tmp_path / "f.txt"
    p.write_text("")

    result = _run(dispatch_editor_command(None, "view", str(p)))

    assert result == {
        "path": str(p),
        "start_line": 0,
        "end_line": 0,
        "total_lines": 0,
        "content": "",
    }


def test_str_replace_delegates_ambiguous_match_to_the_hardened_engine(tmp_path):
    """Proves the delegation is real: the generic engine's ambiguous-match
    guard (never guess which occurrence) surfaces through this tool too."""
    p = tmp_path / "f.txt"
    p.write_text("dup\ndup\n")

    result = _run(
        dispatch_editor_command(None, "str_replace", str(p), old_str="dup", new_str="x")
    )

    assert result["error"] == "ambiguous_match"
    assert result["match_count"] == 2
    assert p.read_text() == "dup\ndup\n"


def test_str_replace_unique_match_writes(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("hello world\n")

    result = _run(
        dispatch_editor_command(
            None, "str_replace", str(p), old_str="world", new_str="puppy"
        )
    )

    assert result["success"] is True
    assert p.read_text() == "hello puppy\n"


def test_str_replace_missing_old_str_is_a_typed_error(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("hello\n")

    result = _run(dispatch_editor_command(None, "str_replace", str(p), new_str="x"))

    assert result == {
        "error": "missing_field",
        "command": "str_replace",
        "field": "old_str",
        "message": "command 'str_replace' requires 'old_str'.",
    }


def test_str_replace_missing_new_str_is_a_typed_error_not_a_silent_delete(tmp_path):
    """Regression: omitting new_str must fail loudly, not be coerced to ""
    (which would silently delete the matched text and report success --
    exactly the class of silent-corruption bug Phase 2 exists to remove)."""
    p = tmp_path / "f.txt"
    original = "hello world\n"
    p.write_text(original)

    result = _run(dispatch_editor_command(None, "str_replace", str(p), old_str="world"))

    assert result == {
        "error": "missing_field",
        "command": "str_replace",
        "field": "new_str",
        "message": "command 'str_replace' requires 'new_str'.",
    }
    assert p.read_text() == original


def test_str_replace_explicit_empty_new_str_is_a_deliberate_deletion(tmp_path):
    """An explicitly-passed empty string (as opposed to an omitted field)
    is a legitimate delete-the-match request and must still work."""
    p = tmp_path / "f.txt"
    p.write_text("hello world\n")

    result = _run(
        dispatch_editor_command(
            None, "str_replace", str(p), old_str=" world", new_str=""
        )
    )

    assert result["success"] is True
    assert p.read_text() == "hello\n"


def test_create_missing_file_text_is_a_typed_error(tmp_path):
    p = tmp_path / "f.txt"
    result = _run(dispatch_editor_command(None, "create", str(p)))
    assert result == {
        "error": "missing_field",
        "command": "create",
        "field": "file_text",
        "message": "command 'create' requires 'file_text'.",
    }


def test_create_overwrites_an_existing_file_unlike_portable_create_file(tmp_path):
    """Deliberate spec conformance: Anthropic's `create` always overwrites,
    unlike the portable create_file tool's default refuse-if-exists."""
    p = tmp_path / "f.txt"
    p.write_text("old content\n")

    result = _run(
        dispatch_editor_command(None, "create", str(p), file_text="new content\n")
    )

    assert result["success"] is True
    assert p.read_text() == "new content\n"


@pytest.mark.parametrize(
    "insert_line,new_str,expected_lines",
    [
        (0, "PREPENDED", ["PREPENDED", "one", "two", "three"]),
        (1, "MIDDLE", ["one", "MIDDLE", "two", "three"]),
        (3, "APPENDED", ["one", "two", "three", "APPENDED"]),
    ],
)
def test_insert_places_text_at_the_requested_line(
    tmp_path, insert_line, new_str, expected_lines
):
    p = tmp_path / "f.txt"
    p.write_text("one\ntwo\nthree\n")

    result = _run(
        dispatch_editor_command(
            None, "insert", str(p), insert_line=insert_line, new_str=new_str
        )
    )

    assert result["success"] is True
    assert p.read_text().splitlines() == expected_lines


def test_insert_into_empty_file_at_line_zero(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("")

    result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line=0, new_str="only")
    )

    assert result["success"] is True
    assert p.read_text() == "only\n"


def test_insert_out_of_range_line_is_rejected_without_writing(tmp_path):
    p = tmp_path / "f.txt"
    original = "one\ntwo\n"
    p.write_text(original)

    result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line=5, new_str="x")
    )

    assert result["error"] == "invalid_insert_line"
    assert result["line_count"] == 2
    assert p.read_text() == original


def test_insert_preserves_crlf_line_endings(tmp_path):
    """Regression guard: Phase 2 fixed a universal CRLF-loss bug in the
    read-modify-write path (see phase2-implementation-log.md). Insert must
    not reintroduce it by rebuilding the file through a plain-LF join."""
    p = tmp_path / "f.txt"
    p.write_bytes(b"one\r\ntwo\r\nthree\r\n")

    result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line=1, new_str="MIDDLE")
    )

    assert result["success"] is True
    assert p.read_bytes() == b"one\r\nMIDDLE\r\ntwo\r\nthree\r\n"


def test_insert_empty_new_str_is_a_no_op_and_pushes_no_undo_entry(tmp_path):
    """Regression: an insert that produces byte-identical content must be
    reported as a no-op, not routed through write_to_file_async as a
    'successful' write -- the same no-op contract _replace_in_file honors
    (see test_replace_in_file_safety.py::test_record_change_not_called...).
    """
    p = tmp_path / "f.txt"
    original = "one\ntwo\n"
    p.write_text(original)

    with patch("code_puppy.undo_manager.UndoManager.capture_change") as mock_capture:
        result = _run(
            dispatch_editor_command(None, "insert", str(p), insert_line=1, new_str="")
        )

    assert result == {
        "success": False,
        "path": str(p),
        "changed": False,
        "message": "No change: the inserted text was empty.",
    }
    assert p.read_text() == original
    mock_capture.assert_not_called()


def test_insert_empty_new_str_on_file_without_trailing_newline_is_a_true_no_op(
    tmp_path,
):
    """Regression: the no-op check used to run AFTER a terminator was
    already appended to the file's last line (to prep for an insertion that
    then never happened), so an empty insert against a file lacking a
    trailing newline silently added one and reported success."""
    p = tmp_path / "f.txt"
    p.write_bytes(b"one\ntwo")  # no trailing newline

    with patch("code_puppy.undo_manager.UndoManager.capture_change") as mock_capture:
        result = _run(
            dispatch_editor_command(None, "insert", str(p), insert_line=2, new_str="")
        )

    assert result == {
        "success": False,
        "path": str(p),
        "changed": False,
        "message": "No change: the inserted text was empty.",
    }
    assert p.read_bytes() == b"one\ntwo"
    mock_capture.assert_not_called()


def test_insert_line_non_integer_is_rejected(tmp_path):
    p = tmp_path / "f.txt"
    original = "one\ntwo\n"
    p.write_text(original)

    result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line="1", new_str="x")
    )

    assert result["error"] == "invalid_insert_line"
    assert p.read_text() == original


def test_view_and_insert_agree_on_line_numbers_across_form_feed(tmp_path):
    """Regression: `view` used to number lines with str.splitlines(), which
    also breaks on form feed/vertical tab/U+2028/U+2029 -- characters
    `insert` does not treat as line boundaries. A line number read from
    `view` and handed back to `insert` could then land mid-record. Using a
    form-feed byte (not a line break for either command post-fix) as the
    probe: both must agree there are 2 lines, and inserting after line 1
    must not split the form-feed-joined first line."""
    p = tmp_path / "f.txt"
    p.write_bytes(b"alpha\x0cbeta\ngamma\n")

    view_result = _run(dispatch_editor_command(None, "view", str(p)))
    assert view_result["total_lines"] == 2

    insert_result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line=1, new_str="X")
    )

    assert insert_result["success"] is True
    assert p.read_bytes() == b"alpha\x0cbeta\nX\ngamma\n"


def test_view_sanitizes_invalid_utf8_instead_of_leaking_a_surrogate(tmp_path):
    """Regression: a raw non-UTF-8 byte must be replaced, not surfaced as a
    lone surrogate codepoint that later crashes JSON/UTF-8 serialization."""
    p = tmp_path / "f.bin"
    p.write_bytes(b"good\xffbad\n")

    result = _run(dispatch_editor_command(None, "view", str(p)))

    assert "error" not in result
    assert "\udcff" not in result["content"]
    assert "\ufffd" in result["content"]


def test_insert_sanitizes_invalid_utf8_instead_of_raising(tmp_path):
    """Regression: inserting into a file with a stray non-UTF-8 byte must
    not leak an untyped UnicodeEncodeError from the eventual write."""
    p = tmp_path / "f.bin"
    p.write_bytes(b"good\xffbad\n")

    result = _run(
        dispatch_editor_command(None, "insert", str(p), insert_line=0, new_str="NEW")
    )

    assert result["success"] is True
    written = p.read_text(encoding="utf-8")
    assert "\udcff" not in written
    assert "\ufffd" in written


def test_insert_missing_required_fields_are_typed_errors(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("one\n")

    missing_line = _run(dispatch_editor_command(None, "insert", str(p), new_str="x"))
    assert missing_line == {
        "error": "missing_field",
        "command": "insert",
        "field": "insert_line",
        "message": "command 'insert' requires 'insert_line'.",
    }

    missing_text = _run(dispatch_editor_command(None, "insert", str(p), insert_line=0))
    assert missing_text == {
        "error": "missing_field",
        "command": "insert",
        "field": "new_str",
        "message": "command 'insert' requires 'new_str'.",
    }


def test_undo_edit_is_explicitly_rejected_as_unsupported(tmp_path):
    """The 2025-04-29/2025-07-28 tool versions this façade targets have no
    undo_edit command (verified: zero matches in the installed SDK) --
    reject by name rather than falling through to unknown_command, in case
    a model trained on the older tool still emits it."""
    p = tmp_path / "f.txt"
    p.write_text("one\n")

    result = _run(dispatch_editor_command(None, "undo_edit", str(p)))

    assert result["error"] == "unsupported_command"
    assert result["command"] == "undo_edit"


def test_unknown_command_lists_the_supported_set(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("one\n")

    result = _run(dispatch_editor_command(None, "delete", str(p)))

    assert result == {
        "error": "unknown_command",
        "command": "delete",
        "supported_commands": ["create", "insert", "str_replace", "view"],
        "message": "Unknown command 'delete'. Supported: "
        "['create', 'insert', 'str_replace', 'view'].",
    }


@pytest.mark.parametrize(
    "command,kwargs,expected_payload_type",
    [
        (
            "str_replace",
            {"old_str": "world", "new_str": "puppy"},
            "ReplacementsPayload",
        ),
        ("create", {"file_text": "hi\n"}, "ContentPayload"),
        ("insert", {"insert_line": 0, "new_str": "NEW"}, "ContentPayload"),
    ],
)
def test_mutation_commands_fire_on_edit_file_like_the_portable_tools(
    tmp_path, command, kwargs, expected_payload_type
):
    """Regression: str_replace/create/insert used to call write_to_file_async
    / replace_in_file_async directly and return early, silently skipping the
    on_edit_file callback that the portable create_file/replace_in_file
    tools fire after every write (see file_modifications.py). Any plugin
    hooking on_edit_file -- e.g. for rejection-detail enrichment or
    telemetry -- must see native-editor writes too, not just portable ones.
    """
    p = tmp_path / "f.txt"
    p.write_text("hello world\n")

    with patch(
        "code_puppy.tools.anthropic_editor_tool.on_edit_file", return_value=None
    ) as mock_hook:
        result = _run(dispatch_editor_command(None, command, str(p), **kwargs))

    assert result["success"] is True
    mock_hook.assert_called_once()
    call_args = mock_hook.call_args.args
    assert call_args[0] is None  # context
    assert call_args[1] is result  # the result dict passed to the hook
    assert type(call_args[2]).__name__ == expected_payload_type


def test_on_edit_file_enhancement_result_overrides_the_returned_dict(tmp_path):
    """Mirrors the portable tools' contract: the first non-None value a
    plugin returns from on_edit_file replaces the tool's own result."""
    p = tmp_path / "f.txt"
    p.write_text("hello world\n")
    sentinel = {"success": True, "path": str(p), "enhanced": True}

    with patch(
        "code_puppy.tools.anthropic_editor_tool.on_edit_file",
        return_value=[None, sentinel],
    ):
        result = _run(
            dispatch_editor_command(
                None, "str_replace", str(p), old_str="world", new_str="puppy"
            )
        )

    assert result == sentinel
