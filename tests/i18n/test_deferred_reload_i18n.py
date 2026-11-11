"""Protect the deferred reload confirmation's real interpolation contract."""

from string import Formatter

import pytest

from code_puppy.i18n import catalog, translate


@pytest.mark.parametrize("locale", ["en-US", "es", "fr-CA"])
def test_reload_success_preserves_agent_parameter(locale):
    key = "agent_reload.success"
    message = catalog.load_catalog(locale)[key]
    params = {field for _, field, _, _ in Formatter().parse(message) if field}
    assert params == {"agent"}

    translate.set_locale(locale)
    agent = "[bold]helper[/bold]"
    rendered = translate.t(key, agent=agent)
    assert rendered != key
    assert agent in rendered
    assert "{" not in rendered
    assert "}" not in rendered
