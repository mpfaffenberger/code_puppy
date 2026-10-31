"""i18n contract for the browser locator, semantic, snapshot and screenshot tools.

Banners keep the tool-argument echo (``role=button name=...``) out of the
catalog: translators get a ``{details}`` placeholder, so argument names are
never translated.  Tool results returned to the model stay English.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.i18n import available_locales, catalog, ngettext, pseudo, translate
from code_puppy.i18n import t as tr
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.tools.browser import browser_locators as locators
from code_puppy.tools.browser import browser_page_snapshot as snapshot
from code_puppy.tools.browser import browser_screenshot as screenshot
from code_puppy.tools.browser import browser_semantic_interactions as semantic

_PREFIXES = (
    "browser.locator.",
    "browser.semantic.",
    "browser.snapshot.",
    "browser.screenshot.",
)
_MODULES = (locators, semantic, snapshot, screenshot)
_EMITTERS = ("emit_info", "emit_success", "emit_error")
_LOCALES = (*available_locales(), pseudo.PSEUDO_LOCALE)
# Message glyphs, spelled as escapes so tooling cannot strip them.
_ROLE, _LABEL, _BUTTON, _LINK, _CAMERA = (
    "\U0001f3a8",
    "\U0001f3f7\ufe0f",
    "\U0001f518",
    "\U0001f517",
    "\U0001f4f7",
)
_TEXT = "[b]Sign in[/b]"
_ERROR = "[red]boom[/x]"

# key -> real kwargs (``count`` marks a plural key). One row per catalog key.
_REAL_PARAMS = {
    **{
        f"browser.locator.{key}": {"details": "role=button"}
        for key in (
            "find_by_role",
            "find_by_text",
            "find_by_label",
            "find_by_placeholder",
            "find_by_test_id",
            "xpath_query",
            "find_buttons",
            "find_links",
        )
    },
    "browser.locator.found_by_role": {"count": 2, "role": "button"},
    "browser.locator.found_by_text": {"count": 2, "text": "Go"},
    "browser.locator.found_by_label": {"count": 2, "label": "Email"},
    "browser.locator.found_by_placeholder": {"count": 2, "placeholder": "Search"},
    "browser.locator.found_by_test_id": {"count": 2, "test_id": "submit"},
    "browser.locator.found_by_xpath": {"count": 2, "xpath": "//a"},
    "browser.locator.found_buttons": {"count": 2},
    "browser.locator.found_buttons_matching": {"count": 2, "filter": "go"},
    "browser.locator.found_links": {"count": 2},
    "browser.locator.found_links_matching": {"count": 2, "filter": "go"},
    **{
        f"browser.semantic.{action}": {"strategy": "ROLE", "target": "role='button'"}
        for action in ("click", "fill", "check")
    },
    "browser.semantic.no_match": {"target": "text='Go'"},
    **{
        f"browser.semantic.{done}": {"target": "role='button'"}
        for done in ("clicked", "filled", "checked")
    },
    **{
        f"browser.semantic.{action}_failed": {"error": "boom"}
        for action in ("click", "fill", "check")
    },
    "browser.snapshot.banner": {},
    "browser.snapshot.done": {"buttons": "1 button", "links": "2 links", "inputs": "0"},
    "browser.snapshot.buttons": {"count": 2},
    "browser.snapshot.links": {"count": 2},
    "browser.snapshot.inputs": {"count": 2},
    "browser.screenshot.banner": {"details": "target=viewport"},
    "browser.screenshot.saved": {"path": "/tmp/shot.png"},
    "browser.screenshot.no_page": {},
    "browser.screenshot.not_visible": {"selector": "#x"},
    "browser.screenshot.failed": {"error": "boom"},
}
_PLURAL = {key for key, params in _REAL_PARAMS.items() if "count" in params}
# Reached through semantic._MESSAGE_KEYS rather than a direct t() call.
_MAPPED = {key for keys in semantic._MESSAGE_KEYS.values() for key in keys}


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
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).startswith(_PREFIXES)
        ):
            kwargs = {keyword.arg for keyword in node.keywords}
            if node.func.id == "ngettext":
                kwargs.add("count")
            yield node.func.id, node.args[0].value, kwargs


def test_keys_and_kwargs_match_actual_callers():
    """Direct callers pass exactly each key's params; mapped keys are driven below."""
    found = {}
    for module in _MODULES:
        for func, key, kwargs in _translation_calls(module):
            assert found.setdefault(key, kwargs) == kwargs, key
            assert (func == "ngettext") == (key in _PLURAL), key
    assert set(found) | _MAPPED == set(_REAL_PARAMS)
    assert not set(found) & _MAPPED
    for key, kwargs in found.items():
        assert kwargs == set(_REAL_PARAMS[key]), key


