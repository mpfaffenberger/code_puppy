"""i18n contracts and call sites for ``/mcp logs`` and ``/mcp search``."""

import ast
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from code_puppy.command_line.mcp import logs_command, search_command
from code_puppy.i18n import catalog, ngettext, translate
from code_puppy.i18n import t as tr
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated

_PREFIXES = ("mcp.logs.", "mcp.search.")
_MODULES = (logs_command, search_command)
_LOCALES = sorted(
    path.stem for path in (Path(catalog.__file__).parent / "locales").glob("*.json")
)
_USAGE = "`/mcp logs <server_name> [lines|all]`"
_EXAMPLES = "/mcp search database, /mcp search file, /mcp search git"

# key -> real kwargs (``count`` marks a plural key). One row per catalog key.
_REAL_PARAMS = {
    "mcp.logs.lines_not_positive": {"default": 50},
    "mcp.logs.invalid_lines": {"value": "abc", "default": 50},
    "mcp.logs.none_found": {},
    "mcp.logs.list_title": {},
    "mcp.logs.server_entry": {
        "server": "srv",
        "lines": "3 lines",
        "size": "1.0 KB",
        "rotated": " (+2 rotated)",
    },
    "mcp.logs.lines": {"count": 3},
    "mcp.logs.rotated": {"count": 2},
    "mcp.logs.usage": {"command": _USAGE},
    "mcp.logs.server_not_found": {"server": "srv"},
    "mcp.logs.no_logs_for": {"server": "srv", "path": "/logs/srv.log"},
    "mcp.logs.title_all": {"server": "srv", "count": 3},
    "mcp.logs.title_last": {"server": "srv", "showing": 2, "count": 3},
    "mcp.logs.file": {"path": "/logs/srv.log"},
    "mcp.logs.more_hint": {"all_command": "`a`", "count_command": "`b`"},
    "mcp.logs.get_failed": {"error": "boom"},
    "mcp.logs.nothing_to_clear": {"server": "srv"},
    "mcp.logs.cleared": {"server": "srv", "count": 3},
    "mcp.logs.clear_failed": {"error": "boom"},
    "mcp.search.popular_title": {},
    "mcp.search.searching": {"query": "git"},
    "mcp.search.no_results": {},
    "mcp.search.try": {"examples": _EXAMPLES},
    **{
        f"mcp.search.column.{column}": {}
        for column in ("id", "name", "category", "description", "tags")
    },
    "mcp.search.legend": {},
    "mcp.search.install_label": {},
    "mcp.search.details_label": {},
    "mcp.search.registry_unavailable": {},
    "mcp.search.failed": {"error": "boom"},
}
_PLURAL = {key for key, params in _REAL_PARAMS.items() if "count" in params}

# Layout-only or international words that are correctly identical to English.
_SAME_AS_ENGLISH = {
    *((locale, "mcp.logs.server_entry") for locale in ("es", "fr-CA")),
    *((locale, "mcp.search.column.id") for locale in ("es", "fr-CA")),
    ("fr-CA", "mcp.search.column.description"),
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

    Keys reached through ``_hint()`` are not direct calls, so they take none.
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


# ---------------------------------------------------------------- call sites

# Message glyphs, spelled as escapes so tooling cannot strip them.
_CLIPBOARD, _BULB, _TRASH = "\U0001f4cb", "\U0001f4a1", "\U0001f5d1\ufe0f"
_HOSTILE_NAME = "db[/bold]"
_HOSTILE_PATH = "/logs/[x]/db.log"
_HOSTILE_ERROR = "[red]bad[/x] [link=https://evil.example]here[/link]"


def _shape(message):
    """Comparable form of an emitted message."""
    if isinstance(message, Panel):
        return ("Panel", _shape(message.title), _shape(message.subtitle))
    if isinstance(message, Text):
        return ("Text", message.plain, str(message.style), list(message.spans))
    return message


def _render(renderable):
    """Render through the production renderer, which escapes plain strings."""
    stream = StringIO()
    console = Console(file=stream, width=200, color_system=None)
    message = SimpleNamespace(type=MessageType.INFO, content=renderable, metadata={})
    _print_message_uncoordinated(console, message)
    return stream.getvalue()


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    for module in _MODULES:
        for name in ("emit_info", "emit_error", "emit_warning", "emit_system_message"):
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **_: calls.append((_n, message)),
                )
    return calls


