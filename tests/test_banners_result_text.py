"""Tests for banners.result_text: failed results always lead with the one-line summary."""

import pytest

from code_puppy.banners import result_text
from code_puppy.tools.command_runner import ShellCommandOutput


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
        (_shell(success=False, exit_code=3, stderr="a\nb"), "b"),
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
