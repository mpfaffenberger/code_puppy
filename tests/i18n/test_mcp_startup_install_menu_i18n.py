"""i18n contracts and call sites for MCP stdio startup and the install menu.

Catalog checks pin keys, placeholders and translations; the call-site tests
drive the real code paths through the real ``emit_*`` -> ``emit_message``
seam (so close-notice suppression applies) and render through the
production renderer, so names, errors and subprocess output print literally.
"""

import ast
import sys
import threading
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.mcp import MCPToolset
from rich.console import Console
from rich.errors import MarkupError
from rich.text import Text

from code_puppy.command_line import menu_session
from code_puppy.command_line.mcp import install_menu
from code_puppy.i18n import catalog, translate
from code_puppy.i18n import t as tr
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.mcp_ import blocking_startup
from code_puppy.messaging import message_queue
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated

_PREFIXES = ("mcp.startup.", "mcp.install_menu.")
_MODULES = (blocking_startup, install_menu)
_LOCALES = sorted(
    path.stem for path in (Path(catalog.__file__).parent / "locales").glob("*.json")
)
_AGENTS_COMMAND = "/agents \u2192 B"

# key -> real kwargs. One row per catalog key; none of these are plural.
_REAL_PARAMS = {
    "mcp.startup.stderr_line": {"server": "srv", "line": "listening on stdio"},
    "mcp.startup.not_started": {
        "server": "srv",
        "logs_command": "/mcp logs srv",
        "agents_command": _AGENTS_COMMAND,
    },
    "mcp.install_menu.no_categories": {},
    "mcp.install_menu.catalog_unavailable": {"error": "boom"},
    "mcp.install_menu.load_error": {"error": "boom"},
    "mcp.install_menu.no_catalog": {},
}

# "MCP {server}: {line}" is a product token plus punctuation: only fr-CA
# typography (space before the colon) differs from English.
_SAME_AS_ENGLISH = {("es", "mcp.startup.stderr_line")}


# ------------------------------------------------------------------ catalog


def _translator_calls(module):
    """Yield every prefixed string constant and every ``t()`` call."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(_PREFIXES):
                yield node.value
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "t"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).startswith(_PREFIXES)
        ):
            yield node.args[0].value, {keyword.arg for keyword in node.keywords}


def test_keys_and_kwargs_match_actual_callers():
    """Every key is called exactly as the catalog expects: no dead or missing keys."""
    referenced, called = set(), {}
    for module in _MODULES:
        for item in _translator_calls(module):
            if isinstance(item, str):
                referenced.add(item)
                continue
            key, kwargs = item
            assert called.setdefault(key, kwargs) == kwargs, key
    assert referenced == set(called) == set(_REAL_PARAMS)
    for key, params in _REAL_PARAMS.items():
        assert called[key] == set(params), key


@pytest.mark.parametrize("locale", _LOCALES)
def test_catalog_contract(locale):
    entries = catalog.load_catalog(locale)
    source = catalog.load_catalog("en-US")
    assert {key for key in entries if key.startswith(_PREFIXES)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        text = entries[key]
        assert isinstance(text, str), key
        assert placeholder_names(text) == set(params), key
        assert "[" not in text and "\x1b" not in text, key  # no markup
        if locale != "en-US" and (locale, key) not in _SAME_AS_ENGLISH:
            assert text != source[key], key
        rendered = tr(key, **params)
        assert "{" not in rendered and "}" not in rendered, key
        assert all(str(value) in rendered for value in params.values()), key


def test_same_as_english_allowlist_is_still_needed():
    for locale, key in _SAME_AS_ENGLISH:
        assert catalog.load_catalog(locale)[key] == catalog.load_catalog("en-US")[key]


def test_fr_ca_typography():
    entries = catalog.load_catalog("fr-CA")
    assert "« {server} »" in entries["mcp.startup.not_started"]
    assert "'" not in entries["mcp.startup.not_started"]
    assert entries["mcp.startup.stderr_line"] == "MCP {server} : {line}"


# --------------------------------------------------------------- harnesses

_HOSTILE_NAMES = ("files[/bold]", "x[/cyan]", "[link=https://evil.example]x[/link]")
_HOSTILE_ERROR = "[red]bad[/x] [link=https://evil.example]here[/link]"
_HOSTILE_LINE = "[bold]ERROR[/] {line} {{x}} [/cyan]"
_TRACEBACK_LINE = '  File "srv.py", line 1'


def _render(content):
    """Render through the production renderer, which escapes plain strings."""
    stream = StringIO()
    console = Console(file=stream, width=400, color_system=None)
    message = SimpleNamespace(type=MessageType.INFO, content=content, metadata={})
    _print_message_uncoordinated(console, message)
    return stream.getvalue().rstrip("\n")


class _QueueSink:
    """Stands in for the global queue, *behind* the real emit_* helpers."""

    def __init__(self):
        self.calls = []
        self.threads = []
        self.arrived = threading.Event()

    def emit_simple(self, message_type, content, **metadata):
        self.calls.append((message_type, content, metadata))
        self.threads.append(threading.current_thread())
        self.arrived.set()


@pytest.fixture
def sink(monkeypatch):
    queue = _QueueSink()
    monkeypatch.setattr(message_queue, "get_global_queue", lambda: queue)
    return queue


@pytest.fixture
def emitted(sink):
    return sink.calls


@pytest.fixture
def logs(monkeypatch, tmp_path):
    """Keep blocking_startup's log files inside ``tmp_path``."""
    monkeypatch.setattr(
        blocking_startup, "get_log_file_path", lambda name: tmp_path / "srv.log"
    )
    monkeypatch.setattr(blocking_startup, "rotate_log_if_needed", lambda name: None)
    monkeypatch.setattr(blocking_startup, "write_log", lambda *a, **k: None)
    return tmp_path / "srv.log"


