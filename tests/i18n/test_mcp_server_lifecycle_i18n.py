"""Runtime and catalog contracts for MCP server lifecycle messages.

Covers ``/mcp start|stop|restart|remove|start-all|stop-all`` plus the shared
"did you mean" helper. Expectations are rendered through the public i18n API
with the kwargs the call sites really pass (``_REAL_PARAMS``), never derived
from the catalog text under test.

Message shape matters as much as wording: the production renderer escapes
plain ``str`` content and colours it by level (bold red errors, green
successes), while ``rich.text.Text`` is printed as-is. Sites that were plain
strings upstream must stay plain strings; sites that used styled markup use
``Text`` with an explicit style. Every expectation below pins that shape.
"""

import ast
import re
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.text import Text

import code_puppy.messaging as messaging
from code_puppy.command_line.mcp import (
    edit_command,
    remove_command,
    restart_command,
    start_all_command,
    start_command,
    stop_all_command,
    stop_command,
    utils,
)
from code_puppy.i18n import catalog, ngettext, translate
from code_puppy.i18n import t as tr
from code_puppy.mcp_.managed_server import ServerState
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated

_PREFIX = "mcp.server."
_LOCALE_DIR = Path(catalog.__file__).parent / "locales"
_LOCALES = sorted(path.stem for path in _LOCALE_DIR.glob("*.json"))
_COMMAND_MODULES = (
    start_command,
    stop_command,
    restart_command,
    start_all_command,
    stop_all_command,
    remove_command,
)
_CALLER_MODULES = (*_COMMAND_MODULES, utils, edit_command)
_EMITTERS = ("emit_info", "emit_error", "emit_success", "emit_warning")
# Values deliberately contain Rich markup: it must never be interpreted.
NAME = "srv[/dim]"
AGENT = "pup[bold]"
ERROR = "[red]boom[/red]"

_REAL_PARAMS = {
    "agent_reloaded": {},
    "already_running": {"server": NAME},
    "available": {"servers": "alpha, beta"},
    "bound": {"server": NAME, "agent": AGENT},
    "bound_session_only": {},
    "count_already_running": {"count": 2},
    "count_start_failed": {"count": 2},
    "count_started": {"count": 2},
    "count_stop_failed": {"count": 2},
    "count_stopped": {"count": 2},
    "did_you_mean": {"suggestions": "alpha, alpha-2"},
    "enabled": {"server": NAME},
    "item_failed": {"server": NAME},
    "item_started": {"server": NAME},
    "item_stopped": {"server": NAME},
    "none_registered": {},
    "none_running": {},
    "not_found": {"server": NAME},
    "reload_failed": {"server": NAME},
    "reloading_config": {},
    "remove_error": {"error": ERROR},
    "remove_failed": {"server": NAME},
    "removed": {"server": NAME},
    "restart_error": {"error": ERROR},
    "restart_start_failed": {"server": NAME},
    "restarted": {"server": NAME},
    "start_all_error": {"error": ERROR},
    "start_error": {"error": ERROR},
    "start_failed": {"server": NAME},
    "starting": {"server": NAME},
    "starting_all": {"count": 2},
    "starting_background": {"server": NAME},
    "status_tip": {},
    "stop_all_error": {"error": ERROR},
    "stop_error": {"error": ERROR},
    "stop_failed": {"server": NAME},
    "stopped": {"server": NAME},
    "stopping": {"server": NAME},
    "stopping_all": {"count": 2},
    "unbound": {"count": 2, "agents": "a1, a2"},
    "usage": {"command": "start"},
}
_PLURAL = {key for key, params in _REAL_PARAMS.items() if "count" in params}

