"""i18n contract for the browser script and workflow tools.

Banners keep the tool-argument echo (``direction=down amount=3``) out of the
catalog: translators get a ``{details}`` placeholder, so argument names and
values are never translated.  Scroll directions and wait states are whole
sentences per value, so no English token is spliced into a translation.
Tool results returned to the model stay English.
"""

import ast
import typing
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Locator
from rich.console import Console

from code_puppy.i18n import available_locales, catalog, ngettext, pseudo, translate
from code_puppy.i18n import t as tr
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated
from code_puppy.tools.browser import browser_scripts as scripts
from code_puppy.tools.browser import browser_workflows as workflows

_PREFIX = "browser.automation."
_MODULES = (scripts, workflows)
_EMITTERS = ("emit_info", "emit_success", "emit_warning", "emit_error")
_LOCALES = (*available_locales(), pseudo.PSEUDO_LOCALE)
_DIRECTIONS = ("down", "up", "left", "right")
_STATES = ("visible", "hidden", "attached", "detached")
# Hostile values: markup must reach the terminal literally.
_SEL = "#go[/red]"
_ERROR = "[red]boom[/x]"
_NAME = "My Flow[/b]"
_SCRIPT = "x" * 95 + "[b]ok[/b]"  # 104 chars: the banner echo is truncated

# key -> real kwargs (``count`` marks a plural key). One row per catalog key.
_REAL_PARAMS = {
    **{
        f"{_PREFIX}{banner}": {"details": f"selector='{_SEL}'"}
        for banner in (
            "execute_js",
            "scroll",
            "scroll_to_element",
            "set_viewport",
            "wait_for_element",
            "highlight_element",
            "save_workflow",
            "read_workflow",
        )
    },
    f"{_PREFIX}clear_highlights": {},
    f"{_PREFIX}list_workflows": {},
    f"{_PREFIX}js_executed": {},
    f"{_PREFIX}js_failed": {"error": _ERROR},
    **{f"{_PREFIX}scrolled_page_{d}": {} for d in _DIRECTIONS},
    **{f"{_PREFIX}scrolled_element_{d}": {"selector": _SEL} for d in _DIRECTIONS},
    f"{_PREFIX}scroll_direction_unknown": {"direction": "sideways[/b]"},
    f"{_PREFIX}scrolled_to_element": {"selector": _SEL},
    f"{_PREFIX}viewport_set": {"size": "1280x720"},
    **{f"{_PREFIX}element_now_{s}": {"selector": _SEL} for s in _STATES},
    f"{_PREFIX}element_highlighted": {"selector": _SEL},
    f"{_PREFIX}highlights_cleared": {"count": 2},
    f"{_PREFIX}workflow_saved": {"path": "/tmp/[b]flow.md"},
    f"{_PREFIX}workflow_save_failed": {"error": _ERROR},
    f"{_PREFIX}workflow_unreadable": {"path": "/tmp/[b]flow.md", "error": _ERROR},
    f"{_PREFIX}workflows_found": {"count": 2},
    f"{_PREFIX}workflows_list_failed": {"error": _ERROR},
    f"{_PREFIX}workflow_not_found": {"name": _NAME},
    f"{_PREFIX}workflow_read": {"count": 2},
    f"{_PREFIX}workflow_read_failed": {"error": _ERROR},
}
_PLURAL = {key for key, params in _REAL_PARAMS.items() if "count" in params}
_PAGE_SCROLLED = {f"{_PREFIX}scrolled_page_{d}" for d in _DIRECTIONS}
_ELEMENT_SCROLLED = {f"{_PREFIX}scrolled_element_{d}" for d in _DIRECTIONS}
_WAIT_STATES = {f"{_PREFIX}element_now_{s}" for s in _STATES}
# Sentence maps in browser_scripts -> the catalog keys they may hold. Which key
# each call actually emits is pinned by the golden output, not by reading code.
_MAPS = {
    "_PAGE_SCROLLED_KEYS": _PAGE_SCROLLED,
    "_ELEMENT_SCROLLED_KEYS": _ELEMENT_SCROLLED,
    "_WAIT_STATE_KEYS": _WAIT_STATES,
}
_MAPPED = set().union(*_MAPS.values())


