"""Tests for banners.result_text: failed results always lead with the one-line summary."""

import pytest

from code_puppy.banners import result_status, result_text
from code_puppy.tools.command_runner import ShellCommandOutput
from code_puppy.tools.file_operations import (
    GrepOutput,
    ListFileOutput,
    MatchInfo,
    ReadFileOutput,
)

BOILERPLATE = "The process didn't exit cleanly! If the user_interrupted flag is true,"


class _ErrorWithEmptyStr:
    error = "boom"

    def __str__(self):
        return ""


def _shell(**fields):
    return ShellCommandOutput(
        **(
            {
                "success": True,
                "command": "c",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
            }
            | fields
        )
    )


@pytest.mark.parametrize(
    ("result", "expected_start"),
    [
        ({"error": "boom"}, "boom"),
        (_shell(success=False, exit_code=3, stderr="a\nb"), "exit code 3: b"),
    ],
    ids=["dict-error", "shell-last-stderr-line"],
)
def test_failed_text_begins_with_one_line_summary(result, expected_start):
    assert result_text(result).startswith(expected_start)


def test_failed_text_with_empty_body_is_exactly_the_summary():
    assert result_text(_ErrorWithEmptyStr()) == "boom"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (ValueError("x"), "ValueError: x"),
        (RuntimeError(), "RuntimeError"),
    ],
    ids=["exception-body-equals-summary", "exception-empty-message"],
)
def test_failed_exception_text_is_not_duplicated(result, expected):
    assert result_text(result) == expected


@pytest.mark.parametrize("result", [None, ""], ids=["none", "empty-string"])
def test_completed_empty_result_stays_empty(result):
    assert result_text(result) == ""


MATCH_ROWS = [
    {"file_path": "a.py", "line_number": 3, "line_content": "foo"},
    {"file_path": "b.py", "line_number": 9, "line_content": "bar"},
]
TWO_MATCHES = "a.py:3: foo\nb.py:9: bar"

RESULT_TEXT_CASES = [
    (ReadFileOutput(content="hello", num_tokens=1), "hello"),
    (ReadFileOutput(content=None, num_tokens=0), ""),
    (
        ReadFileOutput(content=None, num_tokens=0, error="no such file"),
        "no such file",
    ),
    (
        ReadFileOutput(
            content="no such file: a", num_tokens=0, error="no such file: a"
        ),
        "no such file: a",
    ),
    (ListFileOutput(content="a.py\nb.py"), "a.py\nb.py"),
    (ListFileOutput(content="", error="no dir"), "no dir"),
    (
        GrepOutput(
            matches=[
                MatchInfo(file_path="a.py", line_number=3, line_content="foo"),
                MatchInfo(file_path="b.py", line_number=9, line_content="bar"),
            ]
        ),
        TWO_MATCHES,
    ),
    (GrepOutput(matches=MATCH_ROWS), TWO_MATCHES),
    ({"matches": MATCH_ROWS}, TWO_MATCHES),
    (
        {
            "matches": [
                {"line_number": 1, "line_content": "no path"},
                {"file_path": "c.py", "line_number": 2, "line_content": "ok"},
            ]
        },
        "c.py:2: ok",
    ),
    (
        GrepOutput(
            matches=[
                MatchInfo(
                    file_path="a.py", line_number=1, line_content="x", is_context=True
                )
            ]
        ),
        "a.py:1: x",
    ),
    (GrepOutput(matches=[]), ""),
    (GrepOutput(matches=[], error="bad regex"), "bad regex"),
    (
        _shell(
            success=False,
            error=BOILERPLATE,
            exit_code=3,
            stderr="x\nboom",
            stdout="out",
        ),
        "exit code 3: boom\n\nout\nstderr:\nx\nboom",
    ),
    (_shell(success=False, error=BOILERPLATE, exit_code=3), "exit code 3"),
    (_shell(success=False, timeout=True), "timed out"),
    (_shell(stdout="line1\n\nline2"), "line1\n\nline2"),
    (_shell(stdout="out\n\n"), "out"),
    (_shell(stdout="", stderr=""), ""),
    (
        {"exit_code": 3, "error": BOILERPLATE, "stderr": "x\nboom", "stdout": "out"},
        "exit code 3: boom\n\nout\nstderr:\nx\nboom",
    ),
    ({"content": "hello", "error": None}, "hello"),
    ({"content": None, "error": "gone"}, "gone"),
    ({"error": "boom"}, "boom"),
    ({"a": 1}, '{"a": 1}'),
    ("plain", "plain"),
    (ValueError("x"), "ValueError: x"),
]
RESULT_TEXT_IDS = [
    "read-ok",
    "read-empty-none",
    "read-error-content-none",
    "read-error-content-starts-with-error",
    "list-ok",
    "list-error",
    "grep-two-models",
    "grep-two-dicts",
    "grep-dict-matches",
    "grep-skips-row-without-path",
    "grep-context-row-kept",
    "grep-empty",
    "grep-error",
    "shell-exit-stderr-stdout",
    "shell-exit-no-stderr",
    "shell-timeout",
    "shell-stdout-keeps-inner-blank-line",
    "shell-stdout-trailing-newlines-stripped",
    "shell-empty-streams",
    "dict-shell-exit",
    "dict-content",
    "dict-error-content-none",
    "dict-error-only",
    "dict-without-readable-fields",
    "str-passthrough",
    "exception",
]


@pytest.mark.parametrize(("result", "expected"), RESULT_TEXT_CASES, ids=RESULT_TEXT_IDS)
def test_result_text_is_readable_body_with_failure_summary(result, expected):
    assert result_text(result) == expected


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [
        (
            _shell(success=False, error=BOILERPLATE, exit_code=3, stderr="x\nboom"),
            ("failed", "exit code 3: boom"),
        ),
        (
            _shell(success=False, error=BOILERPLATE, exit_code=3),
            ("failed", "exit code 3"),
        ),
        (
            _shell(success=False, error=BOILERPLATE, exit_code=3, stderr="x" * 400),
            ("failed", "exit code 3: " + "x" * 286 + "\u2026"),
        ),
        ({"error": "boom"}, ("failed", "boom")),
    ],
    ids=[
        "exit-code-ignores-boilerplate-error",
        "exit-code-without-stderr",
        "exit-code-summary-capped-at-300",
        "error-only-unchanged",
    ],
)
def test_failure_summary_prefers_exit_code_over_error_text(result, expected_status):
    assert result_status(result) == expected_status


def test_readable_body_is_capped_at_default_limit():
    text = result_text(_shell(stdout="x" * 5000))
    assert len(text) == 4000
    assert text.endswith("\u2026")