# English as it read before extraction (plurals replace the old "server(s)").
_ENGLISH = {
    "agent_reloaded": ({}, "Agent reloaded with updated servers"),
    "already_running": ({"server": "x"}, "x: already running"),
    "available": ({"servers": "a, b"}, "Available servers: a, b"),
    "bound": (
        {"server": "s", "agent": "a"},
        "\U0001f517 Bound 's' to agent 'a'",
    ),
    "bound_session_only": ({}, "(this session only)"),
    "did_you_mean": ({"suggestions": "a, b"}, "Did you mean: a, b"),
    "enabled": ({"server": "x"}, "\u2705 Enabled server: x"),
    "item_failed": ({"server": "x"}, "\u2717 Failed: x"),
    "item_started": ({"server": "x"}, "\u2713 Started: x"),
    "item_stopped": ({"server": "x"}, "\u2713 Stopped: x"),
    "none_registered": ({}, "No servers registered"),
    "none_running": ({}, "No servers are currently running"),
    "not_found": ({"server": "x"}, "Server 'x' not found"),
    "reload_failed": (
        {"server": "x"},
        "\u2717 Failed to reload server configuration: x",
    ),
    "reloading_config": ({}, "Reloading configuration..."),
    "remove_error": ({"error": "e"}, "Error removing server: e"),
    "remove_failed": ({"server": "x"}, "\u2717 Failed to remove server: x"),
    "removed": ({"server": "x"}, "\u2713 Removed server: x"),
    "restart_error": ({"error": "e"}, "Failed to restart server: e"),
    "restart_start_failed": (
        {"server": "x"},
        "\u2717 Failed to start server after reload: x",
    ),
    "restarted": ({"server": "x"}, "\u2713 Restarted server: x"),
    "start_all_error": ({"error": "e"}, "Failed to start servers: e"),
    "start_error": ({"error": "e"}, "Failed to start server: e"),
    "start_failed": ({"server": "x"}, "Failed to start server: x"),
    "starting": ({"server": "x"}, "Starting server: x"),
    "starting_background": (
        {"server": "x"},
        "\U0001f680 Starting server: x (subprocess starting in background)",
    ),
    "status_tip": (
        {},
        "Tip: Use /mcp status to check if the server is fully initialized",
    ),
    "stop_all_error": ({"error": "e"}, "Failed to stop servers: e"),
    "stop_error": ({"error": "e"}, "Failed to stop server: e"),
    "stop_failed": ({"server": "x"}, "\u2717 Failed to stop server: x"),
    "stopped": ({"server": "x"}, "\u2713 Stopped server: x"),
    "stopping": ({"server": "x"}, "Stopping server: x"),
    "usage": ({"command": "stop"}, "Usage: /mcp stop <server_name>"),
}
# Plural keys: (params, rendered for count=1, rendered for count=3).
_ENGLISH_PLURAL = {
    "count_already_running": (
        {},
        "1 server already running",
        "3 servers already running",
    ),
    "count_start_failed": ({}, "Failed to start 1 server", "Failed to start 3 servers"),
    "count_started": ({}, "Started 1 server", "Started 3 servers"),
    "count_stop_failed": ({}, "Failed to stop 1 server", "Failed to stop 3 servers"),
    "count_stopped": ({}, "Stopped 1 server", "Stopped 3 servers"),
    "starting_all": ({}, "Starting 1 server...", "Starting 3 servers..."),
    "stopping_all": (
        {},
        "Stopping 1 running server...",
        "Stopping 3 running servers...",
    ),
    "unbound": (
        {"agents": "a1, a2"},
        "\u2713 Also unbound from 1 agent: a1, a2",
        "\u2713 Also unbound from 3 agents: a1, a2",
    ),
}


@pytest.fixture(autouse=True)
def _reset_locale():
    yield
    translate.set_locale("en-US")


def _calls(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("t", "ngettext")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value.startswith(_PREFIX)
        ):
            yield node.func.id, node.args[0].value.removeprefix(_PREFIX), node


def test_keys_and_kwargs_match_actual_callers():
    found = {}
    for module in _CALLER_MODULES:
        for func, key, node in _calls(module):
            kwargs = {keyword.arg for keyword in node.keywords}
            if func == "ngettext":
                kwargs.add("count")
            assert found.setdefault(key, kwargs) == kwargs, key
            assert (func == "ngettext") == (key in _PLURAL), key
    assert found == {key: set(params) for key, params in _REAL_PARAMS.items()}


@pytest.mark.parametrize("locale", _LOCALES)
def test_catalog_contract(locale):
    entries = catalog.load_catalog(locale)
    source = catalog.load_catalog("en-US")
    keys = {f"{_PREFIX}{suffix}" for suffix in _REAL_PARAMS}
    assert {key for key in entries if key.startswith(_PREFIX)} == keys
    assert not {"mcp.edit.not_found", "mcp.edit.usage"} & set(entries)
    translate.set_locale(locale)
    for suffix, params in _REAL_PARAMS.items():
        key = f"{_PREFIX}{suffix}"
        entry = entries[key]
        if suffix in _PLURAL:
            assert set(entry) == {"one", "other"}
        for text in entry.values() if suffix in _PLURAL else [entry]:
            assert set(re.findall(r"\{(\w+)\}", text)) == set(params)
        if locale != "en-US":
            assert entry != source[key], key
        for count in (1, 2) if suffix in _PLURAL else (None,):
            kwargs = {**params, "count": count} if count else params
            rendered = ngettext(key, count, **kwargs) if count else tr(key, **kwargs)
            assert rendered != key
            assert "{" not in rendered and "}" not in rendered
            assert all(str(value) in rendered for value in kwargs.values())


