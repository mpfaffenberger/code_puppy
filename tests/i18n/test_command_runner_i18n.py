"""i18n contract for the shell tool's terminal messages (``tools.shell.*``).

Shortcut names (``Ctrl+X``, ``Ctrl-C``) and stream names (``stdout``) are
passed as placeholders, so a translator can never rename the key the user
must press. Leading newlines are layout and stay at the call site. Results
returned to the model (``ShellCommandOutput``) stay English.
"""

import ast
import signal
import threading
from functools import partial
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from rich.console import Console
from rich.text import Text

from code_puppy.i18n import available_locales, catalog, pseudo, translate
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated
from code_puppy.tools import command_runner

_PREFIX = "tools.shell."
_LOCALES = (*available_locales(), pseudo.PSEUDO_LOCALE)
_ERROR = "[red]boom[/x]"
_REASON = "plugin[/dim][bold]x"
_LOG_NAME = "shell_bg_[bold]x.log"
_PID = 4242
_GROUP = {"message_group": "test-group"}

# key -> the kwargs real callers pass; values carry markup to prove it stays literal.
_REAL_PARAMS = {
    "tools.shell.background_failed": {"error": _ERROR},
    "tools.shell.background_log": {"path": f"/tmp/{_LOG_NAME}"},
    "tools.shell.background_started": {"pid": _PID},
    "tools.shell.backgrounding_all": {"shortcut": "Ctrl+X Ctrl+B"},
    "tools.shell.cleanup_failed": {"error": _ERROR},
    "tools.shell.command_rewritten": {"reason": _REASON},
    "tools.shell.command_rewritten_by_plugin": {},
    "tools.shell.empty_command": {},
    "tools.shell.inactivity_timeout": {},
    "tools.shell.interrupting_all": {"shortcut": "Ctrl+X"},
    "tools.shell.kill_failed": {"error": _ERROR},
    "tools.shell.reader_stuck": {"stream": "stdout"},
    "tools.shell.sigint_interrupting": {"shortcut": "Ctrl-C"},
    "tools.shell.sigint_stopping_agent": {"shortcut": "Ctrl-C"},
}


def _translation_calls():
    tree = ast.parse(Path(command_runner.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):  # also walks into f-string FormattedValues
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"t", "ngettext"}
        ):
            key = node.args[0]
            assert isinstance(key, ast.Constant), ast.dump(node)
            yield key.value, {keyword.arg for keyword in node.keywords}


def test_keys_and_kwargs_match_actual_callers():
    found = {}
    for key, kwargs in _translation_calls():
        assert found.setdefault(key, kwargs) == kwargs, key
    assert found == {key: set(params) for key, params in _REAL_PARAMS.items()}