@pytest.fixture(autouse=True)
def _reset_locale():
    yield
    translate.set_locale("en-US")


def _translation_calls(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("t", "ngettext")
            and node.args
        ):
            kwargs = {keyword.arg for keyword in node.keywords}
            if node.func.id == "ngettext":
                kwargs.add("count")
            yield node.func.id, node.args[0], kwargs


def test_keys_and_kwargs_match_actual_callers():
    literal = {}
    for module in _MODULES:
        for func, key_node, kwargs in _translation_calls(module):
            if isinstance(key_node, ast.Constant):
                key = key_node.value
                assert literal.setdefault(key, kwargs) == kwargs, key
                assert (func == "ngettext") == (key in _PLURAL), key
            else:
                # Any computed key is a lookup in one of the sentence maps.
                assert func == "t", ast.unparse(key_node)
                assert isinstance(key_node, ast.Subscript), ast.unparse(key_node)
                assert ast.unparse(key_node.value) in _MAPS, ast.unparse(key_node)
    assert set(literal) | _MAPPED == set(_REAL_PARAMS)
    assert not set(literal) & _MAPPED
    for key, kwargs in literal.items():
        assert kwargs == set(_REAL_PARAMS[key]), key


def test_message_maps_cover_the_supported_values():
    # Both scroll maps cover the four supported directions.
    assert scripts._PAGE_SCROLLED_KEYS == {
        d: f"{_PREFIX}scrolled_page_{d}" for d in _DIRECTIONS
    }
    assert scripts._ELEMENT_SCROLLED_KEYS == {
        d: f"{_PREFIX}scrolled_element_{d}" for d in _DIRECTIONS
    }
    # Playwright accepts only these states, so the lookup cannot miss.
    (literal,) = (
        arg
        for arg in typing.get_args(typing.get_type_hints(Locator.wait_for)["state"])
        if typing.get_origin(arg) is typing.Literal
    )
    assert set(typing.get_args(literal)) == set(_STATES)
    assert scripts._WAIT_STATE_KEYS == {s: f"{_PREFIX}element_now_{s}" for s in _STATES}


# Hand-checked translations of the per-value sentences, so a translation that
# names the wrong direction or state is caught (English is pinned below).
_PINNED_SENTENCES = {
    "es": {
        "scrolled_page_down": "Se desplazó la página hacia abajo",
        "scrolled_page_up": "Se desplazó la página hacia arriba",
        "scrolled_page_left": "Se desplazó la página hacia la izquierda",
        "scrolled_page_right": "Se desplazó la página hacia la derecha",
        "scrolled_element_down": f"Se desplazó el elemento '{_SEL}' hacia abajo",
        "scrolled_element_up": f"Se desplazó el elemento '{_SEL}' hacia arriba",
        "scrolled_element_left": f"Se desplazó el elemento '{_SEL}' hacia la izquierda",
        "scrolled_element_right": f"Se desplazó el elemento '{_SEL}' hacia la derecha",
        "element_now_visible": f"El elemento {_SEL} ahora está visible",
        "element_now_hidden": f"El elemento {_SEL} ahora está oculto",
        "element_now_attached": f"El elemento {_SEL} ya está en el DOM",
        "element_now_detached": f"El elemento {_SEL} ya no está en el DOM",
    },
    "fr-CA": {
        "scrolled_page_down": "Défilement de la page vers le bas",
        "scrolled_page_up": "Défilement de la page vers le haut",
        "scrolled_page_left": "Défilement de la page vers la gauche",
        "scrolled_page_right": "Défilement de la page vers la droite",
        "scrolled_element_down": f"Défilement de l’élément « {_SEL} » vers le bas",
        "scrolled_element_up": f"Défilement de l’élément « {_SEL} » vers le haut",
        "scrolled_element_left": f"Défilement de l’élément « {_SEL} » vers la gauche",
        "scrolled_element_right": f"Défilement de l’élément « {_SEL} » vers la droite",
        "element_now_visible": f"L’élément {_SEL} est maintenant visible",
        "element_now_hidden": f"L’élément {_SEL} est maintenant masqué",
        "element_now_attached": f"L’élément {_SEL} est maintenant dans le DOM",
        "element_now_detached": f"L’élément {_SEL} n’est plus dans le DOM",
    },
}  # fmt: skip