def _command(cls):
    command = object.__new__(cls)
    command.manager = object()
    return command


class _Logs:
    """Fake log store behind ``logs_command``'s imported helpers."""

    def __init__(self, monkeypatch):
        self.stats = {}
        self.logs = []
        self.known = True
        self.fail = None
        self.cleared = []
        patch = lambda name, value: monkeypatch.setattr(logs_command, name, value)  # noqa: E731
        patch("list_servers_with_logs", lambda: list(self.stats))
        patch("get_log_stats", self._stats)
        patch("read_logs", self._read)
        patch("get_log_file_path", lambda name: f"/logs/{name}.log")
        patch("clear_logs", self._clear)
        patch("find_server_id_by_name", lambda _m, name: name if self.known else None)
        patch("suggest_similar_servers", lambda *_a, **_k: None)

    def _stats(self, name):
        base = {"exists": False, "line_count": 0, "total_size_bytes": 0}
        return {**base, "rotated_count": 0, **self.stats.get(name, {})}

    def _read(self, name, lines=None):
        if self.fail:
            raise RuntimeError(self.fail)
        return self.logs if lines is None else self.logs[-lines:]

    def _clear(self, name, include_rotated):
        if self.fail:
            raise RuntimeError(self.fail)
        self.cleared.append(name)


@pytest.fixture
def logs(monkeypatch):
    return _Logs(monkeypatch)


def _run_logs(logs, *args):
    _command(logs_command.LogsCommand).execute(list(args), group_id="g")


def _drive_logs(logs):
    _run_logs(logs)  # no servers
    logs.stats = {
        "srv": {"exists": True, "line_count": 1, "total_size_bytes": 512},
        "big": {
            "exists": True,
            "line_count": 3,
            "total_size_bytes": 2 * 1024 * 1024,
            "rotated_count": 2,
        },
    }
    _run_logs(logs)  # server list
    _run_logs(logs, "empty", "-5")  # bad count, then no lines for the server
    _run_logs(logs, "empty", "abc")
    logs.stats["srv"]["line_count"] = 5
    logs.logs = ["a", "b", "c", "d", "e"]
    _run_logs(logs, "srv", "2")  # panel + more hint
    logs.stats["srv"]["line_count"] = 1
    logs.logs = ["a"]
    _run_logs(logs, "srv", "all")  # panel, no hint
    logs.known = False
    _run_logs(logs, "ghost")  # unknown server, no logs
    _run_logs(logs, "srv", "--clear")
    _run_logs(logs, "big", "--clear")
    _run_logs(logs, "ghost", "--clear")
    logs.known, logs.fail = True, _HOSTILE_ERROR
    _run_logs(logs, "srv")
    _run_logs(logs, "srv", "--clear")


