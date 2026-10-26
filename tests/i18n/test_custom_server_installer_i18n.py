"""i18n coverage for the custom_server_installer.py extraction.

Locks in the ``mcp.custom_server.*`` catalog namespace that
custom_server_installer.py depends on.
"""

import pytest

from code_puppy.i18n import catalog, pseudo, translate


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def _custom_server_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("mcp.custom_server.")]


def test_custom_server_namespace_is_populated():
    assert len(_custom_server_keys()) >= 20


def test_every_custom_server_key_resolves_to_real_text():
    translate.set_locale("en-US")
    offenders = [
        k for k in _custom_server_keys() if not translate.t(k) or translate.t(k) == k
    ]
    assert not offenders, f"mcp.custom_server.* keys not resolving: {offenders}"


def test_every_custom_server_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [
        k for k in _custom_server_keys() if not translate.t(k).startswith("\u27e6")
    ]
    assert not offenders, f"mcp.custom_server.* keys not pseudolocalized: {offenders}"


def test_example_header_interpolates():
    translate.set_locale("en-US")
    assert "stdio" in translate.t(
        "mcp.custom_server.example_header", server_type="stdio"
    )


def test_url_missing_interpolates():
    translate.set_locale("en-US")
    assert "http" in translate.t("mcp.custom_server.url_missing", server_type="http")


def test_invalid_json_interpolates():
    translate.set_locale("en-US")
    assert "boom" in translate.t("mcp.custom_server.invalid_json", error="boom")


def test_success_and_start_hint_interpolate():
    translate.set_locale("en-US")
    assert "my-server" in translate.t(
        "mcp.custom_server.success", server_name="my-server"
    )
    assert "my-server" in translate.t(
        "mcp.custom_server.start_hint", server_name="my-server"
    )


def test_bind_skipped_and_add_failed_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("mcp.custom_server.bind_skipped", error="boom")
    assert "boom" in translate.t("mcp.custom_server.add_failed", error="boom")