@pytest.mark.parametrize("locale", sorted(_PINNED_SENTENCES))
def test_direction_and_state_sentences_say_the_right_thing(locale):
    pinned = _PINNED_SENTENCES[locale]
    assert {f"{_PREFIX}{suffix}" for suffix in pinned} == _MAPPED
    translate.set_locale(locale)
    rendered = {suffix: tr(f"{_PREFIX}{suffix}", selector=_SEL) for suffix in pinned}
    assert rendered == pinned


@pytest.mark.parametrize("locale", available_locales())
def test_catalog_contract(locale):
    source = catalog.load_catalog("en-US")
    target = catalog.load_catalog(locale)
    assert {key for key in target if key.startswith(_PREFIX)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        plural = key in _PLURAL
        forms = ("one", "other") if plural else (None,)
        if plural:
            assert set(target[key]) == set(forms), key
        for form in forms:
            text = target[key][form] if plural else target[key]
            assert placeholder_names(text) == set(params), (key, form)
            if "details" in params:
                # The argument echo is its own trailing segment: no translated
                # text may be glued to it (e.g. "nom={details}").
                assert text.endswith(" {details}"), (key, text)
            if locale != "en-US":
                english = source[key][form] if plural else source[key]
                assert text != english, (key, form)
        kwargs = {k: v for k, v in params.items() if k != "count"}
        # 0 matters: French uses the "one" form for it.
        for count in (0, 1, 2) if plural else (None,):
            rendered = ngettext(key, count, **kwargs) if plural else tr(key, **kwargs)
            assert "{" not in rendered and "}" not in rendered, key
            assert all(str(value) in rendered for value in kwargs.values()), key


# English for counts 0, 1, 2: the singular is new ("1 highlights" before).
_ENGLISH_PLURALS = {
    f"{_PREFIX}highlights_cleared": (
        "Cleared 0 highlights",
        "Cleared 1 highlight",
        "Cleared 2 highlights",
    ),
    f"{_PREFIX}workflows_found": (
        "Found 0 workflows",
        "Found 1 workflow",
        "Found 2 workflows",
    ),
    f"{_PREFIX}workflow_read": (
        "Workflow read successfully: 0 characters",
        "Workflow read successfully: 1 character",
        "Workflow read successfully: 2 characters",
    ),
}


@pytest.mark.parametrize("key", sorted(_PLURAL))
def test_english_plural_forms(key):
    translate.set_locale("en-US")
    assert tuple(ngettext(key, n) for n in (0, 1, 2)) == _ENGLISH_PLURALS[key]


# ---------------------------------------------------------------- call sites


@pytest.fixture
def env(monkeypatch, tmp_path):
    element = AsyncMock()
    element.evaluate.return_value = {"clientHeight": 300}
    page = AsyncMock()
    page.locator = MagicMock(return_value=SimpleNamespace(first=element))
    page.evaluate.return_value = 600
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    calls = []
    monkeypatch.setattr(scripts, "get_session_browser_manager", lambda: manager)
    monkeypatch.setattr(workflows.config, "DATA_DIR", str(tmp_path))
    for module in _MODULES:
        monkeypatch.setattr(module, "generate_group_id", lambda *_: "g")
        for name in _EMITTERS:
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **kw: calls.append((_n, message, kw)),
                )
    return SimpleNamespace(
        calls=calls,
        page=page,
        monkeypatch=monkeypatch,
        flows=tmp_path / "browser_workflows",
    )


def _unreadable(name):
    """Path.stat that fails for one file, as a vanished or locked file would."""
    real_stat = Path.stat

    def stat(self, *args, **kwargs):
        if self.name == name:
            raise PermissionError(_ERROR)
        return real_stat(self, *args, **kwargs)

    return stat


def _fail(*_args, **_kwargs):
    raise RuntimeError(_ERROR)


