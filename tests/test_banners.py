"""Tests for code_puppy.banners: wire shape, terminal markup, titles, failure status, notices."""

import logging
import sys
import threading
import types
from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text

import code_puppy
from code_puppy import banners, callbacks, config
from code_puppy.banners import (
    Banner,
    BannerDef,
    banner_for_call,
    banner_for_result,
    emit_notice,
    get_banner_def,
    has_banner_def,
    notice,
    register_banner_def,
    result_status,
    result_text,
)
from code_puppy.messaging import message_queue
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.message_queue import MessageType, UIMessage
from code_puppy.messaging.renderers import _print_message_uncoordinated
from code_puppy.messaging.rich_renderer import RichConsoleRenderer
from code_puppy.tools.command_runner import ShellCommandOutput
from code_puppy.tools.file_operations import GrepOutput, ListFileOutput, ReadFileOutput

READ_FILE = BannerDef("read_file", "READ FILE", "read", ("file_path",), "path")
SHELL = BannerDef("shell_command", "SHELL COMMAND", "execute", ("command",), "command")
GREP = BannerDef("grep", "GREP", "search", ("pattern", "directory"), "query")
LONG = "x" * 70


@pytest.fixture
def registry(monkeypatch):
    """Isolated registry seeded with test-only definitions; builtins never load."""
    monkeypatch.setattr(banners, "_definitions", {})
    monkeypatch.setattr(banners, "_builtins_loaded", True)
    register_banner_def("read_file", READ_FILE)
    register_banner_def("shell_command", SHELL)
    register_banner_def("grep", GREP)


@pytest.fixture
def fixed_colour(monkeypatch):
    monkeypatch.setattr(config, "get_banner_color", lambda name: "dark_orange")


@pytest.fixture
def bus(monkeypatch):
    """Record every legacy INFO emission instead of queueing it for a renderer."""
    sent = []
    monkeypatch.setattr(
        message_queue,
        "emit_message",
        lambda message_type, content, **metadata: sent.append((message_type, content)),
    )
    return sent


@pytest.fixture
def seen_callbacks(monkeypatch):
    seen = []
    monkeypatch.setattr(callbacks, "on_banner_notice", seen.append, raising=False)
    return seen


def _banner(**overrides):
    fields = {
        "event": "tool_call",
        "name": "read_file",
        "label": "READ FILE",
        "kind": "read",
        "title": "READ FILE",
    }
    return Banner(**(fields | overrides))


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


def _read(**fields):
    return ReadFileOutput(**({"content": "x", "num_tokens": 1} | fields))


def test_to_wire_emits_every_camel_case_key_when_set():
    banner = Banner(
        event="tool_result",
        name="shell_command",
        label="SHELL COMMAND",
        kind="execute",
        title="SHELL COMMAND exit 3",
        target="exit 3",
        target_type="command",
        status="failed",
        details="d",
        error="exit code 3",
        duration_ms=12.5,
        exit_code=3,
    )
    assert banner.to_wire() == {
        "v": 1,
        "event": "tool_result",
        "name": "shell_command",
        "label": "SHELL COMMAND",
        "kind": "execute",
        "title": "SHELL COMMAND exit 3",
        "target": "exit 3",
        "targetType": "command",
        "status": "failed",
        "details": "d",
        "error": "exit code 3",
        "durationMs": 12.5,
        "exitCode": 3,
    }


def test_to_wire_omits_none_but_keeps_zero_values_and_version():
    assert _banner(exit_code=0, duration_ms=0.0).to_wire() == {
        "v": 1,
        "event": "tool_call",
        "name": "read_file",
        "label": "READ FILE",
        "kind": "read",
        "title": "READ FILE",
        "durationMs": 0.0,
        "exitCode": 0,
    }


def test_markup_matches_terminal_renderer_bracket_format_byte_for_byte(fixed_colour):
    renderer = RichConsoleRenderer(MessageBus())
    assert _banner().to_markup() == renderer._format_banner("read_file", "READ FILE")