@pytest.mark.parametrize("locale", available_locales())
def test_catalog_contract(locale):
    source = catalog.load_catalog("en-US")
    target = catalog.load_catalog(locale)
    assert {key for key in target if key.startswith(_PREFIXES)} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        plural = key in _PLURAL
        forms = {"one", "other"} if plural else {None}
        if plural:
            assert set(target[key]) == forms, key
        for form in forms:
            text = target[key][form] if plural else target[key]
            assert placeholder_names(text) == set(params), key
            if locale != "en-US":
                english = source[key][form] if plural else source[key]
                assert text != english, (key, form)
        kwargs = {k: v for k, v in params.items() if k != "count"}
        # 0 matters: French uses the "one" form for it.
        for count in (0, 1, 2) if plural else (None,):
            rendered = ngettext(key, count, **kwargs) if plural else tr(key, **kwargs)
            assert "{" not in rendered and "}" not in rendered, key
            assert all(str(value) in rendered for value in kwargs.values()), key


# English (count=1, count=2) for every plural key: the singular is new.
_ENGLISH_PLURALS = {
    "browser.locator.found_by_role": (
        "Found 1 element with role 'button'",
        "Found 2 elements with role 'button'",
    ),
    "browser.locator.found_by_text": (
        "Found 1 element containing text 'Go'",
        "Found 2 elements containing text 'Go'",
    ),
    "browser.locator.found_by_label": (
        "Found 1 element with label 'Email'",
        "Found 2 elements with label 'Email'",
    ),
    "browser.locator.found_by_placeholder": (
        "Found 1 element with placeholder 'Search'",
        "Found 2 elements with placeholder 'Search'",
    ),
    "browser.locator.found_by_test_id": (
        "Found 1 element with test-id 'submit'",
        "Found 2 elements with test-id 'submit'",
    ),
    "browser.locator.found_by_xpath": (
        "Found 1 element with XPath '//a'",
        "Found 2 elements with XPath '//a'",
    ),
    "browser.locator.found_buttons": ("Found 1 button", "Found 2 buttons"),
    "browser.locator.found_buttons_matching": (
        "Found 1 button containing 'go'",
        "Found 2 buttons containing 'go'",
    ),
    "browser.locator.found_links": ("Found 1 link", "Found 2 links"),
    "browser.locator.found_links_matching": (
        "Found 1 link containing 'go'",
        "Found 2 links containing 'go'",
    ),
    "browser.snapshot.buttons": ("1 button", "2 buttons"),
    "browser.snapshot.links": ("1 link", "2 links"),
    "browser.snapshot.inputs": ("1 input", "2 inputs"),
}


@pytest.mark.parametrize("key", sorted(_PLURAL))
def test_english_plural_forms(key):
    translate.set_locale("en-US")
    kwargs = {k: v for k, v in _REAL_PARAMS[key].items() if k != "count"}
    rendered = (ngettext(key, 1, **kwargs), ngettext(key, 2, **kwargs))
    assert rendered == _ENGLISH_PLURALS[key]


# ---------------------------------------------------------------- call sites


def _element(text=_TEXT):
    element = AsyncMock()
    element.is_visible.return_value = True
    element.text_content.return_value = text
    element.evaluate.return_value = "button"
    element.get_attribute.return_value = "x"
    element.input_value.return_value = "v"
    return element


async def _ready(value):
    return value


@pytest.fixture
def env(monkeypatch, tmp_path):
    # Varied texts, so filtered counts differ from the total.
    elements = [_element(_TEXT), _element("Help"), _element("Sign up")]
    locator = MagicMock()
    locator.first = AsyncMock()
    locator.count = AsyncMock(return_value=3)
    locator.nth.side_effect = lambda i: elements[i % len(elements)]
    page = MagicMock()
    for finder in (
        "get_by_role",
        "get_by_text",
        "get_by_label",
        "get_by_placeholder",
        "get_by_test_id",
        "locator",
    ):
        getattr(page, finder).return_value = locator
    page.evaluate = AsyncMock(
        return_value={"buttons": [1], "links": [1, 2], "inputs": []}
    )
    page.screenshot = AsyncMock(return_value=b"png")
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    calls = []
    for module in _MODULES:
        monkeypatch.setattr(module, "get_session_browser_manager", lambda: manager)
        monkeypatch.setattr(module, "generate_group_id", lambda *_: "g")
        for name in _EMITTERS:
            if hasattr(module, name):
                monkeypatch.setattr(
                    module,
                    name,
                    lambda message, _n=name, **kw: calls.append((_n, message, kw)),
                )
    monkeypatch.setattr(
        screenshot, "_build_screenshot_path", lambda _ts: tmp_path / "shot.png"
    )
    return SimpleNamespace(
        calls=calls, page=page, locator=locator, manager=manager, tmp=tmp_path
    )