def _echo_stderr(logs, name, *lines):
    """Drive ``StderrFileCapture`` over ``lines`` with echo-to-user on."""
    capture = blocking_startup.StderrFileCapture(name, emit_to_user=True)
    capture.log_path = logs
    logs.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    capture._drain_new_lines()


@pytest.fixture
def fail_start(monkeypatch, logs):
    """Coroutine factory: run ``__aenter__`` for ``name`` and make it fail."""
    monkeypatch.setattr(
        MCPToolset, "__aenter__", AsyncMock(side_effect=RuntimeError("boom"))
    )

    async def run(name):
        server = blocking_startup.BlockingStdioToolset("echo", server_name=name)
        with pytest.raises(RuntimeError):
            await server.__aenter__()

    return run


def _stub_catalog(monkeypatch, **attrs):
    module = ModuleType("code_puppy.mcp_.server_registry_catalog")
    module.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def _raise(error):
    def fail(*_a, **_k):
        raise error

    return fail


def _run_menu(monkeypatch, categories):
    """Run ``run_mcp_install_menu`` with the picker cancelled (Esc)."""
    monkeypatch.setattr(install_menu, "set_awaiting_user_input", lambda _v: None)
    monkeypatch.setattr(menu_session, "menu_session", nullcontext)
    monkeypatch.setattr(install_menu, "run_browse_flow", lambda *_a: None)
    monkeypatch.setattr(install_menu, "load_catalog", lambda: (None, categories))
    assert install_menu.run_mcp_install_menu(manager=None) is False


def _drive_install_menu(monkeypatch):
    _stub_catalog(monkeypatch, catalog=SimpleNamespace(list_categories=lambda: []))
    install_menu.load_catalog()  # no categories

    def missing(name):
        if name == "catalog":
            raise ImportError("boom")
        raise AttributeError(name)

    _stub_catalog(monkeypatch, __getattr__=missing)
    install_menu.load_catalog()  # ImportError
    broken = SimpleNamespace(list_categories=_raise(RuntimeError("boom")))
    _stub_catalog(monkeypatch, catalog=broken)
    install_menu.load_catalog()  # any other error
    _run_menu(monkeypatch, [])  # no catalog


async def _drive_startup(logs, fail_start):
    _echo_stderr(logs, "srv", "listening on stdio", _TRACEBACK_LINE)
    await fail_start("srv")


# ------------------------------------------------------------- goldens

# Written out by hand, in call order. English is the pre-extraction output
# with one deliberate change: main's [cyan]/[/cyan] tags are gone (the
# renderer escapes plain strings, so users saw those tags verbatim).
_GOLDEN_STARTUP = {
    "en-US": [
        "MCP srv: listening on stdio",
        'MCP srv:   File "srv.py", line 1',
        "MCP server 'srv' didn't start. Run /mcp logs srv to investigate, "
        "or unbind it via /agents \u2192 B.",
    ],
    "es": [
        "MCP srv: listening on stdio",
        'MCP srv:   File "srv.py", line 1',
        "El servidor MCP 'srv' no se inici\u00f3. Ejecuta /mcp logs srv para "
        "investigar o desvinc\u00falalo con /agents \u2192 B.",
    ],
    "fr-CA": [
        "MCP srv : listening on stdio",
        'MCP srv :   File "srv.py", line 1',
        "Le serveur MCP \u00ab srv \u00bb n\u2019a pas d\u00e9marr\u00e9. "
        "Ex\u00e9cutez /mcp logs srv pour enqu\u00eater, ou dissociez-le via "
        "/agents \u2192 B.",
    ],
}
_STARTUP_SHAPE = [
    (MessageType.INFO, {}),
    (MessageType.INFO, {}),
    (MessageType.INFO, {"style": "yellow"}),
]

