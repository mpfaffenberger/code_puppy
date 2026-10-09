"""Protect real interpolation in the catalog install command."""

import re
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.text import Text

from code_puppy.i18n import catalog, translate

_LOCALES = ("en-US", "es", "fr-CA")
_REAL_PARAMS = {
    "mcp.install.argument_prompt": {"prompt": "Path"},
    "mcp.install.custom_name_prompt": {"name": "github"},
    "mcp.install.description": {"description": "A server"},
    "mcp.install.error": {"error": "boom"},
    "mcp.install.multiple_servers": {"server": "git"},
    "mcp.install.no_server_found": {"server": "git"},
    "mcp.install_wizard.installing": {"name": "GitHub"},
    "mcp.install_wizard.override_prompt": {"server_name": "github"},
    "mcp.install_wizard.env_var_prompt": {"var": "API_KEY"},
    "mcp.install_wizard.install_failed": {"error": "boom"},
}


@pytest.mark.parametrize("locale", _LOCALES)
def test_install_placeholders_use_call_site_names(locale):
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        rendered = translate.t(key, **params)
        assert "{" not in rendered, (locale, key, rendered)
        for value in params.values():
            assert str(value) in rendered, (locale, key, rendered)


@pytest.fixture
def install_flow(monkeypatch):
    """Exercise the real command without a manager, network, or disk writes."""
    from code_puppy import messaging
    from code_puppy.command_line.mcp import install_command, utils, wizard_utils
    from code_puppy.mcp_.server_registry_catalog import catalog as registry

    def no_network(*args, **kwargs):
        pytest.fail("Install regression tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    server = SimpleNamespace(
        name="github",
        display_name="GitHub",
        description="A server",
        get_environment_vars=lambda: [],
        get_command_line_args=lambda: [],
    )
    monkeypatch.setattr(registry, "get_by_id", lambda _: server)
    monkeypatch.setattr(registry, "search", lambda _: [])
    monkeypatch.setattr(utils, "find_server_id_by_name", lambda *args: None)
    messages, prompts = [], []
    answers = []

    def prompt(text):
        prompts.append(text)
        return answers.pop(0)

    monkeypatch.setattr(messaging, "emit_prompt", prompt)
    monkeypatch.setattr(
        install_command, "emit_info", lambda text, **kwargs: messages.append(text)
    )
    monkeypatch.setattr(
        install_command, "emit_error", lambda text, **kwargs: messages.append(text)
    )
    installer = Mock(return_value=True)
    monkeypatch.setattr(wizard_utils, "install_server_from_catalog", installer)
    command = object.__new__(install_command.InstallCommand)
    command.manager = object()
    return SimpleNamespace(
        command=command,
        server=server,
        installer=installer,
        messages=messages,
        prompts=prompts,
        answers=answers,
        utils=utils,
    )


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("accept", (True, False))
def test_override_prompt_token_drives_real_parser(
    locale, accept, install_flow, monkeypatch
):
    translate.set_locale(locale)
    monkeypatch.setattr(
        install_flow.utils, "find_server_id_by_name", lambda *args: "old"
    )
    prompt = translate.t("mcp.install_wizard.override_prompt", server_name="github")
    token = re.search(r"\[([^/]+)/[^\]]+\]", prompt).group(1)
    install_flow.answers[:] = ["", token.upper() if accept else ""]
    assert install_flow.command._install_from_catalog("github", "test") is accept
    assert install_flow.prompts[-1] == prompt
    assert install_flow.installer.called is accept
    if not accept:
        assert translate.t("mcp.install_wizard.cancelled") in install_flow.messages


@pytest.mark.parametrize("locale", _LOCALES)
def test_optional_argument_and_prompt_spacing(locale, install_flow, monkeypatch):
    translate.set_locale(locale)
    monkeypatch.delenv("INSTALL_TEST_KEY", raising=False)
    install_flow.server.get_environment_vars = lambda: ["INSTALL_TEST_KEY"]
    install_flow.server.get_command_line_args = lambda: [
        {"name": "path", "prompt": "Path", "default": "/tmp", "required": False}
    ]
    install_flow.answers[:] = ["", "test-value", ""]
    assert install_flow.command._install_from_catalog("github", "test")
    assert all(prompt.endswith(" ") for prompt in install_flow.prompts)
    assert translate.t("mcp.install_wizard.optional_suffix") in install_flow.prompts[-1]
    assert install_flow.installer.call_args.args[3:5] == (
        {"INSTALL_TEST_KEY": "test-value"},
        {"path": "/tmp"},
    )


@pytest.mark.parametrize("locale", _LOCALES)
def test_translations_and_environment_names_render_as_literal_text(
    locale, install_flow, monkeypatch
):
    translate.set_locale(locale)
    keys = (
        "mcp.install_wizard.env_vars_header",
        "mcp.install_wizard.already_set",
        "mcp.install_wizard.cmd_args_header",
    )
    for key in keys:
        monkeypatch.setitem(catalog.load_catalog(locale), key, "[bold]literal[/bold]")
    variable = "INSTALL_TEST_[italic]KEY[/italic]"
    monkeypatch.setenv(variable, "secret-not-for-display")
    install_flow.server.get_environment_vars = lambda: [variable]
    install_flow.server.get_command_line_args = lambda: [
        {"name": "path", "prompt": "Path", "default": "/tmp"}
    ]
    install_flow.answers[:] = ["", ""]
    assert install_flow.command._install_from_catalog("github", "test")
    styled = [message for message in install_flow.messages if isinstance(message, Text)]
    assert [message.plain for message in styled] == [
        "\n[bold]literal[/bold]",
        f"  {variable}: [bold]literal[/bold]",
        "\n[bold]literal[/bold]",
    ]
    assert styled[0].style == styled[2].style == "yellow"
    assert styled[1].spans[-1].style == "green"
    assert "secret-not-for-display" not in "".join(map(str, install_flow.messages))


@pytest.mark.parametrize("locale", _LOCALES)
def test_install_catalog_key_and_placeholder_parity(locale):
    source = catalog.load_catalog("en-US")
    translated = catalog.load_catalog(locale)
    keys = {key for key in source if key.startswith("mcp.install.")}
    assert keys == {key for key in translated if key.startswith("mcp.install.")}
    for key in keys | _REAL_PARAMS.keys():
        assert set(re.findall(r"\{(\w+)\}", source[key])) == set(
            re.findall(r"\{(\w+)\}", translated[key])
        ), (locale, key)