def test_markup_escapes_target_so_it_renders_literally(fixed_colour):
    markup = _banner(target="[red]x", target_type="path").to_markup()
    assert Text.from_markup(markup).plain == " READ FILE  [red]x"


def test_markup_target_matches_the_title_target(fixed_colour):
    target = "first line\n" + LONG + "\nthird"
    banner = _banner(target=target, target_type="text")
    assert Text.from_markup(banner.to_markup()).plain == " READ FILE  first line"
    assert (
        banner.to_markup()
        == _banner(target="first line", target_type="text").to_markup()
    )


def test_markup_escapes_label_so_brackets_render_literally(fixed_colour):
    assert Text.from_markup(_banner(label="A [b]").to_markup()).plain == " A [b] "


@pytest.mark.parametrize(
    ("event", "expected_plain"),
    [("plugin_notice", " KB CARD  2 cards"), ("tool_call", " KB CARD ")],
    ids=["notice-shows-details", "tool-hides-details"],
)
def test_markup_appends_dim_details_only_for_plugin_notices(
    fixed_colour, event, expected_plain
):
    banner = _banner(event=event, label="KB CARD", details="2 cards")
    assert Text.from_markup(banner.to_markup()).plain == expected_plain


def test_registered_definition_is_returned_and_reported(registry):
    assert get_banner_def("read_file") == READ_FILE
    assert has_banner_def("read_file") is True


@pytest.mark.parametrize("tool_name", ["mystery_tool", "a"])
def test_unknown_tool_gets_fallback_definition_that_is_not_registered(
    registry, tool_name
):
    assert get_banner_def(tool_name) == BannerDef(
        name=tool_name, label=tool_name.upper(), kind="other"
    )
    assert has_banner_def(tool_name) is False


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        (BannerDef("x", "LIT", "other", label_key="k.one"), "localized:k.one"),
        (BannerDef("x", "LIT", "other"), "LIT"),
    ],
    ids=["label-key-translated", "no-key-uses-literal"],
)
def test_resolved_label_translates_only_when_key_is_set(
    monkeypatch, definition, expected
):
    monkeypatch.setattr(banners, "t", lambda key, **_: f"localized:{key}")
    assert definition.resolved_label() == expected


def test_builtin_definitions_load_once_on_first_lookup(monkeypatch):
    monkeypatch.setattr(banners, "_definitions", {})
    monkeypatch.setattr(banners, "_builtins_loaded", False)
    calls = []

    def register_builtin_banner_defs():
        calls.append(True)
        register_banner_def("fake_tool", BannerDef("fake_tool", "FAKE", "other"))

    fake = types.ModuleType("code_puppy.banner_defs")
    fake.register_builtin_banner_defs = register_builtin_banner_defs
    monkeypatch.setitem(sys.modules, "code_puppy.banner_defs", fake)
    monkeypatch.setattr(code_puppy, "banner_defs", fake, raising=False)

    assert has_banner_def("fake_tool") is True
    assert get_banner_def("fake_tool").label == "FAKE"
    assert calls == [True]


def test_call_banner_carries_definition_target_and_in_progress_status(registry):
    assert banner_for_call("read_file", {"file_path": "/a/b/s.txt"}) == Banner(
        event="tool_call",
        name="read_file",
        label="READ FILE",
        kind="read",
        title="READ FILE s.txt",
        target="/a/b/s.txt",
        target_type="path",
        status="in_progress",
    )


