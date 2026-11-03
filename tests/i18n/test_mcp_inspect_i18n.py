"""i18n contract for ``/mcp list``, ``/mcp status`` and the shared state labels.

Catalog-level checks pin keys, placeholders and the English text; the
call-site tests drive the real commands and render their Rich output, so
server-provided text is proven literal and label styling is pinned.
"""

import ast
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from code_puppy.command_line.mcp import list_command, status_command, utils
from code_puppy.i18n import catalog, ngettext, translate
from code_puppy.i18n import t as tr
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.mcp_.managed_server import ServerState

_PREFIXES = ("mcp.state.", "mcp.list.", "mcp.status.")
_MODULES = (list_command, status_command, utils)
_LOCALES = sorted(
    path.stem for path in (Path(catalog.__file__).parent / "locales").glob("*.json")
)
_LABELS = (
    "server", "id", "type", "state", "enabled", "process",
    "quarantined", "uptime", "error", "recent_events", "metadata",
)  # fmt: skip

# key -> real kwargs (``count`` marks a plural key). One row per catalog key.
_REAL_PARAMS = {
    **{f"mcp.state.{state.value}": {} for state in ServerState},
    "mcp.state.unknown": {},
    "mcp.list.title": {},
    **{f"mcp.list.column.{c}": {} for c in ("name", "type", "state")},
    **{f"mcp.list.column.{c}": {} for c in ("enabled", "uptime", "status")},
    "mcp.list.status_ok": {},
    "mcp.list.status_quarantined": {},
    "mcp.list.summary": {"running": 1, "count": 3},
    "mcp.list.error": {"error": "boom"},
    "mcp.status.failed": {"error": "boom"},
    "mcp.status.error": {"error": "boom"},
    "mcp.status.not_accessible": {"server": "srv"},
    **{f"mcp.status.label.{label}": {} for label in _LABELS},
    "mcp.status.enabled_yes": {},
    "mcp.status.enabled_no": {},
    "mcp.status.process_active": {},
    "mcp.status.process_inactive": {},
    "mcp.status.quarantined_yes": {},
    "mcp.status.metadata_keys": {"count": 3},
    "mcp.status.title": {"server": "srv"},
    "mcp.status.recent_events": {},
}
_PLURAL = {key for key, params in _REAL_PARAMS.items() if "count" in params}

# Translations that legitimately equal the English source.
_SAME_AS_ENGLISH = {
    ("es", "mcp.list.status_ok"),
    ("fr-CA", "mcp.list.status_ok"),
    ("fr-CA", "mcp.list.column.type"),
    ("es", "mcp.status.label.id"),
    ("es", "mcp.status.label.error"),
    ("es", "mcp.status.enabled_no"),
}

# The pre-extraction English, verbatim; plural rows add the fixed singular.
_ENGLISH = {
    "mcp.state.running": "\u2713 Run",
    "mcp.state.stopped": "\u2717 Stop",
    "mcp.state.starting": "\u2197 Start",
    "mcp.state.stopping": "\u2199 Stop",
    "mcp.state.error": "\u26a0 Err",
    "mcp.state.quarantined": "\u23f8 Quar",
    "mcp.state.unknown": "? Unk",
    "mcp.list.title": "\U0001f50c MCP Server Status Dashboard",
    "mcp.list.column.name": "Name",
    "mcp.list.column.type": "Type",
    "mcp.list.column.state": "State",
    "mcp.list.column.enabled": "Enabled",
    "mcp.list.column.uptime": "Uptime",
    "mcp.list.column.status": "Status",
    "mcp.list.status_ok": "OK",
    "mcp.list.status_quarantined": "Quarantined",
    "mcp.list.error": "Error listing servers: boom",
    "mcp.status.failed": "Failed to get server status: boom",
    "mcp.status.error": "Error getting server status: boom",
    "mcp.status.not_accessible": "Server 'srv' not found or not accessible",
    "mcp.status.label.server": "Server:",
    "mcp.status.label.id": "ID:",
    "mcp.status.label.type": "Type:",
    "mcp.status.label.state": "State:",
    "mcp.status.label.enabled": "Enabled:",
    "mcp.status.label.process": "Process:",
    "mcp.status.label.quarantined": "Quarantined:",
    "mcp.status.label.uptime": "Uptime:",
    "mcp.status.label.error": "Error:",
    "mcp.status.label.recent_events": "Recent Events:",
    "mcp.status.label.metadata": "Metadata:",
    "mcp.status.enabled_yes": "\u2713 Yes",
    "mcp.status.enabled_no": "\u2717 No",
    "mcp.status.process_active": "\u2713 Active (subprocess/connection running)",
    "mcp.status.process_inactive": "Not active",
    "mcp.status.quarantined_yes": "\u26a0 Yes",
    "mcp.status.title": "\U0001f50c srv Status",
    "mcp.status.recent_events": "\U0001f4cb Recent Events:",
}
_ENGLISH_PLURAL = {
    "mcp.list.summary": (
        "\U0001f4ca Summary: 1/1 server running",
        "\U0001f4ca Summary: 1/3 servers running",
    ),
    "mcp.status.metadata_keys": ("1 key", "3 keys"),
}


