"""i18n contract for the browser interaction and navigation tools.

Banners keep the tool-argument echo (``selector='...' button=left``) out of
the catalog: translators get a ``{details}`` placeholder, so argument names
can never be translated.  Tool results stay English for the model.
"""

import ast
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from code_puppy.i18n import available_locales, catalog, pseudo, translate
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated
from code_puppy.tools.browser import browser_interactions as interactions
from code_puppy.tools.browser import browser_navigation as navigation

_PREFIXES = ("browser.interaction.", "browser.navigation.")
_EMITTERS = ("emit_info", "emit_success", "emit_error")
_LOCALES = (*available_locales(), pseudo.PSEUDO_LOCALE)
_SELECTOR = "#go[/red]"
_ERROR = "[red]boom[/x]"
_URL = "https://example.test/[page]"
_LONG_TEXT = "x" * 60

# key -> real kwargs; values carry markup so the tests prove it stays literal.
_REAL_PARAMS = {
    **{
        f"browser.interaction.{action}": {"details": f"selector='{_SELECTOR}'"}
        for action in (
            "click",
            "double_click",
            "hover",
            "set_text",
            "get_text",
            "get_value",
            "select_option",
            "check",
            "uncheck",
        )
    },  # fmt: skip
    **{
        f"browser.interaction.{done}": {"selector": _SELECTOR}
        for done in (
            "clicked",
            "double_clicked",
            "hovered",
            "text_set",
            "checked",
            "unchecked",
        )
    },  # fmt: skip
    "browser.interaction.option_selected": {"selector": _SELECTOR, "selection": "b"},
    "browser.interaction.click_failed": {"error": _ERROR},
    "browser.interaction.set_text_failed": {"error": _ERROR},
    "browser.navigation.navigate": {"url": _URL},
    "browser.navigation.navigated": {"url": _URL},
    "browser.navigation.failed": {"error": _ERROR},
    "browser.navigation.page_info": {},
    "browser.navigation.go_back": {},
    "browser.navigation.go_forward": {},
    "browser.navigation.reload": {"details": "wait_until=load"},
    "browser.navigation.wait_for_load": {"details": "state=load timeout=5ms"},
}

# Pre-extraction English for every call site driven below, in order. The one
# deliberate difference: select_option used to say option='unknown' here.
_LEGACY_ENGLISH = [
    ("emit_info", f"BROWSER CLICK \U0001f5b1\ufe0f selector='{_SELECTOR}' button=right"),
    ("emit_success", f"Clicked element: {_SELECTOR}"),
    ("emit_info", f"BROWSER DOUBLE CLICK \U0001f5b1\ufe0f\U0001f5b1\ufe0f selector='{_SELECTOR}'"),
    ("emit_success", f"Double-clicked element: {_SELECTOR}"),
    ("emit_info", f"BROWSER HOVER \U0001f446 selector='{_SELECTOR}'"),
    ("emit_success", f"Hovered over element: {_SELECTOR}"),
    ("emit_info", f"BROWSER SET TEXT selector='{_SELECTOR}' text='{'x' * 50}...'"),
    ("emit_success", f"Set text in element: {_SELECTOR}"),
    ("emit_info", f"BROWSER GET TEXT selector='{_SELECTOR}'"),
    ("emit_info", f"BROWSER GET VALUE \U0001f4ce selector='{_SELECTOR}'"),
    ("emit_info", f"BROWSER SELECT OPTION selector='{_SELECTOR}' option='b'"),
    ("emit_success", f"Selected option in {_SELECTOR}: b"),
    ("emit_info", f"BROWSER CHECK \u2611\ufe0f selector='{_SELECTOR}'"),
    ("emit_success", f"Checked element: {_SELECTOR}"),
    ("emit_info", f"BROWSER UNCHECK \u2610\ufe0f selector='{_SELECTOR}'"),
    ("emit_success", f"Unchecked element: {_SELECTOR}"),
    ("emit_info", f"BROWSER NAVIGATE \U0001f310 {_URL}"),
    ("emit_success", f"Navigated to: {_URL}"),
    ("emit_info", "BROWSER GET PAGE INFO \U0001f4cc"),
    ("emit_info", "BROWSER GO BACK \u2b05\ufe0f"),
    ("emit_info", "BROWSER GO FORWARD \u27a1\ufe0f"),
    ("emit_info", "BROWSER RELOAD \U0001f504 wait_until=load"),
    ("emit_info", "BROWSER WAIT FOR LOAD state=load timeout=5ms"),
    # Failure paths.
    ("emit_info", f"BROWSER CLICK \U0001f5b1\ufe0f selector='{_SELECTOR}' button=left"),
    ("emit_error", f"Click failed: {_ERROR}"),
    ("emit_info", f"BROWSER SET TEXT selector='{_SELECTOR}' text='short'"),
    ("emit_error", f"Set text failed: {_ERROR}"),
    ("emit_info", f"BROWSER NAVIGATE \U0001f310 {_URL}"),
    ("emit_error", f"Navigation failed: {_ERROR}"),
]  # fmt: skip