TITLE_CASES = [
    ("read_file", {"file_path": "/a/b/s.txt"}, "READ FILE s.txt", "/a/b/s.txt"),
    ("read_file", {"file_path": "s.txt"}, "READ FILE s.txt", "s.txt"),
    ("read_file", {"file_path": "/"}, "READ FILE /", "/"),
    ("read_file", {}, "READ FILE", None),
    ("read_file", {"file_path": ""}, "READ FILE", None),
    ("read_file", None, "READ FILE", None),
    ("read_file", "not-a-dict", "READ FILE", None),
    ("shell_command", {"command": LONG}, f"SHELL COMMAND {'x' * 59}…", LONG),
    ("shell_command", {"command": "x" * 60}, f"SHELL COMMAND {'x' * 60}", "x" * 60),
    ("shell_command", {"command": "ls\necho hi"}, "SHELL COMMAND ls", "ls\necho hi"),
    (
        "shell_command",
        {"command": "\n pytest\n"},
        "SHELL COMMAND pytest",
        "\n pytest\n",
    ),
    ("grep", {"pattern": "p" * 70}, f"GREP {'p' * 59}…", "p" * 70),
    ("grep", {"pattern": "", "directory": "src"}, "GREP src", "src"),
    ("grep", {"pattern": "a\nb"}, "GREP a", "a\nb"),
]
TITLE_IDS = [
    "path-basename",
    "path-bare-name",
    "path-root",
    "missing-target",
    "empty-target",
    "args-none",
    "args-not-dict",
    "command-cut-to-60",
    "command-of-60-kept",
    "command-first-line-only",
    "command-skips-leading-blank-lines",
    "query-cut-to-60",
    "first-non-empty-target-arg-wins",
    "query-first-line-only",
]


@pytest.mark.parametrize(
    ("tool", "args", "title", "target"), TITLE_CASES, ids=TITLE_IDS
)
def test_call_title_and_target_follow_target_type_rules(
    registry, tool, args, title, target
):
    banner = banner_for_call(tool, args)
    assert (banner.title, banner.target) == (title, target)


def test_call_falls_back_when_definition_lookup_breaks(monkeypatch):
    def broken(tool_name):
        raise RuntimeError("registry corrupt")

    monkeypatch.setattr(banners, "get_banner_def", broken)
    assert banner_for_call("read_file", {"file_path": "x"}) == Banner(
        event="tool_call",
        name="read_file",
        label="READ_FILE",
        kind="other",
        title="READ_FILE",
        status="in_progress",
    )


class _UnprintableError(Exception):
    def __str__(self):
        raise RuntimeError("no text")


STATUS_CASES = [
    (RuntimeError("boom"), ("failed", "RuntimeError: boom")),
    (ValueError(), ("failed", "ValueError")),
    ({"error": "nope"}, ("failed", "nope")),
    ({"error": ""}, ("completed", None)),
    ({"error": None, "success": True}, ("completed", None)),
    ({"success": False, "stderr": "bad\nreal reason\n"}, ("failed", "real reason")),
    ({"success": False}, ("failed", "tool reported failure")),
    ({"exit_code": 3, "stderr": "a\nlast line"}, ("failed", "exit code 3: last line")),
    ({"exit_code": 3}, ("failed", "exit code 3")),
    ({"exit_code": 0}, ("completed", None)),
    ({"exit_code": True}, ("completed", None)),
    ({"timeout": True}, ("failed", "timed out")),
    ({"timeout": False}, ("completed", None)),
    ("plain text", ("completed", None)),
    (None, ("completed", None)),
    (_read(content=None, num_tokens=0, error="gone"), ("failed", "gone")),
    (_read(), ("completed", None)),
    (GrepOutput(matches=[], error="bad regex"), ("failed", "bad regex")),
    (ListFileOutput(content="", error="no dir"), ("failed", "no dir")),
    (_shell(success=False, command="exit 3", exit_code=3), ("failed", "exit code 3")),
    (
        _shell(success=False, exit_code=1, stderr="oops"),
        ("failed", "exit code 1: oops"),
    ),
    (_shell(success=False, timeout=True), ("failed", "timed out")),
    (_shell(), ("completed", None)),
    ({"error": logging.getLogger("x").error}, ("completed", None)),
    (
        types.SimpleNamespace(error=print, success=False),
        ("failed", "tool reported failure"),
    ),
    (_UnprintableError(), ("failed", "_UnprintableError")),
]
STATUS_IDS = [
    "exception",
    "exception-empty-message",
    "dict-error",
    "dict-falsy-error",
    "dict-none",
    "success-false-uses-last-stderr-line",
    "success-false-bare",
    "exit-code-stderr-wins",
    "exit-code-without-stderr",
    "exit-code-zero",
    "bool-exit-code-ignored",
    "timeout",
    "timeout-false",
    "plain-string",
    "none",
    "read-file-error",
    "read-file-ok",
    "grep-error",
    "list-files-error",
    "shell-exit-3",
    "shell-stderr",
    "shell-timeout",
    "shell-ok",
    "callable-error-ignored",
    "callable-error-with-success-false",
    "exception-whose-str-raises",
]