async def _drive_every_call_site(env):
    count = env.locator.count
    results = []
    count.return_value = 1
    results.append(await locators.find_by_role("button", name="Save[/b]"))
    count.return_value = 3
    results += [
        await locators.find_by_text(_TEXT),
        await locators.find_by_label(_TEXT),
        await locators.find_by_placeholder(_TEXT),
        await locators.find_by_test_id("t[/x]"),
        await locators.run_xpath_query("//a[@id='x']"),
        await locators.find_buttons(),
        await locators.find_buttons(text_filter="Help"),
        await locators.find_links(),
        await locators.find_links(text_filter="Sign"),
        await semantic.click_by_role("button", name="Go[/b]"),
        await semantic.set_text_by_label("Email", "a@b"),
        await semantic._act_on_semantic("label", "Agree", "check"),
        await snapshot.get_page_snapshot(),
        await screenshot.take_screenshot(),
    ]
    count.return_value = 0
    results.append(await semantic.click_by_text("Nope"))
    count.return_value = 3
    for method in ("click", "fill", "check"):
        getattr(env.locator.first, method).side_effect = RuntimeError(_ERROR)
    results += [
        await semantic.click_by_text("Go"),
        await semantic.set_text_by_label("Email", "a@b"),
        await semantic._act_on_semantic("label", "Agree", "check"),
    ]
    env.manager.get_current_page.return_value = None
    results.append(await screenshot.take_screenshot())
    env.manager.get_current_page.return_value = env.page
    hidden = _element()
    hidden.is_visible.return_value = False
    env.page.locator.return_value = SimpleNamespace(first=_ready(hidden))
    results.append(await screenshot.take_screenshot(element_selector="#hidden"))
    env.page.screenshot.side_effect = RuntimeError(_ERROR)
    results.append(await screenshot.take_screenshot())
    env.manager.get_current_page.side_effect = RuntimeError(_ERROR)
    results.append(await screenshot.take_screenshot())
    return results


def _golden_english(tmp):
    """Pre-extraction English plus the declared changes: a count of one is
    singular, and a capture exception is prefixed "Screenshot failed: "."""
    role = "role='button' name='Go[/b]'"
    return [
        ("emit_info", f"BROWSER FIND BY ROLE {_ROLE} role=button name=Save[/b]"),
        ("emit_success", "Found 1 element with role 'button'"),
        ("emit_info", f"BROWSER FIND BY TEXT text='{_TEXT}' exact=False"),
        ("emit_success", f"Found 3 elements containing text '{_TEXT}'"),
        ("emit_info", f"BROWSER FIND BY LABEL {_LABEL} label='{_TEXT}' exact=False"),
        ("emit_success", f"Found 3 elements with label '{_TEXT}'"),
        ("emit_info", f"BROWSER FIND BY PLACEHOLDER placeholder='{_TEXT}' exact=False"),
        ("emit_success", f"Found 3 elements with placeholder '{_TEXT}'"),
        ("emit_info", "BROWSER FIND BY TEST ID test_id='t[/x]'"),
        ("emit_success", "Found 3 elements with test-id 't[/x]'"),
        ("emit_info", "BROWSER XPATH QUERY xpath='//a[@id='x']'"),
        ("emit_success", "Found 3 elements with XPath '//a[@id='x']'"),
        ("emit_info", f"BROWSER FIND BUTTONS {_BUTTON} filter='none'"),
        ("emit_success", "Found 3 buttons"),
        ("emit_info", f"BROWSER FIND BUTTONS {_BUTTON} filter='Help'"),
        ("emit_success", "Found 1 button containing 'Help'"),
        ("emit_info", f"BROWSER FIND LINKS {_LINK} filter='none'"),
        ("emit_success", "Found 3 links"),
        ("emit_info", f"BROWSER FIND LINKS {_LINK} filter='Sign'"),
        ("emit_success", "Found 2 links containing 'Sign'"),
        ("emit_info", f"BROWSER CLICK BY ROLE  {role}"),
        ("emit_success", f"click on {role}"),
        ("emit_info", "BROWSER FILL BY LABEL  label='Email'"),
        ("emit_success", "fill on label='Email'"),
        ("emit_info", "BROWSER CHECK BY LABEL  label='Agree'"),
        ("emit_success", "check on label='Agree'"),
        ("emit_info", "BROWSER PAGE SNAPSHOT  gathering DOM state"),
        ("emit_success", "Snapshot: 1 button, 2 links, 0 inputs"),
        ("emit_info", f"BROWSER SCREENSHOT {_CAMERA} target=viewport"),
        ("emit_success", f"Screenshot saved: {tmp / 'shot.png'}"),
        ("emit_info", "BROWSER CLICK BY TEXT  text='Nope'"),
        ("emit_error", "No element matched text='Nope'"),
        ("emit_info", "BROWSER CLICK BY TEXT  text='Go'"),
        ("emit_error", f"click failed: {_ERROR}"),
        ("emit_info", "BROWSER FILL BY LABEL  label='Email'"),
        ("emit_error", f"fill failed: {_ERROR}"),
        ("emit_info", "BROWSER CHECK BY LABEL  label='Agree'"),
        ("emit_error", f"check failed: {_ERROR}"),
        ("emit_info", f"BROWSER SCREENSHOT {_CAMERA} target=viewport"),
        ("emit_error", "No active browser page. Navigate to a webpage first."),
        ("emit_info", f"BROWSER SCREENSHOT {_CAMERA} target=#hidden"),
        ("emit_error", "Element '#hidden' is not visible"),
        ("emit_info", f"BROWSER SCREENSHOT {_CAMERA} target=viewport"),
        ("emit_error", f"Screenshot failed: {_ERROR}"),
        ("emit_info", f"BROWSER SCREENSHOT {_CAMERA} target=viewport"),
        ("emit_error", f"Screenshot failed: {_ERROR}"),
    ]


