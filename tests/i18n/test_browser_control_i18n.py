from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from code_puppy.i18n import available_locales, catalog, pseudo, translate
from code_puppy.i18n.interpolation import placeholder_names
from code_puppy.messaging.message_queue import MessageType
from code_puppy.messaging.renderers import _print_message_uncoordinated
from code_puppy.tools.browser import browser_control as control

_REAL_PARAMS = {
    "blank_page": {},
    "close": {},
    "closed": {},
    "initialize": {
        "browser_type": "firefox",
        "homepage": "https://example.test/[home]",
    },
    "initialize_failed": {"error": "[red]startup failed[/red]"},
    "list_pages": {},
    "new_page": {"url": "https://example.test/[new]"},
    "page_created": {"url": "https://example.test/[final]"},
    "status": {},
}
_LOCALES = (*available_locales(), pseudo.PSEUDO_LOCALE)


@pytest.mark.parametrize("locale", available_locales())
def test_catalog_contract(locale):
    """Browser-specific contracts; generic sweeps live in test_catalog_namespaces."""
    translate.set_locale(locale)
    try:
        source = catalog.load_catalog("en-US")
        target = catalog.load_catalog(locale)
        keys = {f"browser.control.{suffix}" for suffix in _REAL_PARAMS}
        assert {key for key in target if key.startswith("browser.control.")} == keys
        for suffix, params in _REAL_PARAMS.items():
            key = f"browser.control.{suffix}"
            assert placeholder_names(target[key]) == set(params)
            rendered = translate.t(key, **params)
            for value in params.values():
                assert value in rendered
            if locale != "en-US":
                assert target[key] != source[key]
    finally:
        translate.set_locale("en-US")


@pytest.mark.parametrize("locale", _LOCALES)
async def test_lifecycle_call_sites(locale, monkeypatch):
    translate.set_locale(locale)
    manager = AsyncMock()
    manager._initialized = True
    page = AsyncMock()
    page.url = _REAL_PARAMS["page_created"]["url"]
    page.title.return_value = "[bold]Page title[/bold]"
    manager.get_current_page.return_value = page
    manager.new_page.return_value = page
    manager.get_all_pages.return_value = []
    monkeypatch.setattr(control, "get_session_browser_manager", lambda: manager)
    monkeypatch.setattr(control, "generate_group_id", lambda *args: "test-group")
    emitters = {}
    for name in ("emit_info", "emit_warning", "emit_success", "emit_error"):
        emitters[name] = MagicMock()
        monkeypatch.setattr(control, name, emitters[name])
    try:
        result = await control.initialize_browser(**_REAL_PARAMS["initialize"])
        assert result["browser_type"] == "firefox"
        assert result["homepage"] == _REAL_PARAMS["initialize"]["homepage"]
        assert result["current_title"] == "[bold]Page title[/bold]"
        assert (await control.get_browser_status())["status"] == "initialized"
        assert (await control.list_pages())["pages"] == []
        for url in (_REAL_PARAMS["new_page"]["url"], None, ""):
            result = await control.create_new_page(url)
            assert result == {
                "success": True,
                "url": page.url,
                "title": "[bold]Page title[/bold]",
                "requested_url": url,
            }
        assert await control.close_browser() == {
            "success": True,
            "message": "Browser closed",
        }
        manager.async_initialize.side_effect = RuntimeError(
            _REAL_PARAMS["initialize_failed"]["error"]
        )
        assert (await control.initialize_browser())["error"] == _REAL_PARAMS[
            "initialize_failed"
        ]["error"]

        expected_info = [
            translate.t("browser.control.initialize", **_REAL_PARAMS["initialize"]),
            translate.t("browser.control.status"),
            translate.t("browser.control.list_pages"),
            translate.t("browser.control.new_page", **_REAL_PARAMS["new_page"]),
            *[
                translate.t(
                    "browser.control.new_page",
                    url=translate.t("browser.control.blank_page"),
                )
            ]
            * 2,
            translate.t("browser.control.close"),
            translate.t(
                "browser.control.initialize",
                browser_type="chromium",
                homepage="https://www.google.com",
            ),
        ]
        assert [
            call.args[0] for call in emitters["emit_info"].call_args_list
        ] == expected_info
        for emitter, suffix, count in (
            ("emit_success", "page_created", 3),
            ("emit_warning", "closed", 1),
            ("emit_error", "initialize_failed", 1),
        ):
            assert [call.args[0] for call in emitters[emitter].call_args_list] == [
                translate.t(f"browser.control.{suffix}", **_REAL_PARAMS[suffix])
            ] * count
        for emitter in emitters.values():
            for call in emitter.call_args_list:
                message = call.args[0]
                # Plain str: the renderer escapes it and colours it by level.
                assert type(message) is str
                assert call.kwargs == {"message_group": "test-group"}
                assert "{" not in message and "}" not in message
    finally:
        translate.set_locale("en-US")


_LEVELS = {
    "emit_error": (MessageType.ERROR, "\x1b[1;31m"),
    "emit_warning": (MessageType.WARNING, "\x1b[33m"),
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
    ("emitter", "suffix"),
    [
        ("emit_error", "initialize_failed"),
        ("emit_warning", "closed"),
        ("emit_success", "page_created"),
    ],
)
def test_production_renderer_keeps_level_colour_and_literal_markup(emitter, suffix):
    message = translate.t(f"browser.control.{suffix}", **_REAL_PARAMS[suffix])
    message_type, colour = _LEVELS[emitter]
    assert _render(message_type, message, color=False) == message + "\n"
    assert colour in _render(message_type, message, color=True)


def test_english_layout_is_unchanged():
    translate.set_locale("en-US")
    assert translate.t("browser.control.initialize", **_REAL_PARAMS["initialize"]) == (
        "BROWSER INITIALIZE \U0001f310 firefox → https://example.test/[home]"
    )
    assert translate.t("browser.control.close") == "BROWSER CLOSE \U0001f512"
    assert translate.t("browser.control.status") == "BROWSER STATUS \U0001f4ca"
    assert (
        translate.t(
            "browser.control.new_page", url=translate.t("browser.control.blank_page")
        )
        == "BROWSER NEW PAGE blank page"
    )
