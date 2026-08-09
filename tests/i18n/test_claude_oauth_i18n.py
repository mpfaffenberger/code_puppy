"""i18n coverage for the claude_code_oauth/register_callbacks extraction.

Validates the concrete ``oauth.*`` key/interpolation contracts introduced
by this extraction. Integration with the live OAuth flow is tested
elsewhere; this suite focuses purely on catalog correctness. The generic
namespace sweep lives in ``test_catalog_namespaces.py``.
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


def test_server_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("oauth.server.redirect_uri_error", error="boom")
    assert "http://x" in translate.t("oauth.server.listening", uri="http://x")
    assert "http://x" in translate.t("oauth.server.pasteback_uri", uri="http://x")


def test_pasteback_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("oauth.pasteback.parse_error", error="boom")
    assert "boom" in translate.t("oauth.pasteback.provider_error", message="boom")


def test_callback_keys_interpolate():
    translate.set_locale("en-US")
    assert "500" in translate.t("oauth.callback.error", error="500")


def test_browser_keys_interpolate():
    translate.set_locale("en-US")
    for key in (
        "oauth.browser.headless_url",
        "oauth.browser.fallback_url",
        "oauth.browser.manual_url",
    ):
        assert "https://x" in translate.t(key, url="https://x")
    assert "boom" in translate.t("oauth.browser.open_failed", error="boom")


def test_auth_keys_interpolate():
    translate.set_locale("en-US")
    assert "5" in translate.t("oauth.auth.discovered_models", count=5, models="a, b")
    assert "a, b" in translate.t("oauth.auth.discovered_models", count=5, models="a, b")


def test_status_keys_interpolate():
    translate.set_locale("en-US")
    assert "2" in translate.t("oauth.cmd.status.expires", hours=2, minutes=30)
    assert "30" in translate.t("oauth.cmd.status.expires", hours=2, minutes=30)
    assert "claude-3" in translate.t(
        "oauth.claude.cmd.status.models", models="claude-3"
    )


def test_fast_keys_interpolate():
    translate.set_locale("en-US")
    assert "opus" in translate.t("oauth.claude.cmd.fast.enabled", model="opus")
    assert "opus" in translate.t("oauth.claude.cmd.fast.disabled", model="opus")


def test_logout_keys_interpolate():
    translate.set_locale("en-US")
    assert "7" in translate.t("oauth.cmd.logout.models_removed", count=7)


def test_model_no_api_key_interpolates():
    translate.set_locale("en-US")
    assert "my-model" in translate.t("oauth.claude.model.no_api_key", model="my-model")


def test_register_callbacks_imports_cleanly():
    import code_puppy.plugins.claude_code_oauth.register_callbacks  # noqa: F401


def test_no_raw_emit_in_register_callbacks():
    """Fail fast if any emit_* call bypasses t() in the OAuth plugin."""
    import ast
    import pathlib

    src = pathlib.Path(
        "code_puppy/plugins/claude_code_oauth/register_callbacks.py"
    ).read_text()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            fn_name = (
                fn.id
                if isinstance(fn, ast.Name)
                else (fn.attr if isinstance(fn, ast.Attribute) else "")
            )
            if fn_name.startswith("emit_"):
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.strip()
                    ):
                        offenders.append((node.lineno, fn_name, arg.value[:50]))
                    elif isinstance(arg, ast.JoinedStr):
                        for v in arg.values:
                            if (
                                isinstance(v, ast.Constant)
                                and isinstance(v.value, str)
                                and v.value.strip()
                            ):
                                offenders.append((node.lineno, fn_name, "f-string"))
                                break
    assert not offenders, f"Raw emit_* calls found: {offenders}"
