"""i18n coverage for the config-commands extraction.

Locks in the concrete ``cfg.*`` key contracts that config_commands.py
depends on. Command registration side-effects aren't exercised here —
they require the full CLI stack; the namespace guard is the pragmatic
proof. The generic namespace sweep lives in ``test_catalog_namespaces.py``.
"""

import pytest

from code_puppy.i18n import catalog, translate


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def test_parametrized_cfg_keys_interpolate():
    translate.set_locale("en-US")
    assert "theme" in translate.t("cfg.set.success", key="theme", value="dark")
    assert "gpt-5" in translate.t("cfg.pin_model.success", model="gpt-5", agent="coder")
    assert "coder" in translate.t("cfg.agent.not_found", agent="coder")
    assert "boom" in translate.t("cfg.unpin.failed", agent="coder", error="boom")


def test_colors_usage_renders_as_literal_placeholder():
    """{{color_type}} must render as the literal text {color_type}, never substituted."""
    translate.set_locale("en-US")
    rendered = translate.t("cfg.colors.usage")
    assert "{color_type}" in rendered, (
        f"Expected literal {{color_type}} in output, got: {rendered!r}"
    )


def test_config_commands_imports_cleanly():
    import importlib

    import code_puppy.command_line.config_commands as mod

    importlib.reload(mod)
    assert hasattr(mod, "handle_unpin_command")