@pytest.fixture(autouse=True)
def _reset_locale():
    yield
    translate.set_locale("en-US")


def _string_constants(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(_PREFIXES):
                yield node.value
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("t", "ngettext")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).startswith(_PREFIXES)
        ):
            kwargs = {keyword.arg for keyword in node.keywords}
            if node.func.id == "ngettext":
                kwargs.add("count")
            yield node.func.id, node.args[0].value, kwargs


def test_keys_and_kwargs_match_actual_callers():
    """Every key is referenced, and callers pass exactly its params.

    Keys reached through ``line()``, the state map or a conditional are not
    direct calls, so they must take no params at all.
    """
    referenced, direct = set(), {}
    for module in _MODULES:
        for item in _string_constants(module):
            if isinstance(item, str):
                referenced.add(item)
            else:
                func, key, kwargs = item
                assert direct.setdefault(key, kwargs) == kwargs, key
                assert (func == "ngettext") == (key in _PLURAL), key
    assert referenced == set(_REAL_PARAMS)
    for key, params in _REAL_PARAMS.items():
        assert direct.get(key, set()) == set(params), key


@pytest.mark.parametrize("locale", _LOCALES)
def test_catalog_contract(locale):
    entries = catalog.load_catalog(locale)
    source = catalog.load_catalog("en-US")
    assert {key for key in entries if key.startswith(_PREFIXES)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        entry = entries[key]
        texts = entry.values() if key in _PLURAL else [entry]
        if key in _PLURAL:
            assert set(entry) == {"one", "other"}, key
        for text in texts:
            assert placeholder_names(text) == set(params), key
        if locale != "en-US" and (locale, key) not in _SAME_AS_ENGLISH:
            assert entry != source[key], key
        for count in (1, 2) if key in _PLURAL else (None,):
            kwargs = {k: v for k, v in params.items() if k != "count"}
            rendered = ngettext(key, count, **kwargs) if count else tr(key, **kwargs)
            assert "{" not in rendered and "}" not in rendered, key
            assert all(str(value) in rendered for value in kwargs.values()), key


def test_same_as_english_allowlist_is_still_needed():
    for locale, key in _SAME_AS_ENGLISH:
        assert catalog.load_catalog(locale)[key] == catalog.load_catalog("en-US")[key]


def test_english_output_is_unchanged():
    translate.set_locale("en-US")
    assert set(_ENGLISH) | set(_ENGLISH_PLURAL) == set(_REAL_PARAMS)
    for key, expected in _ENGLISH.items():
        assert tr(key, **_REAL_PARAMS[key]) == expected, key
    for key, (one, other) in _ENGLISH_PLURAL.items():
        kwargs = {k: v for k, v in _REAL_PARAMS[key].items() if k != "count"}
        assert ngettext(key, 1, **kwargs) == one, key
        assert ngettext(key, 3, **kwargs) == other, key


# -- call-site behaviour -------------------------------------------------------

_HOSTILE_NAME = "srv[/bold]"
_HOSTILE_ERROR = "[red]bad[/x] path"
_HOSTILE_TYPE = "st[/x]dio"
_STATE_COLORS = {
    ServerState.RUNNING: "green",
    ServerState.STOPPED: "red",
    ServerState.STARTING: "yellow",
    ServerState.STOPPING: "yellow",
    ServerState.ERROR: "red",
    ServerState.QUARANTINED: "yellow",
}


def _render(renderable):
    buffer = StringIO()
    Console(file=buffer, width=200, color_system=None).print(renderable)
    return buffer.getvalue()


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    for module in (list_command, status_command, utils):
        for name in ("emit_info", "emit_error"):
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **_: calls.append((_n, message)),
                )
    monkeypatch.setattr(
        "code_puppy.messaging.emit_info",
        lambda message, **_: calls.append(("emit_info", message)),
    )
    return calls