def _expected_calls():
    """The same sequence as _LEGACY_ENGLISH, built from the active catalog.

    This mirrors the call sites, so on its own it would prove little; it is
    pinned by _LEGACY_ENGLISH (exact English) and by the AST caller contract.
    """
    t = translate.t
    sel = f"selector='{_SELECTOR}'"
    ia, nav = "browser.interaction.", "browser.navigation."
    return [
        ("emit_info", t(f"{ia}click", details=f"{sel} button=right")),
        ("emit_success", t(f"{ia}clicked", selector=_SELECTOR)),
        ("emit_info", t(f"{ia}double_click", details=sel)),
        ("emit_success", t(f"{ia}double_clicked", selector=_SELECTOR)),
        ("emit_info", t(f"{ia}hover", details=sel)),
        ("emit_success", t(f"{ia}hovered", selector=_SELECTOR)),
        ("emit_info", t(f"{ia}set_text", details=f"{sel} text='{'x' * 50}...'")),
        ("emit_success", t(f"{ia}text_set", selector=_SELECTOR)),
        ("emit_info", t(f"{ia}get_text", details=sel)),
        ("emit_info", t(f"{ia}get_value", details=sel)),
        ("emit_info", t(f"{ia}select_option", details=f"{sel} option='b'")),
        ("emit_success", t(f"{ia}option_selected", selector=_SELECTOR, selection="b")),
        ("emit_info", t(f"{ia}check", details=sel)),
        ("emit_success", t(f"{ia}checked", selector=_SELECTOR)),
        ("emit_info", t(f"{ia}uncheck", details=sel)),
        ("emit_success", t(f"{ia}unchecked", selector=_SELECTOR)),
        ("emit_info", t(f"{nav}navigate", url=_URL)),
        ("emit_success", t(f"{nav}navigated", url=_URL)),
        ("emit_info", t(f"{nav}page_info")),
        ("emit_info", t(f"{nav}go_back")),
        ("emit_info", t(f"{nav}go_forward")),
        ("emit_info", t(f"{nav}reload", details="wait_until=load")),
        ("emit_info", t(f"{nav}wait_for_load", details="state=load timeout=5ms")),
        ("emit_info", t(f"{ia}click", details=f"{sel} button=left")),
        ("emit_error", t(f"{ia}click_failed", error=_ERROR)),
        ("emit_info", t(f"{ia}set_text", details=f"{sel} text='short'")),
        ("emit_error", t(f"{ia}set_text_failed", error=_ERROR)),
        ("emit_info", t(f"{nav}navigate", url=_URL)),
        ("emit_error", t(f"{nav}failed", error=_ERROR)),
    ]


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
            and node.func.id == "t"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).startswith(_PREFIXES)
        ):
            yield node.args[0].value, {keyword.arg for keyword in node.keywords}


def test_keys_and_kwargs_match_actual_callers():
    found = {}
    for module in (interactions, navigation):
        for key, kwargs in _translation_calls(module):
            assert found.setdefault(key, kwargs) == kwargs, key
    assert found == {key: set(params) for key, params in _REAL_PARAMS.items()}


@pytest.mark.parametrize("locale", available_locales())
def test_catalog_contract(locale):
    """Browser-action contracts; generic sweeps live in test_catalog_namespaces."""
    source = catalog.load_catalog("en-US")
    target = catalog.load_catalog(locale)
    assert {key for key in target if key.startswith(_PREFIXES)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        assert placeholder_names(target[key]) == set(params), key
        rendered = translate.t(key, **params)
        assert "{" not in rendered and "}" not in rendered, key
        assert all(value in rendered for value in params.values()), key
        if locale != "en-US":
            assert target[key] != source[key], key


def _fake_page():
    element = AsyncMock()
    element.text_content.return_value = "[b]text[/b]"
    element.input_value.return_value = "[b]value[/b]"
    page = AsyncMock()
    page.locator = MagicMock(return_value=SimpleNamespace(first=element))
    page.url = _URL
    page.title.return_value = "[bold]Title[/bold]"
    return page, element


@pytest.fixture
def emitted(monkeypatch):
    page, element = _fake_page()
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    calls = []
    for module in (interactions, navigation):
        monkeypatch.setattr(module, "get_session_browser_manager", lambda: manager)
        monkeypatch.setattr(module, "generate_group_id", lambda *_: "test-group")
        for name in _EMITTERS:
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **kw: calls.append((_n, message, kw)),
                )
    return SimpleNamespace(calls=calls, page=page, element=element)


