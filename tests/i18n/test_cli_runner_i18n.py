"""i18n coverage for the CLI runner extraction (PUP-480).

The generic catalog-health sweeps (namespace populated / every key resolves
/ pseudolocalizes / no leftover placeholders) live in
``test_catalog_namespaces.py``. This module keeps the concrete interpolation
contracts for the ``cli.*`` keys the runner depends on.
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


def test_parametrized_cli_keys_interpolate():
    """Representative parametrized keys interpolate their named fields."""
    translate.set_locale("en-US")
    assert translate.t("cli.model.using", model="gpt-5").endswith("gpt-5")
    assert "demo" in translate.t(
        "cli.resume.resumed", messages=3, tokens=1200, session="demo"
    )
    assert "boom" in translate.t("cli.headless.error", error="boom")
    assert "42" in translate.t("cli.autosave.loaded", messages=42, tokens=999)
    assert "my.pkl" in translate.t("cli.autosave.loaded_path", path="my.pkl")


def test_cli_runner_imports_cleanly():
    """The migrated module must import without syntax/import errors."""
    import code_puppy.cli_runner as cli_runner

    assert hasattr(cli_runner, "interactive_mode")