async def test_english_golden_output(env):
    translate.set_locale("en-US")
    await _drive_every_call_site(env)
    emitted = [(name, message) for name, message, _ in env.calls]
    assert emitted == _golden_english(env.tmp)


@pytest.mark.parametrize("locale", _LOCALES)
async def test_every_locale_emits_plain_strings_and_english_results(locale, env):
    translate.set_locale(locale)
    results = await _drive_every_call_site(env)
    golden = _golden_english(env.tmp)
    assert len(env.calls) == len(golden)
    for _, message, kwargs in env.calls:
        assert type(message) is str  # the renderer escapes it
        assert "{" not in message and "}" not in message
        assert kwargs == {"message_group": "g"}
    if locale in ("es", "fr-CA"):
        # Every message is translated, including each use of a shared key.
        for (name, message, _), english in zip(env.calls, golden):
            assert (name, message) != english
    # Filtering really ran: the fake's element texts differ.
    assert results[7]["filtered_count"] == 1
    assert results[9]["filtered_count"] == 2
    # Argument echoes are never translated (en-XA accents whole strings).
    if locale != pseudo.PSEUDO_LOCALE:
        banners = [m for name, m, _ in env.calls if name == "emit_info"]
        for echo in (
            "role=button name=Save[/b]",
            f"text='{_TEXT}' exact=False",
            "xpath='//a[@id='x']'",
            "filter='none'",
            "role='button' name='Go[/b]'",
            "target=#hidden",
        ):
            assert any(echo in banner for banner in banners), echo
    # Results returned to the model stay English in every locale.
    assert results[15] == {
        "success": False,
        "error": "No element matched text='Nope'",
        "target": "text='Nope'",
    }
    assert results[19] == {
        "success": False,
        "error": "No active browser page. Navigate to a webpage first.",
    }
    assert results[20] == {
        "success": False,
        "error": "Element '#hidden' is not visible",
    }
    assert results[21] == {"success": False, "error": _ERROR}
    assert results[22] == {"success": False, "error": f"Screenshot failed: {_ERROR}"}


@pytest.mark.parametrize("locale", available_locales())
async def test_each_semantic_action_uses_its_own_messages(locale, env):
    translate.set_locale(locale)
    for action, args in (
        ("click", ("role", "button")),
        ("fill", ("label", "Email")),
        ("check", ("label", "Agree")),
    ):
        env.calls.clear()
        await semantic._act_on_semantic(*args, action)
        banner, done = (message for _, message, _ in env.calls)
        banner_key, success_key, _ = semantic._MESSAGE_KEYS[action]
        target = f"{args[0]}='{args[1]}'"
        assert banner == tr(banner_key, strategy=args[0].upper(), target=target)
        assert done == tr(success_key, target=target)


async def test_direct_capture_without_group_id_emits_nothing(env):
    """Only take_screenshot passes a group id; direct callers stay silent."""
    hidden = _element()
    hidden.is_visible.return_value = False
    env.page.locator.return_value = SimpleNamespace(first=_ready(hidden))
    not_visible = await screenshot._capture_screenshot(
        env.page, element_selector="#hidden"
    )
    env.page.screenshot.side_effect = RuntimeError(_ERROR)
    raised = await screenshot._capture_screenshot(env.page)
    assert env.calls == []
    assert not_visible == {
        "success": False,
        "error": "Element '#hidden' is not visible",
    }
    assert raised == {"success": False, "error": _ERROR}