def _command(cls, manager):
    command = object.__new__(cls)
    command.manager = manager
    return command


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_state_has_its_own_label_and_colour(locale):
    translate.set_locale(locale)
    assert set(_STATE_COLORS) == set(ServerState), "new state needs a label"
    for state, color in _STATE_COLORS.items():
        indicator = utils.format_state_indicator(state)
        assert (indicator.plain, indicator.style) == (
            tr(f"mcp.state.{state.value}"),
            color,
        )
    unknown = utils.format_state_indicator("bogus")
    assert (unknown.plain, unknown.style) == (tr("mcp.state.unknown"), "dim")


def _list_server(name, *, state, enabled=True, quarantined=False, error=None):
    return SimpleNamespace(
        name=name, type=_HOSTILE_TYPE, state=state, enabled=enabled,
        quarantined=quarantined, error_message=error, uptime_seconds=None,
    )  # fmt: skip


@pytest.mark.parametrize("locale", _LOCALES)
def test_list_renders_translated_table_with_literal_server_text(locale, emitted):
    translate.set_locale(locale)
    manager = MagicMock()
    manager.list_servers.return_value = [
        _list_server(_HOSTILE_NAME, state=ServerState.ERROR, error=_HOSTILE_ERROR),
        _list_server("ok", state=ServerState.RUNNING),
        _list_server("held", state=ServerState.STOPPED, quarantined=True),
    ]
    _command(list_command.ListCommand, manager).execute([])

    (_, table), summary = emitted
    assert isinstance(table, Table)
    assert isinstance(table.title, Text) and table.title.style == "table.title"
    # Header text plus the column styling the table had before extraction.
    assert [
        (column.header.plain, column.style, column.justify, column.no_wrap)
        for column in table.columns
    ] == [
        (tr("mcp.list.column.name"), "cyan", "left", True),
        (tr("mcp.list.column.type"), "dim", "left", True),
        (tr("mcp.list.column.state"), "", "center", True),
        (tr("mcp.list.column.enabled"), "", "center", False),
        (tr("mcp.list.column.uptime"), "dim", "left", False),
        (tr("mcp.list.column.status"), "dim", "left", False),
    ]
    output = _render(table)  # must not raise MarkupError
    for text in (
        tr("mcp.list.title"),
        tr("mcp.list.status_ok"),
        tr("mcp.list.status_quarantined"),
        _HOSTILE_NAME,
        _HOSTILE_TYPE.upper(),
        _HOSTILE_ERROR,
    ):
        assert text in output, text
    assert summary == ("emit_info", "\n" + ngettext("mcp.list.summary", 3, running=1))


@pytest.mark.parametrize("locale", _LOCALES)
def test_list_empty_and_error_messages_stay_plain(locale, emitted):
    translate.set_locale(locale)
    manager = MagicMock()
    manager.list_servers.return_value = []
    command = _command(list_command.ListCommand, manager)
    command.execute([])
    manager.list_servers.side_effect = RuntimeError("boom")
    command.execute([])
    assert emitted == [
        ("emit_info", tr("mcp.server.none_registered")),
        ("emit_error", tr("mcp.list.error", error="boom")),
    ]


def _status_manager(**overrides):
    status = {
        "exists": True,
        "type": "stdio",
        "state": "running",
        "enabled": True,
        "quarantined": True,
        "tracker_uptime": timedelta(seconds=65),
        "error_message": _HOSTILE_ERROR,
        "recent_events_count": 3,
        "tracker_metadata": {"one": 1, "two": 2},
        "recent_events": [
            {"timestamp": datetime(2026, 1, 2, 3, 4, 5).isoformat(), "message": "up"}
        ],
        **overrides,
    }
    manager = MagicMock()
    manager.get_server_status.return_value = status
    return manager


def _styled(text, needle, style):
    start = text.plain.index(needle)
    return any(
        span.start <= start and span.end >= start + len(needle) and span.style == style
        for span in text.spans
    )


def _line(label, value):
    return f"{tr(f'mcp.status.label.{label}')} {value}"


