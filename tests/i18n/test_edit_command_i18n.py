"""Runtime and catalog contracts for MCP edit messages."""

import ast
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.text import Text

from code_puppy.command_line.mcp import edit_command
from code_puppy.i18n import catalog, translate

_LOCALE_DIR = Path(catalog.__file__).parent / "locales"
_LOCALES = sorted(path.stem for path in _LOCALE_DIR.glob("*.json"))
_REAL_PARAMS = {
    "mcp.edit.available_servers": {},
    "mcp.edit.config_load_error": {"error": "load-failed"},
    "mcp.edit.config_read_error": {"error": "json-failed"},
    "mcp.edit.error": {"error": "edit-failed"},
    "mcp.edit.install_hint": {},
    "mcp.edit.list_hint": {},
    "mcp.edit.no_servers": {},
    "mcp.edit.not_found": {"server": "demo-server"},
    "mcp.edit.server_name": {"name": "demo-name"},
    "mcp.edit.usage": {},
}


def test_keys_and_kwargs_match_actual_callers():
    tree = ast.parse(Path(edit_command.__file__).read_text())
    callers = {
        node.args[0].value: {keyword.arg for keyword in node.keywords}
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "t"
    }
    assert callers == {key: set(params) for key, params in _REAL_PARAMS.items()}


@pytest.mark.parametrize("locale", _LOCALES)
def test_exact_namespace_and_real_placeholder_contract(locale):
    entries = catalog.load_catalog(locale)
    assert {key for key in entries if key.startswith("mcp.edit.")} == set(_REAL_PARAMS)
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        assert set(re.findall(r"\{(\w+)\}", entries[key])) == set(params)
        rendered = translate.t(key, **params)
        assert rendered != key
        assert "{" not in rendered
        assert all(value in rendered for value in params.values())


@pytest.mark.parametrize("payload", ["Uso: [nombre]", "Uso: [/mcp edit]"])
def test_usage_keeps_translated_markup_literal(monkeypatch, payload):
    monkeypatch.setattr(edit_command, "t", lambda key: payload)
    output = MagicMock()
    monkeypatch.setattr(edit_command, "emit_info", output)
    command = object.__new__(edit_command.EditCommand)
    command.execute([], group_id="usage")
    usage = output.call_args_list[0].args[0]
    assert isinstance(usage, Text)
    assert usage.plain == payload
    assert usage.style == "yellow"


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("failure", ["form", "reload"])
def test_outer_failure_describes_edit_not_config(monkeypatch, locale, failure):
    translate.set_locale(locale)
    command = object.__new__(edit_command.EditCommand)
    command.manager = MagicMock()
    monkeypatch.setattr(command, "_load_server_config", lambda *_: ("stdio", {}))
    form = MagicMock(return_value=True)
    reload = MagicMock()
    (form if failure == "form" else reload).side_effect = RuntimeError("boom")
    monkeypatch.setattr(edit_command, "run_custom_server_form", form)
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.agent",
        MagicMock(reload_mcp_servers=reload),
    )
    output = MagicMock()
    monkeypatch.setattr(edit_command, "emit_error", output)
    command.execute(["demo"], group_id="failure")
    output.assert_called_once_with(
        translate.t("mcp.edit.error", error="boom"), message_group="failure"
    )