async def _drive_every_call_site(env):
    run = {"js": await scripts.execute_javascript(_SCRIPT)}
    for d in _DIRECTIONS:
        run[f"page_{d}"] = await scripts.scroll_page(d)
        run[f"element_{d}"] = await scripts.scroll_page(d, 2, _SEL)
    run["upper"] = await scripts.scroll_page("DOWN")
    run["element_upper"] = await scripts.scroll_page("UP", 2, _SEL)
    run["unknown"] = await scripts.scroll_page("sideways[/b]")
    run["to_element"] = await scripts.scroll_to_element(_SEL)
    run["viewport"] = await scripts.set_viewport_size(1280, 720)
    for state in _STATES:
        run[f"wait_{state}"] = await scripts.wait_for_element(_SEL, state, 5)
    run["highlight"] = await scripts.highlight_element(_SEL, "blue")
    env.page.evaluate.return_value = 1
    run["clear_1"] = await scripts.clear_highlights()
    env.page.evaluate.return_value = 0
    run["clear_0"] = await scripts.clear_highlights()
    env.page.evaluate.side_effect = RuntimeError(_ERROR)
    run["js_failed"] = await scripts.execute_javascript("1")

    run["list_0"] = await workflows.list_workflows()  # no directory yet
    run["save"] = await workflows.save_workflow(_NAME, "abc")
    run["list_1"] = await workflows.list_workflows()
    run["save_one"] = await workflows.save_workflow("one", "x")
    (env.flows / "broken.md").write_text("", encoding="utf-8")
    with env.monkeypatch.context() as patch:
        patch.setattr(Path, "stat", _unreadable("broken.md"))
        run["list_2"] = await workflows.list_workflows()
    run["read"] = await workflows.read_workflow("my-flow--b")
    run["read_one"] = await workflows.read_workflow("one.md")
    run["missing"] = await workflows.read_workflow("missing[/x]")
    env.monkeypatch.setattr(workflows, "get_workflows_directory", _fail)
    run["save_failed"] = await workflows.save_workflow(_NAME, "abc")
    run["list_failed"] = await workflows.list_workflows()
    run["read_failed"] = await workflows.read_workflow("one")
    return run


