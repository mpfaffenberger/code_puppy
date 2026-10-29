"""The errors.log record layout stays byte-compatible with the format on main."""

from __future__ import annotations

from code_puppy import error_format

RULE = "=" * 80


def _raised(exc: BaseException) -> BaseException:
    try:
        raise exc
    except BaseException as caught:
        return caught


def test_entry_lines_are_in_the_exact_order():
    error = _raised(ValueError("boom"))

    full = error_format._build_error_entry(error, "ctx", True, "T").splitlines()
    plain = error_format._build_error_entry(error, "ctx", False, "T")

    heads = [
        next(i for i, line in enumerate(full) if line.startswith(head))
        for head in (
            "Timestamp:",
            "Error Type:",
            "Error Message:",
            "Context:",
            "Traceback:",
            "Args:",
        )
    ]
    assert heads == sorted(heads)
    assert plain == (
        f"\n{RULE}\nTimestamp: T\nError Type: ValueError\nError Message: boom\n"
        f"Context: ctx\nArgs: ('boom',)\n{RULE}\n"
    )


def test_message_entry_format_is_unchanged():
    entry = error_format.render_message_entry("hello", "ctx")

    lines = entry.splitlines()
    assert [line.split(":")[0] for line in lines if line and set(line) != {"="}] == [
        "Timestamp",
        "Message",
        "Context",
    ]
    assert entry.startswith(f"\n{RULE}\n") and entry.endswith(f"\n{RULE}\n")