@pytest.mark.parametrize("locale", _LOCALES)
def test_status_panel_is_translated_styled_and_literal(locale, emitted, monkeypatch):
    translate.set_locale(locale)
    lifecycle = MagicMock()
    lifecycle.is_running.return_value = True
    monkeypatch.setattr(
        "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager", lambda: lifecycle
    )
    command = _command(status_command.StatusCommand, _status_manager())
    command._show_detailed_server_status("id-1", _HOSTILE_NAME, "g")

    (_, panel), header, event = emitted
    assert isinstance(panel, Panel) and isinstance(panel.title, Text)
    assert panel.title.plain == tr("mcp.status.title", server=_HOSTILE_NAME)
    body = panel.renderable
    assert body.plain.splitlines() == [
        _line("server", _HOSTILE_NAME),
        _line("id", "id-1"),
        _line("type", "STDIO"),
        _line("state", tr("mcp.state.running")),
        _line("enabled", tr("mcp.status.enabled_yes")),
        _line("process", tr("mcp.status.process_active")),
        _line("quarantined", tr("mcp.status.quarantined_yes")),
        _line("uptime", "1m 5s"),
        _line("error", _HOSTILE_ERROR),
        _line("recent_events", "3"),
        _line("metadata", ngettext("mcp.status.metadata_keys", 2)),
    ]
    for label in _LABELS:
        assert _styled(body, tr(f"mcp.status.label.{label}"), "bold"), label
    assert _styled(body, tr("mcp.status.process_active"), "green")
    assert _styled(body, tr("mcp.status.quarantined_yes"), "yellow")
    assert _styled(body, _HOSTILE_ERROR, "red")
    _render(panel)  # must not raise MarkupError
    assert header == ("emit_info", "\n" + tr("mcp.status.recent_events"))
    assert event == ("emit_info", "  03:04:05: up")


def _minimal_status_body(emitted, monkeypatch, lifecycle_factory):
    monkeypatch.setattr(
        "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager", lifecycle_factory
    )
    manager = _status_manager(
        enabled=False, quarantined=False, error_message=None, tracker_metadata={}
    )
    _command(status_command.StatusCommand, manager)._show_detailed_server_status(
        "id-1", "srv", "g"
    )
    return emitted[0][1].renderable


def test_status_state_line_stays_unstyled_like_before(emitted, monkeypatch):
    """Frozen for parity: the old f-string flattened the indicator's colour.

    Colouring the state line would be a visible change, so it belongs in its
    own PR that updates this test deliberately.
    """
    lifecycle = MagicMock()
    lifecycle.is_running.return_value = False
    body = _minimal_status_body(emitted, monkeypatch, lambda: lifecycle)
    state = tr("mcp.state.running")
    assert not any(
        span.style == "green" and body.plain[span.start : span.end] == state
        for span in body.spans
    )
    assert _line("enabled", tr("mcp.status.enabled_no")) in body.plain.splitlines()
    assert _styled(body, tr("mcp.status.process_inactive"), "dim")
    for absent in ("quarantined", "error", "metadata"):
        assert tr(f"mcp.status.label.{absent}") not in body.plain, absent


def test_status_omits_process_line_when_lifecycle_is_unavailable(emitted, monkeypatch):
    def unavailable():
        raise RuntimeError("unavailable")

    body = _minimal_status_body(emitted, monkeypatch, unavailable)
    assert tr("mcp.status.label.process") not in body.plain
    assert _line("uptime", "1m 5s") in body.plain.splitlines()


@pytest.mark.parametrize("locale", _LOCALES)
def test_status_lookup_messages_stay_plain(locale, emitted, monkeypatch):
    translate.set_locale(locale)
    manager = _status_manager(exists=False)
    manager.list_servers.return_value = []
    monkeypatch.setattr(status_command, "find_server_id_by_name", lambda *_: None)
    command = _command(status_command.StatusCommand, manager)
    command.execute(["ghost"])
    command._show_detailed_server_status("id-1", "srv", "g")
    manager.get_server_status.side_effect = RuntimeError("boom")
    command._show_detailed_server_status("id-1", "srv", "g")
    monkeypatch.setattr(
        status_command,
        "find_server_id_by_name",
        lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    command.execute(["srv"])
    assert emitted == [
        ("emit_info", tr("mcp.server.not_found", server="ghost")),
        ("emit_info", tr("mcp.server.none_registered")),
        ("emit_info", tr("mcp.status.not_accessible", server="srv")),
        ("emit_error", tr("mcp.status.error", error="boom")),
        ("emit_info", tr("mcp.status.failed", error="boom")),
    ]
