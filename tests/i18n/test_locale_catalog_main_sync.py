"""Caller and plural contracts for catalog entries synchronized from main."""

import ast
import json
from pathlib import Path

import pytest
from rich.text import Text

from code_puppy.i18n import translate

_CATALOG_DIR = Path(__file__).parents[2] / "code_puppy" / "i18n" / "locales"
_LOCALES = tuple(path.stem for path in _CATALOG_DIR.glob("*.json"))
# Parameter names match the upstream callers, not fields inferred from catalogs.
_REAL_PARAMS = {
    "agent_menu.agent_reloaded_pinned": {"model": "model-name"},
    "agent_menu.models_load_failed": {"error": "load-failure"},
    "agent_menu.pin_apply_failed": {"error": "apply-failure"},
    "agent_menu.pin_cleared": {"agent": "agent-name"},
    "agent_menu.pin_set": {"model": "model-name", "agent": "agent-name"},
    "agent_menu.pinned_reload_failed": {"error": "reload-failure"},
    "browser.chromium.install_failed": {
        "exit_code": 17,
        "command": "python -m playwright install chromium",
        "output": "installer-output",
    },
    "browser.chromium.install_start_failed": {
        "error": "start-failure",
        "command": "python -m playwright install chromium",
    },
    "browser.chromium.retry_failed": {
        "command": "python -m playwright install chromium",
        "error": "browser-failure",
    },
    "model_menu.registry.loaded": {"providers": 65, "models": 1371},
    "speculation.saved": {"seconds": "1.2"},
    "stream.activity.calling": {"tool": "read_file"},
    "stream.progress": {"count": "1,234", "activity": "activity-value"},
    "tools.streaming_progress": {"tool": "read_file", "count": "1,234"},
}


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("key,params", _REAL_PARAMS.items())
def test_main_sync_interpolates_real_caller_params(locale, key, params):
    translate.set_locale(locale)
    rendered = translate.t(key, **params)
    assert rendered != key
    assert "{" not in rendered and "}" not in rendered
    for value in params.values():
        assert str(value) in rendered


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(
    "key", ("speculation.hits", "speculation.misses", "speculation.wasted")
)
@pytest.mark.parametrize("count", (0, 1, 2))
def test_speculation_plural_forms_render_through_runtime(locale, key, count):
    translate.set_locale(locale)
    data = json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    # French uses 'one' for zero; English and Spanish use it only for one.
    category = "one" if count == 1 or (locale == "fr-CA" and count == 0) else "other"
    rendered = translate.ngettext(key, count)
    assert rendered == data[key][category].replace("{count}", str(count))
    assert "{" not in rendered and "}" not in rendered


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(
    "key,tokens",
    [
        ("cli.speculation.off", ("Ctrl+X Ctrl+S",)),
        ("cli.speculation.on", ("Ctrl+X Ctrl+S",)),
        ("speculation.disabled", ("Ctrl+X Ctrl+S",)),
        ("help.keybinding.ctrl_enter.label", ("Ctrl+Enter",)),
        ("help.keybinding.newline.label", ("Ctrl+J", "Shift+Enter")),
        ("help.keybinding.newline.description", ("Ctrl+J",)),
        ("browser.chromium.installing", ("Chromium", "Playwright", "Code Puppy")),
    ],
)
def test_main_sync_preserves_technical_identifiers(locale, key, tokens):
    translate.set_locale(locale)
    rendered = translate.t(key)
    for token in tokens:
        assert token in rendered


def test_obsolete_banner_keys_and_callers_are_removed_together():
    obsolete = {"cli.banner.observability_pitch", "cli.banner.powered_by"}
    source = Path(__file__).parents[2] / "code_puppy" / "cli_runner.py"
    literals = {
        node.value
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert obsolete.isdisjoint(literals)
    for locale in _LOCALES:
        data = json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))
        assert obsolete.isdisjoint(data)


@pytest.mark.parametrize("locale", _LOCALES)
def test_stream_activity_with_markup_like_tool_is_literal(locale):
    translate.set_locale(locale)
    rendered = translate.t("stream.activity.calling", tool="[bold]tool[/bold]")
    text = Text(rendered)
    assert text.plain == rendered
    assert not text.spans