def test_english_output_is_unchanged():
    translate.set_locale("en-US")
    assert set(_ENGLISH) | set(_ENGLISH_PLURAL) == set(_REAL_PARAMS)
    for suffix, (params, expected) in _ENGLISH.items():
        assert tr(f"{_PREFIX}{suffix}", **params) == expected, suffix
    for suffix, (params, one, other) in _ENGLISH_PLURAL.items():
        key = f"{_PREFIX}{suffix}"
        assert ngettext(key, 1, **params) == one, suffix
        assert ngettext(key, 3, **params) == other, suffix


# -- call-site behaviour -------------------------------------------------------


def _server(name, state=ServerState.STOPPED):
    server = MagicMock()
    server.name, server.id, server.state = name, f"id-{name}", state
    return server


def _command(module, cls_name, servers=()):
    command = object.__new__(getattr(module, cls_name))
    command.manager = MagicMock()
    command.manager.list_servers.return_value = list(servers)
    return command


@pytest.fixture
def emitted(monkeypatch):
    """Record (emitter, message) for every emit_* the lifecycle code uses."""
    calls = []
    for module in (*_COMMAND_MODULES, messaging):
        for name in _EMITTERS:
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **kw: calls.append((_n, message)),
                )
    agent = MagicMock()
    agent.name = AGENT
    for module in (start_command, stop_command, start_all_command, stop_all_command):
        monkeypatch.setattr(module, "get_current_agent", lambda: agent)
    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: agent)
    monkeypatch.setattr(start_command, "is_bound", lambda *_: False)
    monkeypatch.setattr(start_command, "set_session_binding", lambda *_: None)
    return calls


def _shape(calls):
    """(emitter, visible text, style): style None means a plain ``str``."""
    return [
        (name, message.plain, message.style)
        if isinstance(message, Text)
        else (name, message, None)
        for name, message in calls
    ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_usage_messages(locale, emitted):
    translate.set_locale(locale)
    for module, cls_name, command, expected_style in (
        (start_command, "StartCommand", "start", "yellow"),
        (stop_command, "StopCommand", "stop", "yellow"),
        (restart_command, "RestartCommand", "restart", None),
        (remove_command, "RemoveCommand", "remove", None),
    ):
        emitted.clear()
        _command(module, cls_name).execute([], group_id="g")
        usage = tr("mcp.server.usage", command=command)
        assert _shape(emitted) == [("emit_info", usage, expected_style)]


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(
    ("module", "cls_name", "emitter"),
    [
        (start_command, "StartCommand", "emit_error"),
        (stop_command, "StopCommand", "emit_info"),
        (restart_command, "RestartCommand", "emit_info"),
        (remove_command, "RemoveCommand", "emit_info"),
    ],
)
def test_not_found_and_suggestions(locale, module, cls_name, emitter, emitted):
    translate.set_locale(locale)
    for servers, hint in (
        ([], tr("mcp.server.none_registered")),
        (
            [_server("srv-a"), _server("srv-b")],
            tr("mcp.server.did_you_mean", suggestions="srv-a, srv-b"),
        ),
        ([_server("x")], tr("mcp.server.available", servers="x")),
    ):
        emitted.clear()
        _command(module, cls_name, servers).execute(["srv"], group_id="g")
        assert _shape(emitted) == [
            (emitter, tr("mcp.server.not_found", server="srv"), None),
            ("emit_info", hint, None),
        ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_start_messages(locale, emitted, monkeypatch):
    translate.set_locale(locale)
    command = _command(start_command, "StartCommand", [_server(NAME)])
    command.manager.get_server_by_name.return_value.type = "stdio"
    command.manager.start_server_sync.return_value = True
    command.execute([NAME], group_id="g")
    bound = tr("mcp.server.bound", server=NAME, agent=AGENT)
    session_only = tr("mcp.server.bound_session_only")
    assert _shape(emitted) == [
        ("emit_info", f"{bound} {session_only}", ""),
        ("emit_success", tr("mcp.server.starting_background", server=NAME), None),
        ("emit_info", tr("mcp.server.status_tip"), "dim"),
        ("emit_info", tr("mcp.server.agent_reloaded"), None),
    ]
    message = emitted[0][1]
    dim = [message.plain[s.start : s.end] for s in message.spans if s.style == "dim"]
    assert dim == [session_only]

    emitted.clear()
    command.manager.get_server_by_name.return_value.type = "sse"
    command.manager.start_server_sync.return_value = False
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        ("emit_error", tr("mcp.server.start_failed", server=NAME), None)
    ]

    emitted.clear()
    command.manager.start_server_sync.return_value = True
    monkeypatch.setattr(start_command, "is_bound", lambda *_: True)
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        ("emit_success", tr("mcp.server.enabled", server=NAME), None),
        ("emit_info", tr("mcp.server.agent_reloaded"), None),
    ]

    emitted.clear()
    command.manager.start_server_sync.side_effect = RuntimeError(ERROR)
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        ("emit_error", tr("mcp.server.start_error", error=ERROR), None)
    ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_stop_messages(locale, emitted):
    translate.set_locale(locale)
    command = _command(stop_command, "StopCommand", [_server(NAME)])
    for result, expected in (
        (
            True,
            [
                ("emit_info", tr("mcp.server.stopped", server=NAME), None),
                ("emit_info", tr("mcp.server.agent_reloaded"), None),
            ],
        ),
        (False, [("emit_info", tr("mcp.server.stop_failed", server=NAME), None)]),
        (
            RuntimeError(ERROR),
            [("emit_error", tr("mcp.server.stop_error", error=ERROR), None)],
        ),
    ):
        emitted.clear()
        if isinstance(result, Exception):
            command.manager.stop_server_sync.side_effect = result
        else:
            command.manager.stop_server_sync.return_value = result
        command.execute([NAME], group_id="g")
        assert _shape(emitted) == expected