async def _drive_every_call_site(emitted):
    sel = _SELECTOR
    results = [
        await interactions.click_element(sel, button="right"),
        await interactions.double_click_element(sel),
        await interactions.hover_element(sel),
        await interactions.set_element_text(sel, _LONG_TEXT),
        await interactions.get_element_text(sel),
        await interactions.get_element_value(sel),
        await interactions.select_option(sel, value="b"),
        await interactions.check_element(sel),
        await interactions.uncheck_element(sel),
        await navigation.navigate_to_url(_URL),
        await navigation.get_page_info(),
        await navigation.go_back(),
        await navigation.go_forward(),
        await navigation.reload_page(wait_until="load"),
        await navigation.wait_for_load_state(state="load", timeout=5),
    ]
    emitted.element.click.side_effect = RuntimeError(_ERROR)
    emitted.element.fill.side_effect = RuntimeError(_ERROR)
    emitted.page.goto.side_effect = RuntimeError(_ERROR)
    results += [
        await interactions.click_element(sel),
        await interactions.set_element_text(sel, "short"),
        await navigation.navigate_to_url(_URL),
    ]
    return results


async def test_english_call_sites_are_byte_identical_to_before(emitted):
    translate.set_locale("en-US")
    await _drive_every_call_site(emitted)
    assert [(name, message) for name, message, _ in emitted.calls] == _LEGACY_ENGLISH


@pytest.mark.parametrize("locale", _LOCALES)
async def test_call_sites_emit_plain_translated_strings(locale, emitted):
    translate.set_locale(locale)
    results = await _drive_every_call_site(emitted)
    assert [(name, message) for name, message, _ in emitted.calls] == _expected_calls()
    for _, message, kwargs in emitted.calls:
        # Plain str: the renderer escapes it and colours it by level.
        assert type(message) is str
        assert kwargs == {"message_group": "test-group"}
    # Argument names are never translated in a real locale. en-XA is skipped:
    # it accents the whole rendered string, and derives from en-US, which
    # _LEGACY_ENGLISH already pins.
    banners = [message for name, message, _ in emitted.calls if name == "emit_info"]
    if locale != pseudo.PSEUDO_LOCALE:
        assert sum(f"selector='{_SELECTOR}'" in banner for banner in banners) == 11
        assert any("wait_until=load" in banner for banner in banners)
        assert any("state=load timeout=5ms" in banner for banner in banners)
    # Tool results are for the model and stay English/untranslated.
    assert results[0] == {
        "success": True,
        "selector": _SELECTOR,
        "action": "right_click",
    }
    assert results[-1] == {"success": False, "error": _ERROR, "url": _URL}


@pytest.mark.parametrize(
    ("kwargs", "option"),
    [
        ({"value": "v1"}, " option='v1'"),
        ({"label": "Label B"}, " option='Label B'"),
        ({"index": 0}, " option='0'"),
        # Same precedence as the selection itself: value="" is what gets selected.
        ({"value": "", "label": "L"}, " option=''"),
        # Nothing requested: no option to echo (and no untranslated placeholder).
        ({}, ""),
    ],
)
async def test_select_option_banner_names_the_requested_option(kwargs, option, emitted):
    """Selecting by value or label used to show option='unknown'."""
    await interactions.select_option(_SELECTOR, **kwargs)
    assert emitted.calls[0][1] == translate.t(
        "browser.interaction.select_option",
        details=f"selector='{_SELECTOR}'{option}",
    )


_LEVELS = {
    "emit_error": (MessageType.ERROR, "\x1b[1;31m"),
    "emit_success": (MessageType.SUCCESS, "\x1b[32m"),
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


@pytest.mark.parametrize(
    ("emitter", "key"),
    [
        ("emit_error", "browser.interaction.click_failed"),
        ("emit_success", "browser.interaction.option_selected"),
        ("emit_error", "browser.navigation.failed"),
    ],
)
def test_production_renderer_keeps_level_colour_and_literal_markup(emitter, key):
    translate.set_locale("fr-CA")
    message = translate.t(key, **_REAL_PARAMS[key])
    message_type, colour = _LEVELS[emitter]
    assert _render(message_type, message, color=False) == message + "\n"
    assert colour in _render(message_type, message, color=True)