def _golden_english(flows):
    """Pre-extraction English, written out by hand, plus the declared changes:
    singular counts, a lowercased direction, and the unknown-direction warning.
    """
    return [
        ("emit_info", f"BROWSER EXECUTE JS \U0001f4dc script='{'x' * 95}[b]ok...'"),
        ("emit_success", "JavaScript executed successfully"),
        ("emit_info", "BROWSER SCROLL direction=down amount=3 target='page'"),
        ("emit_success", "Scrolled page down"),
        ("emit_info", f"BROWSER SCROLL direction=down amount=2 target='{_SEL}'"),
        ("emit_success", f"Scrolled element '{_SEL}' down"),
        ("emit_info", "BROWSER SCROLL direction=up amount=3 target='page'"),
        ("emit_success", "Scrolled page up"),
        ("emit_info", f"BROWSER SCROLL direction=up amount=2 target='{_SEL}'"),
        ("emit_success", f"Scrolled element '{_SEL}' up"),
        ("emit_info", "BROWSER SCROLL direction=left amount=3 target='page'"),
        ("emit_success", "Scrolled page left"),
        ("emit_info", f"BROWSER SCROLL direction=left amount=2 target='{_SEL}'"),
        ("emit_success", f"Scrolled element '{_SEL}' left"),
        ("emit_info", "BROWSER SCROLL direction=right amount=3 target='page'"),
        ("emit_success", "Scrolled page right"),
        ("emit_info", f"BROWSER SCROLL direction=right amount=2 target='{_SEL}'"),
        ("emit_success", f"Scrolled element '{_SEL}' right"),
        ("emit_info", "BROWSER SCROLL direction=DOWN amount=3 target='page'"),
        ("emit_success", "Scrolled page down"),  # was "Scrolled page DOWN"
        ("emit_info", f"BROWSER SCROLL direction=UP amount=2 target='{_SEL}'"),
        ("emit_success", f"Scrolled element '{_SEL}' up"),  # was "... UP"
        ("emit_info", "BROWSER SCROLL direction=sideways[/b] amount=3 target='page'"),
        # was emit_success("Scrolled page sideways[/b]"), though nothing scrolled
        ("emit_warning", "Unknown scroll direction: 'sideways[/b]'"),
        ("emit_info", f"BROWSER SCROLL TO ELEMENT \U0001f3af selector='{_SEL}'"),
        ("emit_success", f"Scrolled to element: {_SEL}"),
        ("emit_info", "BROWSER SET VIEWPORT \U0001f5a5\ufe0f size=1280x720"),
        ("emit_success", "Set viewport size to 1280x720"),
        ("emit_info", f"BROWSER WAIT FOR ELEMENT selector='{_SEL}' state=visible timeout=5ms"),
        ("emit_success", f"Element {_SEL} is now visible"),
        ("emit_info", f"BROWSER WAIT FOR ELEMENT selector='{_SEL}' state=hidden timeout=5ms"),
        ("emit_success", f"Element {_SEL} is now hidden"),
        ("emit_info", f"BROWSER WAIT FOR ELEMENT selector='{_SEL}' state=attached timeout=5ms"),
        ("emit_success", f"Element {_SEL} is now attached"),
        ("emit_info", f"BROWSER WAIT FOR ELEMENT selector='{_SEL}' state=detached timeout=5ms"),
        ("emit_success", f"Element {_SEL} is now detached"),
        ("emit_info", f"BROWSER HIGHLIGHT ELEMENT \U0001f526 selector='{_SEL}' color=blue"),
        ("emit_success", f"Highlighted element: {_SEL}"),
        ("emit_info", "BROWSER CLEAR HIGHLIGHTS \U0001f9f9"),
        ("emit_success", "Cleared 1 highlight"),  # was "Cleared 1 highlights"
        ("emit_info", "BROWSER CLEAR HIGHLIGHTS \U0001f9f9"),
        ("emit_success", "Cleared 0 highlights"),
        ("emit_info", "BROWSER EXECUTE JS \U0001f4dc script='1'"),
        ("emit_error", f"JavaScript execution failed: {_ERROR}"),
        ("emit_info", "LIST WORKFLOWS"),
        ("emit_success", "Found 0 workflows"),  # was "Found 0 workflow(s)"
        ("emit_info", f"SAVE WORKFLOW \U0001f4be name='{_NAME}'"),
        ("emit_success", f"Workflow saved successfully: {flows / 'my-flow--b.md'}"),
        ("emit_info", "LIST WORKFLOWS"),
        ("emit_success", "Found 1 workflow"),  # was "Found 1 workflow(s)"
        ("emit_info", "SAVE WORKFLOW \U0001f4be name='one'"),
        ("emit_success", f"Workflow saved successfully: {flows / 'one.md'}"),
        ("emit_info", "LIST WORKFLOWS"),
        ("emit_warning", f"Could not read {flows / 'broken.md'}: {_ERROR}"),
        ("emit_success", "Found 2 workflows"),  # was "Found 2 workflow(s)"
        ("emit_info", "READ WORKFLOW name='my-flow--b'"),
        ("emit_success", "Workflow read successfully: 3 characters"),
        ("emit_info", "READ WORKFLOW name='one.md'"),
        # was "Workflow read successfully: 1 characters"
        ("emit_success", "Workflow read successfully: 1 character"),
        ("emit_info", "READ WORKFLOW name='missing[/x]'"),
        ("emit_error", "Workflow not found: missing[/x].md"),
        ("emit_info", f"SAVE WORKFLOW \U0001f4be name='{_NAME}'"),
        ("emit_error", f"Failed to save workflow: {_ERROR}"),
        ("emit_info", "LIST WORKFLOWS"),
        ("emit_error", f"Failed to list workflows: {_ERROR}"),
        ("emit_info", "READ WORKFLOW name='one'"),
        ("emit_error", f"Failed to read workflow: {_ERROR}"),
    ]  # fmt: skip


async def test_english_golden_output(env):
    translate.set_locale("en-US")
    await _drive_every_call_site(env)
    emitted = [(name, message) for name, message, _ in env.calls]
    assert emitted == _golden_english(env.flows)


