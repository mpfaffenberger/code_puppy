"""Record layout: field order, caps, Args marker, bare fallback, UTF-8 and bounded rotation."""

from __future__ import annotations

import array
import re
from collections import deque

import pytest

from code_puppy import callbacks, error_format, error_logging

EL = error_format


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Redirect the log and clear subscribers."""
    log_file = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))

    original = list(callbacks._callbacks.get("error_logged", []))
    callbacks._callbacks["error_logged"] = []
    yield log_file
    callbacks._callbacks["error_logged"] = original


def _entry(error, context=None, include_traceback=False) -> str:
    return EL._build_error_entry(error, context, include_traceback, "T")


def _line(entry: str, pattern: str) -> str:
    return re.search(pattern, entry, re.MULTILINE).group(1)


# field -> (limit, characters the line adds around the value, builder, line pattern)
FIELDS = {
    "message": (
        EL._MAX_MESSAGE_CHARS,
        0,
        lambda n: _entry(ValueError("m" * n)),
        r"^Error Message: (.*)$",
    ),
    "context": (
        EL._MAX_CONTEXT_CHARS,
        0,
        lambda n: _entry(ValueError("x"), context="c" * n),
        r"^Context: (.*)$",
    ),
}


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("extra", [0, 1, 3])
def test_field_is_intact_at_its_cap_and_marked_over_it(field, extra):
    limit, framing, build, pattern = FIELDS[field]

    text = _line(build(limit - framing + extra), pattern)

    if extra == 0:
        assert len(text) == limit
        assert "truncated" not in text
    else:
        assert text.endswith(EL._marker(extra))
        assert len(text) == limit + len(EL._marker(extra))


def test_traceback_keeps_the_head_the_innermost_frame_and_the_final_line(monkeypatch):
    def innermost():
        raise RuntimeError("final-boom")

    def middle():
        innermost()

    def outer():
        middle()

    try:
        outer()
    except RuntimeError as error:
        full = EL._format_traceback(error)
        monkeypatch.setattr(EL, "_MAX_TRACEBACK_CHARS", len(full) // 2)
        capped = EL._format_traceback(error)

    head = full.splitlines(keepends=True)[0]
    cut = int(re.search(r"truncated (\d+) chars", capped).group(1))
    tail = capped.split(EL._marker(cut) + "\n", 1)[1]
    assert capped.startswith(head) and head.startswith("Traceback")
    assert full.startswith(head) and full.endswith(tail)
    assert len(head) + cut + len(tail) == len(full)
    assert "in innermost" in tail and tail.endswith("RuntimeError: final-boom\n")
    assert "in outer" not in capped  # the outermost frames are what is cut


def test_huge_message_is_capped_per_exception_line_so_the_traceback_keeps_frames():
    def raiser():
        raise RuntimeError("y" * (8 * 1024 * 1024))

    try:
        raiser()
    except RuntimeError as error:
        text = EL._format_traceback(error)

    assert len(text) < 2 * EL._MAX_MESSAGE_CHARS
    assert "in raiser" in text and text.rstrip().endswith(
        EL._marker(8 * 1024 * 1024 - 4096 + len("RuntimeError: "))
    )


def test_everything_huge_at_once_stays_under_the_entry_cap(isolated_log):
    try:
        raise RuntimeError("y" * (8 * 1024 * 1024))
    except RuntimeError as error:
        entry = _entry(error, context="c" * 100_000, include_traceback=True)

    error_logging._append_entry(entry)

    assert len(isolated_log.read_text(encoding="utf-8")) <= EL._MAX_ENTRY_CHARS


class _RawSentinelRepr:
    def __repr__(self) -> str:
        return "\ufdd0"


ARGS = {
    "small": (("a", "b", 3), False),
    "exactly-at-the-cap": (("a" * 2043,), False),
    "one-element-over-the-cap": (("a" * 10_000,), True),
    "forty-500-char-elements": (tuple("a" * 500 for _ in range(40)), True),
    "five-410-char-elements": (tuple("a" * 410 for _ in range(5)), True),
    "more-than-maxtuple": (tuple(range(33)), True),
    "long-nested-list": ([list(range(40))], True),
    "a-100-digit-int": ((10**100,), False),
    # Spurious by design: a custom __repr__ returning the raw sentinel is
    # indistinguishable from an elision; the output stays bounded.
    "custom-repr-returning-the-sentinel": ((_RawSentinelRepr(),), True),
    "the-sentinel-itself": (("\ufdd0",), False),
    "the-sentinel-inside-text": (("before \ufdd0 after",), False),
}


FORTY_ITEMS = {
    "set": set(range(40)),
    "frozenset": frozenset(range(40)),
    "deque": deque(range(40)),
    "array": array.array("i", range(40)),
}


@pytest.mark.parametrize("container", FORTY_ITEMS.values(), ids=FORTY_ITEMS)
def test_every_container_type_is_marked_beyond_forty_items(container):
    text = _line(_entry(ValueError(container)), r"^Args: (.*)$")

    assert text.endswith(EL._ELIDED_MARKER)


@pytest.mark.parametrize("case", ARGS)
def test_args_marker_is_fixed_and_only_present_when_something_was_dropped(case):
    args, marked = ARGS[case]

    text = _line(_entry(ValueError(*args)), r"^Args: (.*)$")

    assert text.endswith(EL._ELIDED_MARKER) is marked
    assert marked or "truncated" not in text
    assert not re.search(r"truncated \d", text)  # a number would mislead
    assert EL._ELIDED not in text
    assert len(text) <= EL._MAX_ARGS_CHARS + len(EL._ELIDED_MARKER)


def test_entry_cap_keeps_the_header_and_closes_the_record(monkeypatch):
    monkeypatch.setattr(EL, "_MAX_ENTRY_CHARS", 1000)
    entry = (
        "\n"
        + "=" * 80
        + "\nTimestamp: T\nError Type: X\n"
        + "z" * 5000
        + "\n"
        + "=" * 80
        + "\n"
    )

    capped = EL.cap_entry(entry)

    cut = int(re.search(r"truncated (\d+) chars", capped).group(1))
    assert len(capped) <= 1000
    assert capped == entry[: len(entry) - cut] + f"\n{EL._marker(cut)}\n{'=' * 80}\n"
    assert capped.startswith("\n" + "=" * 80 + "\nTimestamp: T\nError Type: X\n")


def test_an_8_mib_message_writes_a_bounded_entry_and_the_phase_sees_the_original(
    isolated_log,
):
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))
    error = ValueError("y" * (8 * 1024 * 1024))

    error_logging.log_error(error, context="big")

    assert isolated_log.stat().st_size <= EL._MAX_ENTRY_CHARS * 4
    assert len(isolated_log.read_text(encoding="utf-8")) <= EL._MAX_ENTRY_CHARS
    assert seen == [error] and len(str(seen[0])) == 8 * 1024 * 1024


@pytest.mark.parametrize(
    "message",
    ["日" * 5000, "😀" * 5000, "ok\udc80" * 2000],
    ids=["cjk", "emoji", "lone-surrogate"],
)
def test_multibyte_text_is_cut_on_a_character_boundary_and_the_file_stays_utf8(
    isolated_log, message
):
    error_logging.log_error(ValueError(message), context="mb")
    error_logging.log_error_message(message, context="mb")

    text = isolated_log.read_bytes().decode("utf-8")  # strict: raises when invalid
    assert text.count(EL._marker(len(message) - EL._MAX_MESSAGE_CHARS)) >= 2


def test_log_error_message_is_capped_like_log_error(isolated_log):
    error_logging.log_error_message("m" * (4096 + 7), context="c" * (1024 + 3))

    text = isolated_log.read_text()
    assert _line(text, r"^Message: (.*)$").endswith(EL._marker(7))
    assert _line(text, r"^Context: (.*)$").endswith(EL._marker(3))


def test_many_large_entries_never_push_the_file_past_the_limit(
    isolated_log, monkeypatch
):
    limit = 150_000
    monkeypatch.setattr(error_logging, "MAX_LOG_SIZE", limit)
    backup = isolated_log.with_name("errors.log.1")

    for index in range(80):
        error_logging.log_error(ValueError("z" * 200_000), context=f"c{index}")
        assert isolated_log.stat().st_size <= limit

    assert backup.exists()
    assert isolated_log.stat().st_size + backup.stat().st_size <= 2 * limit


@pytest.mark.parametrize(("incoming", "rotates"), [(0, False), (10, False), (11, True)])
def test_rotation_counts_the_entry_about_to_be_written(
    isolated_log, monkeypatch, incoming, rotates
):
    monkeypatch.setattr(error_logging, "MAX_LOG_SIZE", 1000)
    isolated_log.write_text("x" * 990)

    error_logging._rotate_log_if_needed(incoming)

    assert isolated_log.with_name("errors.log.1").exists() is rotates


def test_a_failing_cap_helper_still_writes_something_and_never_raises(
    isolated_log, monkeypatch
):
    def broken(*args, **kwargs):
        raise RuntimeError("cap broke")

    monkeypatch.setattr(EL, "_cap", broken)

    error_logging.log_error(ValueError("boom"), context="ctx")
    wrote = error_logging.log_error_message("note")

    text = isolated_log.read_text()
    assert wrote is True
    assert "Error Type: ValueError" in text
    assert text.count("<entry could not be rendered>") == 2

    huge_name = type("N" * 100_000, (ValueError,), {})
    error_logging.log_error(huge_name("x"), context="ctx")

    capped = isolated_log.read_text(encoding="utf-8")[len(text) :]
    assert len(capped) <= EL._MAX_ENTRY_CHARS
    assert "truncated" in capped