# Expected English for every site above, in order: the pre-extraction output
# plus two deliberate changes. The literal ** markers are gone (plain strings
# are escaped, so users saw them verbatim) and a count of one is singular.
_GOLDEN_LOGS_EN = [
    (
        "emit_info",
        f"{_CLIPBOARD} No MCP server logs found.\nLogs are created when servers are started.",
    ),
    (
        "emit_info",
        f"{_CLIPBOARD} Servers with logs:\n\n  • srv - 1 line, 0.5 KB\n"
        "  • big - 3 lines, 2.0 MB (+2 rotated)\n"
        "\nUsage: `/mcp logs <server_name> [lines|all]`",
    ),
    ("emit_info", "Lines must be positive, using default: 50"),
    (
        "emit_info",
        f"{_CLIPBOARD} No logs found for server: empty\nLog file: `/logs/empty.log`",
    ),
    ("emit_info", "Invalid number 'abc', using default: 50"),
    (
        "emit_info",
        f"{_CLIPBOARD} No logs found for server: empty\nLog file: `/logs/empty.log`",
    ),
    (
        "emit_info",
        (
            "Panel",
            ("Text", f"{_CLIPBOARD} Logs for srv (last 2 of 5 lines)", "", []),
            ("Text", "Log file: /logs/srv.log", "", []),
        ),
    ),
    (
        "emit_info",
        (
            "Text",
            f"{_BULB} Use `/mcp logs srv all` to see all logs, "
            "or `/mcp logs srv <number>` for specific count",
            "dim",
            [],
        ),
    ),
    (
        "emit_info",
        (
            "Panel",
            ("Text", f"{_CLIPBOARD} Logs for srv (all 1 line)", "", []),
            ("Text", "Log file: /logs/srv.log", "", []),
        ),
    ),
    ("emit_info", "Server 'ghost' not found and has no logs."),
    ("emit_info", f"{_TRASH}  Cleared 1 log file for srv"),
    ("emit_info", f"{_TRASH}  Cleared 3 log files for big"),
    ("emit_info", "No logs to clear for server: ghost"),
    ("emit_error", f"Error getting logs: {_HOSTILE_ERROR}"),
    ("emit_error", f"Error clearing logs: {_HOSTILE_ERROR}"),
]


def test_logs_english_golden_output(logs, emitted):
    translate.set_locale("en-US")
    _drive_logs(logs)
    assert [(name, _shape(message)) for name, message in emitted] == _GOLDEN_LOGS_EN
    assert logs.cleared == ["srv", "big"]


@pytest.mark.parametrize("locale", _LOCALES)
def test_logs_messages_are_plain_or_literal_in_every_locale(locale, logs, emitted):
    translate.set_locale(locale)
    _drive_logs(logs)
    assert len(emitted) == len(_GOLDEN_LOGS_EN)
    for _, message in emitted:
        assert "**" not in _render(message)
        if isinstance(message, Panel):
            # Rich parses str titles as markup, so panels need literal Text.
            for part in (message.title, message.subtitle):
                assert isinstance(part, Text) and not part.spans
        else:
            assert type(message) is str or (
                isinstance(message, Text) and not message.spans
            )
    text = "\n".join(_render(message) for _, message in emitted)
    for command in (_USAGE, "`/mcp logs srv all`", "`/mcp logs srv <number>`"):
        assert command in text, command


# The plural follows the total, so nothing next to {showing} may need to agree
# with it ("1 dernières" and "últimas 1" were real bugs).
_SHOWING_AGREEMENT_BUGS = {"es": "últimas 1", "fr-CA": "1 dernières"}


@pytest.mark.parametrize("locale", _LOCALES)
def test_logs_title_reads_correctly_when_showing_one_of_many(locale, logs, emitted):
    translate.set_locale(locale)
    logs.stats = {"srv": {"exists": True, "line_count": 5}}
    logs.logs = ["a", "b", "c", "d", "e"]
    _run_logs(logs, "srv", "1")
    title = emitted[0][1].title.plain
    assert title == ngettext("mcp.logs.title_last", 5, server="srv", showing=1)
    assert _SHOWING_AGREEMENT_BUGS.get(locale, "\0") not in title


@pytest.mark.parametrize("locale", _LOCALES)
def test_search_and_install_report_a_missing_registry_identically(locale):
    translate.set_locale(locale)
    assert tr("mcp.search.registry_unavailable") == tr(
        "mcp.install.registry_unavailable"
    )


def test_logs_panel_and_hint_render_hostile_names_and_paths_literally(
    logs, emitted, monkeypatch
):
    monkeypatch.setattr(logs_command, "get_log_file_path", lambda _name: _HOSTILE_PATH)
    logs.stats = {_HOSTILE_NAME: {"exists": True, "line_count": 5}}
    logs.logs = ["a", "b", "c", "d", "e"]
    _run_logs(logs, _HOSTILE_NAME, "2")  # used to raise MarkupError
    panel, hint = emitted[0][1], emitted[1][1]
    rendered = _render(panel)
    assert tr("mcp.logs.file", path=_HOSTILE_PATH) in rendered
    assert _HOSTILE_NAME in rendered
    assert f"`/mcp logs {_HOSTILE_NAME} all`" in hint.plain and not hint.spans