@pytest.mark.parametrize("locale", _LOCALES)
async def test_every_locale_emits_plain_strings_and_english_results(locale, env):
    translate.set_locale(locale)
    run = await _drive_every_call_site(env)
    golden = _golden_english(env.flows)
    assert [name for name, _, _ in env.calls] == [name for name, _ in golden]
    for (_, message, kwargs), (_, english) in zip(env.calls, golden):
        assert type(message) is str  # the renderer escapes it
        assert "{" not in message and "}" not in message
        # The unreadable-file warning never had a message group.
        unreadable = english.startswith("Could not read ")
        assert kwargs == ({} if unreadable else {"message_group": "g"})
    if locale in ("es", "fr-CA"):
        # Every message is translated, including each use of a shared key.
        for (name, message, _), golden_call in zip(env.calls, golden):
            assert (name, message) != golden_call
    # Argument echoes are never translated (en-XA accents whole strings).
    if locale != pseudo.PSEUDO_LOCALE:
        # Data in a message (selectors, names, errors, paths) survives as-is.
        for (_, message, _), (_, english) in zip(env.calls, golden):
            for value in (_SEL, _ERROR, _NAME, "1280x720", str(env.flows)):
                if value in english:
                    assert value in message, (value, message)
        banners = [m for name, m, _ in env.calls if name == "emit_info"]
        for echo in (
            f"script='{'x' * 95}[b]ok...'",
            "direction=left amount=3 target='page'",
            f"direction=up amount=2 target='{_SEL}'",
            "direction=sideways[/b] amount=3 target='page'",
            f"selector='{_SEL}'",
            "size=1280x720",
            f"selector='{_SEL}' state=attached timeout=5ms",
            f"selector='{_SEL}' color=blue",
            f"name='{_NAME}'",
            "name='missing[/x]'",
        ):
            assert any(echo in banner for banner in banners), echo
    # Results returned to the model stay English in every locale.
    assert run["js"] == {"success": True, "script": _SCRIPT, "result": 600}
    assert run["element_up"] == {
        "success": True,
        "direction": "up",
        "amount": 2,
        "target": f"element '{_SEL}'",
        "scroll_position": 600,
    }
    assert run["unknown"] == {
        "success": True,
        "direction": "sideways[/b]",
        "amount": 3,
        "target": "page",
        "scroll_position": 600,
    }
    assert run["viewport"] == {"success": True, "width": 1280, "height": 720}
    assert run["wait_hidden"] == {"success": True, "selector": _SEL, "state": "hidden"}
    assert run["clear_1"] == {"success": True, "cleared_count": 1}
    assert run["js_failed"] == {"success": False, "error": _ERROR, "script": "1"}
    assert run["list_2"]["count"] == 2
    assert run["read_one"]["size"] == 1
    assert run["missing"] == {
        "success": False,
        "error": "Workflow 'missing[/x].md' not found",
        "name": "missing[/x].md",
    }
    assert run["save_failed"] == {"success": False, "error": _ERROR, "name": _NAME}
    assert run["list_failed"] == {"success": False, "error": _ERROR}
    assert run["read_failed"] == {"success": False, "error": _ERROR, "name": "one"}


_LEVELS = {
    "emit_info": (MessageType.INFO, None),
    "emit_success": (MessageType.SUCCESS, "\x1b[32m"),
    "emit_warning": (MessageType.WARNING, "\x1b[33m"),
    "emit_error": (MessageType.ERROR, "\x1b[1;31m"),
}


def _render(message_type, content, color):
    stream = StringIO()
    console = Console(
        file=stream,
        width=1000,
        force_terminal=color,
        color_system="truecolor" if color else None,
    )
    message = SimpleNamespace(type=message_type, content=content, metadata={})
    _print_message_uncoordinated(console, message)
    return stream.getvalue()


@pytest.mark.parametrize("locale", ("en-US", "fr-CA"))
async def test_production_renderer_prints_markup_literally_at_each_level(locale, env):
    translate.set_locale(locale)
    await _drive_every_call_site(env)
    assert {name for name, _, _ in env.calls} == set(_LEVELS)
    for name, message, _ in env.calls:
        message_type, colour = _LEVELS[name]
        assert _render(message_type, message, color=False) == message + "\n"
        if colour:
            assert colour in _render(message_type, message, color=True)