@pytest.mark.parametrize("locale", available_locales())
def test_catalog_contract(locale):
    """Shell-message contracts; generic sweeps live in test_catalog_namespaces."""
    source = catalog.load_catalog("en-US")
    target = catalog.load_catalog(locale)
    assert {key for key in target if key.startswith(_PREFIX)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        text = target[key]
        assert isinstance(text, str), key
        assert placeholder_names(text) == set(params), key
        # Catalog values are plain text: layout and markup live in code.
        assert text == text.strip() and "[" not in text, key
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace(_ERROR, ""), key
        assert all(str(value) in rendered for value in params.values()), key
        if locale != "en-US":
            assert text != source[key], key
    assert "PID" in target["tools.shell.background_started"]


# Hand-written, NOT derived from the catalog under test: keys that share a
# placeholder set ({shortcut} x4, {error} x3) could otherwise be swapped
# unnoticed, and the wording fixed in review stays pinned.
_TRANSLATIONS = {
    "es": {
        "tools.shell.interrupting_all": "Ctrl+X -- interrumpiendo todos los comandos de shell...",
        "tools.shell.backgrounding_all": "Ctrl+X Ctrl+B -- enviando todos los comandos de shell a segundo plano...",
        "tools.shell.sigint_interrupting": "¡Ctrl-C detectado! Interrumpiendo todos los comandos de shell...",
        "tools.shell.sigint_stopping_agent": "¡Ctrl-C detectado! Deteniendo el agente (shells y todos los subagentes)...",
        "tools.shell.kill_failed": f"Error al forzar la terminación del proceso: {_ERROR}",
        "tools.shell.cleanup_failed": f"Error durante la limpieza del proceso: {_ERROR}",
        "tools.shell.background_failed": f"No se pudo iniciar el proceso en segundo plano: {_ERROR}",
        "tools.shell.command_rewritten_by_plugin": "\U0001f527 comando reescrito por un complemento",
        "tools.shell.inactivity_timeout": "Se forzó la terminación del proceso: se agotó el tiempo de espera por inactividad",
        "tools.shell.background_started": f"Proceso en segundo plano iniciado (PID: {_PID}) - sin tiempo de espera, se ejecuta hasta completarse",
    },
    "fr-CA": {
        "tools.shell.interrupting_all": "Ctrl+X -- interruption de toutes les commandes shell...",
        "tools.shell.backgrounding_all": "Ctrl+X Ctrl+B -- mise en arrière-plan de toutes les commandes shell...",
        "tools.shell.sigint_interrupting": "Ctrl-C détecté! Interruption de toutes les commandes shell...",
        "tools.shell.sigint_stopping_agent": "Ctrl-C détecté! Arrêt de l’agent (shells et tous les sous-agents)...",
        "tools.shell.kill_failed": f"Erreur lors de l’arrêt forcé du processus : {_ERROR}",
        "tools.shell.cleanup_failed": f"Erreur lors du nettoyage du processus : {_ERROR}",
        "tools.shell.background_failed": f"Impossible de démarrer le processus en arrière-plan : {_ERROR}",
        "tools.shell.command_rewritten_by_plugin": "\U0001f527 commande réécrite par un module d’extension",
        "tools.shell.inactivity_timeout": "Processus arrêté de force : délai d’inactivité atteint",
        "tools.shell.background_started": f"Processus en arrière-plan démarré (PID : {_PID}) - sans limite de temps, s’exécute jusqu’à la fin",
    },
}  # fmt: skip


@pytest.mark.parametrize("locale", sorted(_TRANSLATIONS))
def test_hand_written_translations(locale):
    translate.set_locale(locale)
    rendered = {
        key: translate.t(key, **_REAL_PARAMS[key]) for key in _TRANSLATIONS[locale]
    }
    assert rendered == _TRANSLATIONS[locale]  # fmt: skip


# --- driving every call site ------------------------------------------------


class _StuckThread:
    """A reader thread that never finishes, so cleanup has to report it.

    Joins are recorded into ``log`` as ``("join", stream, timeout)``.
    """

    def __init__(self, log, *, target=None, args=(), daemon=None):
        self._log = log
        self._stream = args[2]  # pump(pipe, lines, stream)

    def start(self):
        pass

    def join(self, timeout=None):
        self._log.append(("join", self._stream, timeout))

    def is_alive(self):
        return True


class _IdleProcess:
    """A process that stays silent forever (hashable, unlike SimpleNamespace)."""

    pid = _PID
    stdout = stderr = stdin = None

    def poll(self):
        return None


class _UnkillableProcess:
    @property
    def pid(self):
        raise RuntimeError(_ERROR)

    def poll(self):
        return None


@pytest.fixture
def emitted(monkeypatch, tmp_path):
    calls = []
    for name in ("emit_info", "emit_warning", "emit_error"):
        monkeypatch.setattr(
            command_runner,
            name,
            lambda message, _n=name, **kw: calls.append((_n, message, kw)),
        )
    monkeypatch.setattr(command_runner, "IS_WINDOWS", False)
    monkeypatch.setattr(command_runner, "generate_group_id", lambda *_: "test-group")
    monkeypatch.setattr(command_runner, "get_message_bus", Mock)
    monkeypatch.setattr(command_runner, "kill_all_running_shell_processes", Mock())
    monkeypatch.setattr(command_runner, "request_background_all", Mock())
    monkeypatch.setattr(command_runner, "_tear_down_live_panels", Mock())
    monkeypatch.setattr("code_puppy.config.get_command_timeout_seconds", lambda: 3600)
    log_path = tmp_path / _LOG_NAME
    monkeypatch.setattr(
        command_runner.tempfile,
        "NamedTemporaryFile",
        lambda **_: open(log_path, "w", encoding="utf-8"),
    )
    return SimpleNamespace(calls=calls, log_path=str(log_path))


def _callbacks(monkeypatch, results):
    async def fake(*_args, **_kwargs):
        return results

    monkeypatch.setattr("code_puppy.callbacks.on_run_shell_command", fake)


def _popen(monkeypatch, behaviour):
    monkeypatch.setattr(command_runner.subprocess, "Popen", behaviour)


def _stream_idle_process(monkeypatch, silent=False, log=None):
    """Inactivity path with reader threads that refuse to stop."""
    log = [] if log is None else log
    monkeypatch.setattr(
        command_runner,
        "threading",
        SimpleNamespace(Event=threading.Event, Thread=partial(_StuckThread, log)),
    )
    return command_runner.run_shell_command_streaming(
        _IdleProcess(),
        timeout=-1,
        command="sleep",
        group_id="test-group",
        silent=silent,
    )


async def _drive_every_call_site(monkeypatch):
    results = []
    command_runner._handle_ctrl_x_press()
    command_runner._handle_ctrl_b_press()
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", Mock())
    monkeypatch.setattr(command_runner, "_SIGINT_CANCEL_REQUESTED", False)
    command_runner._shell_sigint_handler(signal.SIGINT, None)
    command_runner._shell_sigint_handler(signal.SIGINT, None)  # deduped: silent
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", None)
    monkeypatch.setattr(command_runner, "_SIGINT_CANCEL_REQUESTED", False)
    command_runner._shell_sigint_handler(signal.SIGINT, None)
    command_runner._kill_process_group(_UnkillableProcess())

    _callbacks(
        monkeypatch,
        [
            {"rewrite": "echo bye", "rewrite_reason": _REASON},
            {"rewrite": "echo ciao"},  # no reason: the plugin fallback
        ],
    )
    _popen(monkeypatch, lambda *_, **__: SimpleNamespace(pid=_PID))
    results.append(
        await command_runner.run_shell_command(MagicMock(), "echo hi", background=True)
    )
    _callbacks(monkeypatch, [])
    _popen(monkeypatch, Mock(side_effect=RuntimeError(_ERROR)))
    results.append(
        await command_runner.run_shell_command(MagicMock(), "echo hi", background=True)
    )
    results.append(await command_runner.run_shell_command(MagicMock(), "   "))

    monkeypatch.setattr(command_runner, "_kill_process_group", Mock())
    results.append(_stream_idle_process(monkeypatch))
    monkeypatch.setattr(
        command_runner, "_kill_process_group", Mock(side_effect=RuntimeError(_ERROR))
    )
    results.append(_stream_idle_process(monkeypatch))
    return results


def _shape(message):
    """Compare Text by what the renderer sees: plain text, style, no spans."""
    if isinstance(message, Text):
        return ("Text", message.plain, str(message.style), message.spans)
    return message


def _plain(message):
    return message.plain if isinstance(message, Text) else message


def _dim(plain):
    return ("Text", plain, "dim", [])


def _legacy_english(log_path):
    """Pre-extraction English for every call site driven above, in order.

    The one deliberate change: the rewrite notice used to be the *string*
    "[dim]\U0001f527 command rewritten by ...[/dim]", which the renderer
    escapes, so users saw the literal "[dim]" tags. It is now dim Text.
    """
    return [
        ("emit_warning", "\nCtrl+X -- interrupting all shell commands...", {}),
        ("emit_warning", "\nCtrl+X Ctrl+B -- backgrounding all shell commands...", {}),
        ("emit_warning", "\nCtrl-C detected! Stopping the agent (shells + all sub-agents)...", {}),
        ("emit_warning", "\nCtrl-C detected! Interrupting all shell commands...", {}),
        ("emit_error", f"Kill process error: {_ERROR}", {}),
        ("emit_info", _dim(f"\U0001f527 command rewritten by {_REASON}"), {}),
        ("emit_info", _dim("\U0001f527 command rewritten by plugin"), {}),
        ("emit_info", f"Background process started (PID: {_PID}) - no timeout, runs until complete", {}),
        ("emit_info", f"Output logging to: {log_path}", {}),
        ("emit_error", f"Failed to start background process: {_ERROR}", {}),
        ("emit_error", "Command cannot be empty", _GROUP),
        ("emit_error", "Process killed: inactivity timeout reached", _GROUP),
        ("emit_warning", "stdout reader thread failed to terminate after inactivity timeout", _GROUP),
        ("emit_warning", "stderr reader thread failed to terminate after inactivity timeout", _GROUP),
        ("emit_error", "Process killed: inactivity timeout reached", _GROUP),
        ("emit_warning", f"Error during process cleanup: {_ERROR}", _GROUP),
    ]  # fmt: skip


def _expected_calls(log_path):
    """_legacy_english rebuilt from the active catalog (pinned by that list)."""
    t = translate.t
    s = _PREFIX
    return [
        ("emit_warning", "\n" + t(f"{s}interrupting_all", shortcut="Ctrl+X"), {}),
        ("emit_warning", "\n" + t(f"{s}backgrounding_all", shortcut="Ctrl+X Ctrl+B"), {}),
        ("emit_warning", "\n" + t(f"{s}sigint_stopping_agent", shortcut="Ctrl-C"), {}),
        ("emit_warning", "\n" + t(f"{s}sigint_interrupting", shortcut="Ctrl-C"), {}),
        ("emit_error", t(f"{s}kill_failed", error=_ERROR), {}),
        ("emit_info", _dim(t(f"{s}command_rewritten", reason=_REASON)), {}),
        ("emit_info", _dim(t(f"{s}command_rewritten_by_plugin")), {}),
        ("emit_info", t(f"{s}background_started", pid=_PID), {}),
        ("emit_info", t(f"{s}background_log", path=log_path), {}),
        ("emit_error", t(f"{s}background_failed", error=_ERROR), {}),
        ("emit_error", t(f"{s}empty_command"), _GROUP),
        ("emit_error", t(f"{s}inactivity_timeout"), _GROUP),
        ("emit_warning", t(f"{s}reader_stuck", stream="stdout"), _GROUP),
        ("emit_warning", t(f"{s}reader_stuck", stream="stderr"), _GROUP),
        ("emit_error", t(f"{s}inactivity_timeout"), _GROUP),
        ("emit_warning", t(f"{s}cleanup_failed", error=_ERROR), _GROUP),
    ]  # fmt: skip


def _shaped(calls):
    return [(name, _shape(message), kwargs) for name, message, kwargs in calls]


async def test_english_call_sites_match_pre_extraction_output(monkeypatch, emitted):
    await _drive_every_call_site(monkeypatch)
    assert _shaped(emitted.calls) == _legacy_english(emitted.log_path)


@pytest.mark.parametrize("locale", _LOCALES)
async def test_call_sites_emit_translated_messages(locale, monkeypatch, emitted):
    translate.set_locale(locale)
    results = await _drive_every_call_site(monkeypatch)
    assert _shaped(emitted.calls) == _expected_calls(emitted.log_path)
    for _, message, _ in emitted.calls:
        is_rewrite_notice = isinstance(message, Text)
        assert is_rewrite_notice or type(message) is str
    assert sum(isinstance(message, Text) for _, message, _ in emitted.calls) == 2
    if locale != pseudo.PSEUDO_LOCALE:  # en-XA accents the interpolated values too
        text = "\n".join(_plain(message) for _, message, _ in emitted.calls)
        literals = ("\nCtrl+X ", "\nCtrl+X Ctrl+B ", "Ctrl-C", "PID", "stdout ")
        literals += ("stderr ", _REASON, _ERROR, emitted.log_path)
        for literal in literals:
            assert literal in text, literal
    # Model-facing results stay English.
    background, failed, empty, idle, broken = results
    assert background.background is True and background.pid == _PID
    assert background.command == "echo ciao"
    assert failed.error == f"Failed to start background process: {_ERROR}"
    assert empty.error == "Command cannot be empty"
    assert idle.error == broken.error == "Command timed out after -1 seconds"


_LEVELS = {
    "emit_info": (MessageType.INFO, None),
    "emit_warning": (MessageType.WARNING, "\x1b[33m"),
    "emit_error": (MessageType.ERROR, "\x1b[1;31m"),
}


def _render(message_type, content, color):
    stream = StringIO()
    console = Console(
        file=stream,
        width=400,
        force_terminal=color,
        color_system="truecolor" if color else None,
    )
    message = SimpleNamespace(type=message_type, content=content, metadata={})
    _print_message_uncoordinated(console, message)
    return stream.getvalue()


@pytest.mark.parametrize("locale", _LOCALES)
async def test_production_renderer_keeps_hostile_text_literal(
    locale, monkeypatch, emitted
):
    translate.set_locale(locale)
    await _drive_every_call_site(monkeypatch)
    for name, message, _ in emitted.calls:
        message_type, colour = _LEVELS[name]
        plain = _plain(message)
        assert _render(message_type, message, color=False) == plain + "\n"
        coloured = _render(message_type, message, color=True)
        if colour:
            assert colour in coloured, (name, plain)
    rewrite = next(m for _, m, _ in emitted.calls if isinstance(m, Text))
    coloured = _render(MessageType.INFO, rewrite, color=True)
    assert "\x1b[2m" in coloured  # dim, as before the extraction
    if locale != pseudo.PSEUDO_LOCALE:
        assert _REASON in _render(MessageType.INFO, rewrite, color=False)


# --- locale honoured in the contexts these messages really fire from --------


def test_real_sigint_delivery_uses_the_active_locale(monkeypatch, emitted):
    """The handler runs from a real signal, not a direct call."""
    translate.set_locale("fr-CA")
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", None)
    monkeypatch.setattr(command_runner, "_SIGINT_CANCEL_REQUESTED", False)
    previous = signal.signal(signal.SIGINT, command_runner._shell_sigint_handler)
    try:
        signal.raise_signal(signal.SIGINT)
    finally:
        signal.signal(signal.SIGINT, previous)
    assert emitted.calls == [
        (
            "emit_warning",
            "\nCtrl-C détecté! Interruption de toutes les commandes shell...",
            {},
        )
    ]


def test_worker_threads_use_the_active_locale(monkeypatch, emitted):
    """Chord callbacks fire on the key-listener thread and streaming runs in
    the shell executor; the translator is process-wide, not a ContextVar."""
    translate.set_locale("es")
    monkeypatch.setattr(command_runner, "_kill_process_group", Mock())

    def work():
        command_runner._handle_ctrl_x_press()
        _stream_idle_process(monkeypatch)

    worker = threading.Thread(target=work)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert [message for _, message, _ in emitted.calls] == [
        "\nCtrl+X -- interrumpiendo todos los comandos de shell...",
        "Se forzó la terminación del proceso: se agotó el tiempo de espera por inactividad",
        "El hilo lector de stdout no terminó tras agotarse el tiempo de espera por inactividad",
        "El hilo lector de stderr no terminó tras agotarse el tiempo de espera por inactividad",
    ]  # fmt: skip


def test_silent_streaming_emits_nothing(monkeypatch, emitted):
    """Sub-agent (silent) shells stay quiet: stuck readers and cleanup errors."""
    translate.set_locale("fr-CA")
    monkeypatch.setattr(command_runner, "_kill_process_group", Mock())
    stuck = _stream_idle_process(monkeypatch, silent=True)
    monkeypatch.setattr(
        command_runner, "_kill_process_group", Mock(side_effect=RuntimeError(_ERROR))
    )
    broken = _stream_idle_process(monkeypatch, silent=True)
    assert stuck.timeout is True and broken.timeout is True
    assert emitted.calls == []


@pytest.mark.parametrize(
    ("extra", "english", "french"),
    [
        # Absent reason: the only case that ever fell back to "plugin".
        ({}, "command rewritten by plugin", "commande réécrite par un module d’extension"),
        # Present reasons pass through as given, exactly as on main.
        ({"rewrite_reason": ""}, "command rewritten by ", "commande réécrite par "),
        ({"rewrite_reason": None}, "command rewritten by None", "commande réécrite par None"),
    ],
)  # fmt: skip
async def test_rewrite_reason_fallback_matches_main(
    extra, english, french, monkeypatch, emitted
):
    _callbacks(monkeypatch, [{"rewrite": "echo bye", **extra}])
    _popen(monkeypatch, lambda *_, **__: SimpleNamespace(pid=_PID))
    for locale in ("en-US", "fr-CA"):
        translate.set_locale(locale)
        await command_runner.run_shell_command(MagicMock(), "echo hi", background=True)
    rewrites = [_shape(m) for _, m, _ in emitted.calls if isinstance(m, Text)]
    assert rewrites == [_dim(f"\U0001f527 {english}"), _dim(f"\U0001f527 {french}")]


def test_cleanup_joins_each_stuck_reader_before_closing_pipes(monkeypatch, emitted):
    """Closing a pipe under a live reader can deadlock: joins come first."""
    log = []
    real_close = command_runner._close_pipes

    def close(process, readers=()):
        log.append(("close",))
        return real_close(process, readers)

    monkeypatch.setattr(command_runner, "_close_pipes", close)
    monkeypatch.setattr(command_runner, "_kill_process_group", Mock())
    _stream_idle_process(monkeypatch, log=log)
    assert log == [("join", "stdout", 3), ("join", "stderr", 3), ("close",)]