@pytest.mark.parametrize(("result", "expected"), STATUS_CASES, ids=STATUS_IDS)
def test_result_status_failure_rules(result, expected):
    assert result_status(result) == expected


@pytest.mark.parametrize(
    ("message_length", "expected"),
    [(300, "x" * 300), (301, "x" * 299 + "…")],
    ids=["300-kept", "301-cut-to-300"],
)
def test_error_summary_is_capped_at_300_characters(message_length, expected):
    assert result_status({"error": "x" * message_length}) == ("failed", expected)


def test_multi_line_error_summary_is_first_non_empty_line():
    assert result_status({"error": "\nfirst\nsecond"}) == ("failed", "first")


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("hello", "hello"),
        (None, ""),
        ({"a": 1}, '{"a": 1}'),
        (["x", 2], '["x", 2]'),
        ({"name": "é"}, '{"name": "é"}'),
        (5, "5"),
        (ValueError("bad"), "ValueError: bad"),
    ],
    ids=["string", "none", "dict", "list", "non-ascii", "other", "exception"],
)
def test_result_text_renders_readable_text(result, expected):
    assert result_text(result) == expected


@pytest.mark.parametrize(
    ("text_length", "limit", "expected"),
    [
        (4000, 4000, "x" * 4000),
        (4001, 4000, "x" * 3999 + "…"),
        (20, 10, "x" * 9 + "…"),
    ],
    ids=["default-limit-exact", "default-limit-cut", "custom-limit"],
)
def test_result_text_caps_total_length_at_limit(text_length, limit, expected):
    text = result_text("x" * text_length, limit=limit)
    assert text == expected
    assert len(text) <= limit


def test_failed_text_starts_with_summary_then_readable_body():
    result = _shell(success=False, stdout="out", stderr="boom\n", exit_code=2)
    assert result_text(result) == "exit code 2: boom\n\nout\nstderr:\nboom"


def test_failed_text_is_not_duplicated_when_body_equals_summary():
    assert result_text(RuntimeError("x")) == "RuntimeError: x"


class _Unprintable:
    def __str__(self):
        raise RuntimeError("no str")

    def __repr__(self):
        return "<unprintable>"


def test_result_text_never_raises_and_falls_back_to_repr():
    assert result_text(_Unprintable()) == "<unprintable>"


def test_result_banner_for_failed_shell_carries_status_error_and_exit_code(registry):
    result = _shell(success=False, command="exit 3", exit_code=3)
    assert banner_for_result(
        "shell_command", {"command": "exit 3"}, result, duration_ms=12.5
    ) == Banner(
        event="tool_result",
        name="shell_command",
        label="SHELL COMMAND",
        kind="execute",
        title="SHELL COMMAND exit 3",
        target="exit 3",
        target_type="command",
        status="failed",
        error="exit code 3",
        duration_ms=12.5,
        exit_code=3,
    )