_GOLDEN_INSTALL_MENU = {
    "en-US": [
        "No categories found in server catalog",
        "Server catalog not available: boom",
        "Error loading server catalog: boom",
        "No MCP server catalog available.",
    ],
    "es": [
        "No se encontraron categor\u00edas en el cat\u00e1logo de servidores",
        "El cat\u00e1logo de servidores no est\u00e1 disponible: boom",
        "Error al cargar el cat\u00e1logo de servidores: boom",
        "No hay ning\u00fan cat\u00e1logo de servidores MCP disponible.",
    ],
    "fr-CA": [
        "Aucune cat\u00e9gorie trouv\u00e9e dans le catalogue de serveurs",
        "Catalogue de serveurs non disponible : boom",
        "Erreur de chargement du catalogue de serveurs : boom",
        "Aucun catalogue de serveurs MCP disponible.",
    ],
}
_INSTALL_MENU_TYPES = [MessageType.ERROR] * 3 + [MessageType.WARNING]


def _without_group(metadata):
    return {k: v for k, v in metadata.items() if k != "message_group"}


@pytest.mark.parametrize("locale", sorted(_GOLDEN_STARTUP))
async def test_startup_golden_output(locale, logs, fail_start, emitted):
    translate.set_locale(locale)
    await _drive_startup(logs, fail_start)
    assert [content for _, content, _ in emitted] == _GOLDEN_STARTUP[locale]
    assert all(type(content) is str for _, content, _ in emitted)
    assert [
        (kind, _without_group(metadata)) for kind, _, metadata in emitted
    ] == _STARTUP_SHAPE
    assert all("message_group" in metadata for _, _, metadata in emitted)


@pytest.mark.parametrize("locale", sorted(_GOLDEN_INSTALL_MENU))
def test_install_menu_golden_output(locale, monkeypatch, emitted):
    translate.set_locale(locale)
    _drive_install_menu(monkeypatch)
    assert [content for _, content, _ in emitted] == _GOLDEN_INSTALL_MENU[locale]
    assert [kind for kind, _, _ in emitted] == _INSTALL_MENU_TYPES
    assert all(metadata == {} for _, _, metadata in emitted)


@pytest.mark.parametrize("locale", _LOCALES)
def test_leaving_the_browser_queues_nothing(locale, monkeypatch, emitted):
    """Esc closes the menu silently; no locale may leak a close notice."""
    translate.set_locale(locale)
    _run_menu(monkeypatch, ["custom"])
    assert emitted == []


@pytest.mark.parametrize("locale", _LOCALES)
def test_stderr_echo_thread_uses_the_active_locale(locale, logs, sink):
    """The tail runs on its own thread; the locale is process-wide, not per-thread."""
    translate.set_locale(locale)
    logs.write_text("", encoding="utf-8")
    capture = blocking_startup.StderrFileCapture("srv", emit_to_user=True)
    capture.start()
    with logs.open("a", encoding="utf-8") as handle:
        handle.write("ready\n")
    assert sink.arrived.wait(5)
    capture.stop()
    assert sink.threads[0] is not threading.main_thread()
    assert sink.calls[0][1] == tr("mcp.startup.stderr_line", server="srv", line="ready")


# ---------------------------------------------------------- hostile input


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("name", _HOSTILE_NAMES)
async def test_not_started_renders_hostile_names_literally(
    locale, name, fail_start, emitted
):
    """Regression: main printed raw [cyan] tags; parsing them raises or restyles."""
    translate.set_locale(locale)
    old = f"Run [cyan]/mcp logs {name}[/cyan]."
    try:
        assert f"/mcp logs {name}" not in Text.from_markup(old).plain
    except MarkupError:
        pass
    await fail_start(name)
    rendered = _render(emitted[-1][1])
    assert "[cyan]" not in rendered
    assert rendered == tr(
        "mcp.startup.not_started",
        server=name,
        logs_command=f"/mcp logs {name}",
        agents_command=_AGENTS_COMMAND,
    )
    assert f"/mcp logs {name}" in rendered


@pytest.mark.parametrize("locale", _LOCALES)
def test_stderr_lines_render_literally(locale, logs, emitted):
    """Subprocess output is data: markup and braces must survive untouched."""
    translate.set_locale(locale)
    name = _HOSTILE_NAMES[1]
    _echo_stderr(logs, name, _HOSTILE_LINE)
    content = emitted[0][1]
    assert type(content) is str
    assert content == tr("mcp.startup.stderr_line", server=name, line=_HOSTILE_LINE)
    assert _HOSTILE_LINE in content and _render(content) == content


@pytest.mark.parametrize("locale", _LOCALES)
def test_install_menu_errors_render_literally(locale, monkeypatch, emitted):
    translate.set_locale(locale)
    broken = SimpleNamespace(list_categories=_raise(RuntimeError(_HOSTILE_ERROR)))
    _stub_catalog(monkeypatch, catalog=broken)
    install_menu.load_catalog()
    content = emitted[0][1]
    assert type(content) is str
    assert _render(content) == tr("mcp.install_menu.load_error", error=_HOSTILE_ERROR)
