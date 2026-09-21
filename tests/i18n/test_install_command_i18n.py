"""Protect real interpolation in the catalog install command."""

import pytest

from code_puppy.i18n import translate

_PARAMS = {
    "mcp.install.argument_prompt": {"prompt": "Path"},
    "mcp.install.custom_name_prompt": {"name": "github"},
    "mcp.install.description": {"description": "A server"},
    "mcp.install.error": {"error": "boom"},
    "mcp.install.multiple_servers": {"server": "git"},
    "mcp.install.no_server_found": {"server": "git"},
}


@pytest.mark.parametrize("locale", ("en-US", "es", "fr-CA"))
def test_install_placeholders_use_call_site_names(locale):
    translate.set_locale(locale)
    for key, params in _PARAMS.items():
        rendered = translate.t(key, **params)
        assert "{" not in rendered
        assert any(str(value) in rendered for value in params.values())