def test_result_banner_for_success_has_completed_status_and_no_error(registry):
    banner = banner_for_result("read_file", {"file_path": "/a/s.txt"}, _read())
    assert banner.title == "READ FILE s.txt"
    assert (banner.status, banner.error, banner.exit_code, banner.duration_ms) == (
        "completed",
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("result", "expected_exit_code"),
    [({"exit_code": 0, "stdout": "ok"}, 0), ({"exit_code": True}, None), ("ok", None)],
    ids=["dict-exit-code", "bool-ignored", "string-has-none"],
)
def test_result_banner_exit_code_is_integer_only(registry, result, expected_exit_code):
    assert (
        banner_for_result("shell_command", {}, result).exit_code == expected_exit_code
    )


def test_result_banner_for_exception_is_failed_with_type_and_message(registry):
    banner = banner_for_result("read_file", {}, RuntimeError("boom"))
    assert (banner.status, banner.error, banner.exit_code) == (
        "failed",
        "RuntimeError: boom",
        None,
    )


def test_notice_builds_info_plugin_notice_without_target():
    assert notice("kb.card_injected", "KB CARD", details="2 cards") == Banner(
        event="plugin_notice",
        name="kb.card_injected",
        label="KB CARD",
        kind="other",
        title="KB CARD",
        status="info",
        details="2 cards",
    )


def test_notice_with_target_is_text_typed_and_title_cut_to_60():
    banner = notice("kb.card_injected", "KB CARD", target="a" * 70)
    assert (banner.target, banner.target_type) == ("a" * 70, "text")
    assert banner.title == f"KB CARD {'a' * 59}…"


def test_emit_notice_fires_callback_with_wire_dict_and_prints_once(bus, seen_callbacks):
    banner = notice("kb.card_injected", "KB CARD", details="2 cards")
    emit_notice(banner)

    assert seen_callbacks == [banner.to_wire()]
    assert len(bus) == 1
    message_type, content = bus[0]
    assert message_type == MessageType.INFO
    assert isinstance(content, Text)
    assert content.plain == " KB CARD  2 cards"


def test_printed_notice_renders_styled_text_not_literal_tags(bus, seen_callbacks):
    emit_notice(notice("kb.card_injected", "KB CARD", details="2 cards"))
    ((message_type, content),) = bus

    console = Console(file=StringIO(), width=120, force_terminal=False)
    _print_message_uncoordinated(console, UIMessage(type=message_type, content=content))
    output = console.file.getvalue()
    assert "KB CARD" in output
    assert "2 cards" in output
    assert "[bold white" not in output


@pytest.mark.parametrize(
    ("bus_fails", "callback_fails"),
    [(True, False), (False, True), (True, True)],
    ids=["bus-fails", "callback-fails", "both-fail"],
)
def test_emit_notice_never_raises_and_steps_are_independent(
    monkeypatch, bus_fails, callback_fails
):
    attempts = {"bus": 0, "callback": 0}

    def fake_bus(message_type, content, **metadata):
        attempts["bus"] += 1
        if bus_fails:
            raise RuntimeError("bus down")

    def fake_callback(banner):
        attempts["callback"] += 1
        if callback_fails:
            raise RuntimeError("hook down")

    monkeypatch.setattr(message_queue, "emit_message", fake_bus)
    monkeypatch.setattr(callbacks, "on_banner_notice", fake_callback, raising=False)

    emit_notice(notice("kb.card_injected", "KB CARD"))
    assert attempts == {"bus": 1, "callback": 1}


async def test_emit_notice_works_inside_running_event_loop(bus, seen_callbacks):
    banner = notice("kb.card_injected", "KB CARD")
    emit_notice(banner)
    assert seen_callbacks == [banner.to_wire()]
    assert len(bus) == 1


def test_emit_notice_works_from_worker_thread(bus, seen_callbacks):
    banner = notice("kb.card_injected", "KB CARD")
    worker = threading.Thread(target=emit_notice, args=(banner,))
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert seen_callbacks == [banner.to_wire()]
    assert len(bus) == 1