# -------------------------------------------------------------------- search


def _server(id_, name, *, verified=False, popular=False):
    return SimpleNamespace(
        id=id_,
        display_name=name,
        category="db",
        description="d",
        tags=["x"],
        verified=verified,
        popular=popular,
    )


@pytest.fixture
def registry(monkeypatch):
    fake = SimpleNamespace(
        get_popular=lambda _n: [_server("pg", "Postgres", verified=True, popular=True)],
        search=lambda _query: [],
    )
    monkeypatch.setattr(
        "code_puppy.mcp_.server_registry_catalog.catalog", fake, raising=False
    )
    return fake


def _run_search(*args):
    _command(search_command.SearchCommand).execute(list(args), group_id="g")


@pytest.mark.parametrize("locale", _LOCALES)
def test_search_results_are_translated_and_commands_stay_literal(
    locale, registry, emitted
):
    translate.set_locale(locale)
    _run_search()
    messages = [message for _, message in emitted]
    assert messages[0] == tr("mcp.search.popular_title")
    table = messages[1]
    headers = [column.header for column in table.columns]
    assert [header.plain for header in headers] == [
        tr(f"mcp.search.column.{column}")
        for column in ("id", "name", "category", "description", "tags")
    ]
    assert all(not header.spans for header in headers)
    assert table.header_style == "bold magenta"
    assert messages[2] == tr("mcp.search.legend")
    for hint, key, command in (
        (messages[3], "mcp.search.install_label", "/mcp install <id>"),
        (messages[4], "mcp.search.details_label", "/mcp search <specific-term>"),
    ):
        label = tr(key)
        assert hint.plain == f"{label} {command}"
        assert [(span.start, span.end, span.style) for span in hint.spans] == [
            (0, len(label), "yellow")
        ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_search_no_results_keeps_example_commands(locale, registry, emitted):
    translate.set_locale(locale)
    _run_search("nothing[/x]")
    assert emitted == [
        ("emit_info", tr("mcp.search.searching", query="nothing[/x]")),
        ("emit_warning", tr("mcp.search.no_results")),
        ("emit_info", tr("mcp.search.try", examples=_EXAMPLES)),
    ]
    assert _EXAMPLES in emitted[-1][1]


def test_search_english_golden_output(registry, emitted):
    translate.set_locale("en-US")
    _run_search("nothing")
    _run_search()
    assert [message for _, message in emitted[:3]] == [
        "Searching for: nothing\n",
        "No servers found matching your search",
        "Try: /mcp search database, /mcp search file, /mcp search git",
    ]
    popular = [message for _, message in emitted[3:]]
    assert popular[0] == "Popular MCP Servers:\n"
    assert [column.header.plain for column in popular[1].columns] == [
        "ID",
        "Name",
        "Category",
        "Description",
        "Tags",
    ]
    assert popular[2] == "\n\u2713 = Verified  \u2b50 = Popular"
    assert _render(popular[3]) == _render(
        Text.from_markup("[yellow]To install:[/yellow] /mcp install <id>")
    )
    assert _render(popular[4]) == _render(
        Text.from_markup("[yellow]For details:[/yellow] /mcp search <specific-term>")
    )


@pytest.mark.parametrize("locale", _LOCALES)
def test_search_failures_render_errors_literally_in_red(
    locale, registry, emitted, monkeypatch
):
    translate.set_locale(locale)

    def explode(_query):
        raise RuntimeError(_HOSTILE_ERROR)

    registry.search = explode
    _run_search("x")  # used to raise MarkupError while reporting the error
    failure = emitted[-1][1]
    assert _shape(failure) == (
        "Text",
        tr("mcp.search.failed", error=_HOSTILE_ERROR),
        "red",
        [],
    )
    monkeypatch.setitem(sys.modules, "code_puppy.mcp_.server_registry_catalog", None)
    _run_search("x")
    assert _shape(emitted[-1][1]) == (
        "Text",
        tr("mcp.search.registry_unavailable"),
        "red",
        [],
    )