@pytest.mark.parametrize("locale", _LOCALES)
def test_restart_messages(locale, emitted):
    translate.set_locale(locale)
    command = _command(restart_command, "RestartCommand", [_server(NAME)])
    prefix = [
        ("emit_info", tr("mcp.server.stopping", server=NAME), None),
        ("emit_info", tr("mcp.server.reloading_config"), None),
    ]
    starting = ("emit_info", tr("mcp.server.starting", server=NAME), None)
    for reloaded, started, tail in (
        (
            True,
            True,
            [
                starting,
                ("emit_info", tr("mcp.server.restarted", server=NAME), None),
                ("emit_info", tr("mcp.server.agent_reloaded"), "dim"),
            ],
        ),
        (
            True,
            False,
            [
                starting,
                (
                    "emit_info",
                    tr("mcp.server.restart_start_failed", server=NAME),
                    None,
                ),
            ],
        ),
        (
            False,
            None,
            [("emit_info", tr("mcp.server.reload_failed", server=NAME), None)],
        ),
    ):
        emitted.clear()
        command.manager.reload_server.return_value = reloaded
        command.manager.start_server_sync.return_value = started
        command.execute([NAME], group_id="g")
        assert _shape(emitted) == prefix + tail

    emitted.clear()
    command.manager.stop_server_sync.side_effect = RuntimeError(ERROR)
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        prefix[0],
        ("emit_info", tr("mcp.server.restart_error", error=ERROR), "red"),
    ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_start_all_messages(locale, emitted):
    translate.set_locale(locale)
    command = _command(start_all_command, "StartAllCommand")
    command.execute([], group_id="g")
    assert _shape(emitted) == [
        ("emit_info", tr("mcp.server.none_registered"), "yellow")
    ]

    emitted.clear()
    command.manager.list_servers.return_value = [
        _server(NAME, ServerState.RUNNING),
        _server(NAME),
        _server(NAME),
    ]
    command.manager.start_server_sync.side_effect = [True, False]
    command.execute([], group_id="g")
    running = tr("mcp.server.already_running", server=NAME)
    assert _shape(emitted) == [
        ("emit_info", ngettext("mcp.server.starting_all", 3), None),
        ("emit_info", "  \u2022 " + running, None),
        ("emit_info", "  " + tr("mcp.server.item_started", server=NAME), "green"),
        ("emit_info", "  " + tr("mcp.server.item_failed", server=NAME), "red"),
        ("emit_info", "", None),
        ("emit_info", ngettext("mcp.server.count_started", 1), "green"),
        ("emit_info", ngettext("mcp.server.count_already_running", 1), None),
        ("emit_info", ngettext("mcp.server.count_start_failed", 1), "yellow"),
        ("emit_info", tr("mcp.server.agent_reloaded"), "dim"),
    ]

    emitted.clear()
    command.manager.list_servers.side_effect = RuntimeError(ERROR)
    command.execute([], group_id="g")
    assert _shape(emitted) == [
        ("emit_info", tr("mcp.server.start_all_error", error=ERROR), "red")
    ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_stop_all_messages(locale, emitted):
    translate.set_locale(locale)
    command = _command(stop_all_command, "StopAllCommand")
    command.execute([], group_id="g")
    assert _shape(emitted) == [("emit_info", tr("mcp.server.none_registered"), None)]

    emitted.clear()
    command.manager.list_servers.return_value = [_server(NAME)]
    command.execute([], group_id="g")
    assert _shape(emitted) == [("emit_info", tr("mcp.server.none_running"), None)]

    emitted.clear()
    command.manager.list_servers.return_value = [
        _server(NAME, ServerState.RUNNING),
        _server(NAME, ServerState.RUNNING),
    ]
    command.manager.stop_server_sync.side_effect = [True, False]
    command.execute([], group_id="g")
    assert _shape(emitted) == [
        ("emit_info", ngettext("mcp.server.stopping_all", 2), None),
        ("emit_info", "  " + tr("mcp.server.item_stopped", server=NAME), None),
        ("emit_info", "  " + tr("mcp.server.item_failed", server=NAME), None),
        ("emit_info", "", None),
        ("emit_info", ngettext("mcp.server.count_stopped", 1), None),
        ("emit_info", ngettext("mcp.server.count_stop_failed", 1), None),
        ("emit_info", tr("mcp.server.agent_reloaded"), "dim"),
    ]

    emitted.clear()
    command.manager.list_servers.side_effect = RuntimeError(ERROR)
    command.execute([], group_id="g")
    assert _shape(emitted) == [
        ("emit_info", tr("mcp.server.stop_all_error", error=ERROR), None)
    ]


@pytest.mark.parametrize("locale", _LOCALES)
def test_remove_messages(locale, emitted, monkeypatch):
    translate.set_locale(locale)
    monkeypatch.setattr(
        "code_puppy.mcp_.agent_bindings.get_agents_for_server",
        lambda _: ["a1", "a2"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.mcp.mcp_servers_store.remove_mcp_server",
        lambda _: None,
    )
    command = _command(remove_command, "RemoveCommand", [_server(NAME)])
    command.manager.remove_server.return_value = True
    command.execute([NAME], group_id="g")
    unbound = ngettext("mcp.server.unbound", 2, agents="a1, a2")
    assert _shape(emitted) == [
        ("emit_info", tr("mcp.server.removed", server=NAME), None),
        ("emit_info", "  " + unbound, None),
    ]

    emitted.clear()
    command.manager.remove_server.return_value = False
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        ("emit_info", tr("mcp.server.remove_failed", server=NAME), None)
    ]

    emitted.clear()
    command.manager.remove_server.side_effect = RuntimeError(ERROR)
    command.execute([NAME], group_id="g")
    assert _shape(emitted) == [
        ("emit_error", tr("mcp.server.remove_error", error=ERROR), None)
    ]


# -- real renderer -------------------------------------------------------------

_TYPES = {
    "emit_info": MessageType.INFO,
    "emit_error": MessageType.ERROR,
    "emit_success": MessageType.SUCCESS,
}


def _render(emitter, content, color):
    stream = StringIO()
    console = Console(
        file=stream,
        width=400,
        force_terminal=color,
        color_system="truecolor" if color else None,
    )
    message = SimpleNamespace(type=_TYPES[emitter], content=content, metadata={})
    _print_message_uncoordinated(console, message)
    return stream.getvalue()


def test_production_renderer_keeps_level_colours_and_literal_markup(emitted):
    """Errors stay bold red, successes green, and user markup stays literal."""
    command = _command(start_command, "StartCommand", [_server(NAME)])
    command.execute(["missing[/red]"], group_id="g")
    command.manager.get_server_by_name.return_value.type = "sse"
    command.manager.start_server_sync.return_value = True
    command.execute([NAME], group_id="g")
    restart = _command(restart_command, "RestartCommand", [_server(NAME)])
    restart.manager.stop_server_sync.side_effect = RuntimeError(ERROR)
    restart.execute([NAME], group_id="g")

    rendered = {
        tr("mcp.server.not_found", server="missing[/red]"): "\x1b[1;31m",
        tr("mcp.server.enabled", server=NAME): "\x1b[32m",
        tr("mcp.server.restart_error", error=ERROR): "\x1b[31m",
    }
    seen = set()
    for emitter, content in emitted:
        plain = getattr(content, "plain", content)
        if plain in rendered:
            seen.add(plain)
            assert _render(emitter, content, color=False) == plain + "\n"
            assert rendered[plain] in _render(emitter, content, color=True)
    assert seen == set(rendered)
