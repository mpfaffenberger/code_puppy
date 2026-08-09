"""i18n coverage for the mcp_/config_wizard.py extraction.

Validates the concrete ``mcp.wizard.*`` key/interpolation contracts. The
wizard requires live MCP infrastructure to run, so we test catalog
correctness directly rather than exercising the wizard end-to-end. The
generic namespace sweep lives in ``test_catalog_namespaces.py``.
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


def test_name_keys_interpolate():
    translate.set_locale("en-US")
    assert "my-srv" in translate.t("mcp.wizard.name.exists", name="my-srv")


def test_type_keys_all_static():
    translate.set_locale("en-US")
    for key in ("mcp.wizard.type.sse", "mcp.wizard.type.http", "mcp.wizard.type.stdio"):
        val = translate.t(key)
        assert val and val != key


def test_stdio_dir_not_found_interpolates():
    translate.set_locale("en-US")
    assert "/tmp/x" in translate.t("mcp.wizard.stdio.dir_not_found", path="/tmp/x")


def test_test_config_error_interpolates():
    translate.set_locale("en-US")
    assert "boom" in translate.t("mcp.wizard.test.config_error", error="boom")


def test_summary_keys_interpolate():
    translate.set_locale("en-US")
    assert "myserver" in translate.t("mcp.wizard.summary.name", name="myserver")
    assert "stdio" in translate.t("mcp.wizard.summary.type", server_type="stdio")
    assert "http://x" in translate.t("mcp.wizard.summary.url", url="http://x")
    assert "node s.js" in translate.t("mcp.wizard.summary.command", command="node s.js")
    assert "--port 3000" in translate.t("mcp.wizard.summary.args", args="--port 3000")
    assert "30" in translate.t("mcp.wizard.summary.timeout", timeout=30)


def test_wizard_added_interpolates():
    translate.set_locale("en-US")
    assert "myserver" in translate.t("mcp.wizard.added", name="myserver")
    assert "myserver" in translate.t("mcp.wizard.hint_start", name="myserver")
    assert "srv-001" in translate.t("mcp.wizard.server_id", id="srv-001")


def test_add_failed_interpolates():
    translate.set_locale("en-US")
    assert "boom" in translate.t("mcp.wizard.add_failed", error="boom")


def test_saved_interpolates():
    translate.set_locale("en-US")
    assert "/tmp/mcp.json" in translate.t("mcp.wizard.saved", path="/tmp/mcp.json")


def test_invalid_choice_and_input_error_interpolate():
    translate.set_locale("en-US")
    assert "a, b" in translate.t("mcp.wizard.invalid_choice", choices="a, b")
    assert "boom" in translate.t("mcp.wizard.input_error", error="boom")


def test_config_wizard_imports_cleanly():
    import code_puppy.mcp_.config_wizard  # noqa: F401
