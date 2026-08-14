"""Concrete key/interpolation contracts for extracted i18n namespaces (PUP-480).

The generic catalog-health sweeps (namespace populated / every key resolves
/ pseudolocalizes / no leftover placeholders) live in
``test_catalog_namespaces.py``. This module owns the *concrete* contracts:
one data row per translated key, grouped by the topic they belong to.

The rows below are the interpolation assertions that previously lived as
near-identical per-module test functions across six files
(test_cli_runner_i18n, test_config_commands_i18n, test_config_wizard_i18n,
test_core_commands_i18n, test_session_commands_i18n, test_claude_oauth_i18n).
Every key/needle pair is preserved exactly; only the boilerplate is gone.
"""

import pytest

from code_puppy.i18n import translate

# topic name -> [(key, params, (needles that must appear, ...)), ...]
_CONTRACTS = {
    "cli_keys_interpolate": [
        ("cli.model.using", {"model": "gpt-5"}, ("gpt-5",)),
        (
            "cli.resume.resumed",
            {"messages": 3, "tokens": 1200, "session": "demo"},
            ("demo",),
        ),
        ("cli.headless.error", {"error": "boom"}, ("boom",)),
        ("cli.autosave.loaded", {"messages": 42, "tokens": 999}, ("42",)),
        ("cli.autosave.loaded_path", {"path": "my.pkl"}, ("my.pkl",)),
    ],
    "cfg_keys_interpolate": [
        ("cfg.set.success", {"key": "theme", "value": "dark"}, ("theme",)),
        ("cfg.pin_model.success", {"model": "gpt-5", "agent": "coder"}, ("gpt-5",)),
        ("cfg.agent.not_found", {"agent": "coder"}, ("coder",)),
        ("cfg.unpin.failed", {"agent": "coder", "error": "boom"}, ("boom",)),
    ],
    "wizard_name_keys_interpolate": [
        ("mcp.wizard.name.exists", {"name": "my-srv"}, ("my-srv",)),
    ],
    "wizard_stdio_keys_interpolate": [
        ("mcp.wizard.stdio.dir_not_found", {"path": "/tmp/x"}, ("/tmp/x",)),
        ("mcp.wizard.test.config_error", {"error": "boom"}, ("boom",)),
    ],
    "wizard_summary_keys_interpolate": [
        ("mcp.wizard.summary.name", {"name": "myserver"}, ("myserver",)),
        ("mcp.wizard.summary.type", {"server_type": "stdio"}, ("stdio",)),
        ("mcp.wizard.summary.url", {"url": "http://x"}, ("http://x",)),
        (
            "mcp.wizard.summary.command",
            {"command": "node s.js"},
            ("node s.js",),
        ),
        ("mcp.wizard.summary.args", {"args": "--port 3000"}, ("--port 3000",)),
        ("mcp.wizard.summary.timeout", {"timeout": 30}, ("30",)),
    ],
    "wizard_added_keys_interpolate": [
        ("mcp.wizard.added", {"name": "myserver"}, ("myserver",)),
        ("mcp.wizard.hint_start", {"name": "myserver"}, ("myserver",)),
        ("mcp.wizard.server_id", {"id": "srv-001"}, ("srv-001",)),
    ],
    "wizard_error_keys_interpolate": [
        ("mcp.wizard.add_failed", {"error": "boom"}, ("boom",)),
        ("mcp.wizard.saved", {"path": "/tmp/mcp.json"}, ("/tmp/mcp.json",)),
        ("mcp.wizard.invalid_choice", {"choices": "a, b"}, ("a, b",)),
        ("mcp.wizard.input_error", {"error": "boom"}, ("boom",)),
    ],
    "cd_keys_interpolate": [
        ("cmd.cd.success", {"path": "/tmp"}, ("/tmp",)),
        ("cmd.cd.list_error", {"error": "boom"}, ("boom",)),
        ("cmd.cd.reload_error", {"error": "boom"}, ("boom",)),
        ("cmd.cd.not_a_dir", {"path": "/nope"}, ("/nope",)),
    ],
    "paste_keys_interpolate": [
        ("cmd.paste.count", {"count": 3}, ("3",)),
    ],
    "agent_keys_interpolate": [
        ("cmd.agent.already_using", {"agent": "coder"}, ("coder",)),
        ("cmd.agent.switched", {"agent": "coder"}, ("coder",)),
        ("cmd.agent.picker_failed", {"error": "boom"}, ("boom",)),
    ],
    "model_keys_interpolate": [
        ("cmd.model.success", {"model": "gpt-5"}, ("gpt-5",)),
        ("cmd.model.available", {"models": "gpt-5, claude-3"}, ("gpt-5",)),
        ("cmd.model.picker_failed", {"error": "boom"}, ("boom",)),
    ],
    "model_settings_keys_interpolate": [
        ("cmd.model_settings.reload_failed", {"error": "boom"}, ("boom",)),
        ("cmd.model_settings.failed", {"error": "boom"}, ("boom",)),
    ],
    "session_keys_interpolate": [
        (
            "cmd.session.info",
            {"name": "mysess", "prefix": "/tmp/x"},
            ("mysess",),
        ),
        ("cmd.session.new", {"name": "newsess"}, ("newsess",)),
    ],
    "clear_keys_interpolate": [
        ("cmd.clear.session_rotated", {"id": "abc123"}, ("abc123",)),
        ("cmd.clear.clipboard_cleared", {"count": 3}, ("3",)),
    ],
    "compact_keys_interpolate": [
        (
            "cmd.compact.compacting",
            {"count": 20, "strategy": "summary", "tokens": "4,000"},
            ("20",),
        ),
        (
            "cmd.compact.success.truncation",
            {
                "before_count": 20,
                "after_count": 5,
                "strategy": "truncation",
                "before_tokens": "4,000",
                "after_tokens": "1,000",
                "reduction_pct": "75.0",
            },
            ("truncation", "20"),
        ),
        (
            "cmd.compact.success.summarization",
            {
                "before_count": 20,
                "after_count": 5,
                "before_tokens": "4,000",
                "after_tokens": "1,000",
                "reduction_pct": "75.0",
            },
            ("summarization", "75.0"),
        ),
        ("cmd.compact.error", {"error": "boom"}, ("boom",)),
    ],
    "truncate_keys_interpolate": [
        ("cmd.truncate.already_short", {"current": 42, "n": 50}, ("42",)),
        ("cmd.truncate.success", {"before": 15, "after": 10, "kept": 9}, ("10",)),
    ],
    "quick_resume_keys_interpolate": [
        ("cmd.quick_resume.searching", {"scope": "myrepo/main"}, ("main",)),
        ("cmd.quick_resume.success", {"count": 7, "tokens": 1234}, ("7",)),
    ],
    "dump_context_keys_interpolate": [
        ("cmd.dump_context.invalid_name", {"name": "'bad'"}, ("'bad'",)),
        ("cmd.dump_context.failed", {"error": "boom"}, ("boom",)),
        # Load-bearing emoji: the checkmark + folder are part of the
        # /dump_context UX; keep asserting them so extractions can't drop them.
        (
            "cmd.dump_context.success",
            {
                "message_count": 10,
                "total_tokens": 2000,
                "pickle_path": "/tmp/ctx.pkl",
                "metadata_path": "/tmp/ctx.json",
            },
            ("10", "/tmp/ctx.pkl", "\u2705", "\U0001f4c1"),
        ),
    ],
    "load_context_keys_interpolate": [
        ("cmd.load_context.not_found", {"path": "/tmp/x.pkl"}, ("/tmp/x.pkl",)),
        ("cmd.load_context.available", {"contexts": "a, b"}, ("a, b",)),
        ("cmd.load_context.failed", {"error": "boom"}, ("boom",)),
        (
            "cmd.load_context.success",
            {
                "count": 5,
                "tokens": 1000,
                "path": "/tmp/x.pkl",
                "session_id": "auto_session_123",
                "file": "x.pkl",
            },
            ("5", "auto_session_123"),
        ),
    ],
    "oauth_server_keys_interpolate": [
        ("oauth.server.redirect_uri_error", {"error": "boom"}, ("boom",)),
        ("oauth.server.listening", {"uri": "http://x"}, ("http://x",)),
        ("oauth.server.pasteback_uri", {"uri": "http://x"}, ("http://x",)),
    ],
    "oauth_pasteback_keys_interpolate": [
        ("oauth.pasteback.parse_error", {"error": "boom"}, ("boom",)),
        ("oauth.pasteback.provider_error", {"message": "boom"}, ("boom",)),
    ],
    "oauth_callback_keys_interpolate": [
        ("oauth.callback.error", {"error": "500"}, ("500",)),
    ],
    "oauth_browser_keys_interpolate": [
        ("oauth.browser.headless_url", {"url": "https://x"}, ("https://x",)),
        ("oauth.browser.fallback_url", {"url": "https://x"}, ("https://x",)),
        ("oauth.browser.manual_url", {"url": "https://x"}, ("https://x",)),
        ("oauth.browser.open_failed", {"error": "boom"}, ("boom",)),
    ],
    "oauth_auth_keys_interpolate": [
        (
            "oauth.auth.discovered_models",
            {"count": 5, "models": "a, b"},
            ("5", "a, b"),
        ),
    ],
    "oauth_status_keys_interpolate": [
        ("oauth.cmd.status.expires", {"hours": 2, "minutes": 30}, ("2", "30")),
        ("oauth.claude.cmd.status.models", {"models": "claude-3"}, ("claude-3",)),
    ],
    "oauth_fast_keys_interpolate": [
        ("oauth.claude.cmd.fast.enabled", {"model": "opus"}, ("opus",)),
        ("oauth.claude.cmd.fast.disabled", {"model": "opus"}, ("opus",)),
    ],
    "oauth_logout_keys_interpolate": [
        ("oauth.cmd.logout.models_removed", {"count": 7}, ("7",)),
    ],
    "oauth_model_no_api_key_interpolates": [
        ("oauth.claude.model.no_api_key", {"model": "my-model"}, ("my-model",)),
    ],
}


@pytest.mark.parametrize(
    "cases",
    list(_CONTRACTS.values()),
    ids=list(_CONTRACTS),
)
def test_interpolation_contracts(cases):
    """Every key interpolates its named fields (no leftover placeholder)."""
    translate.set_locale("en-US")
    for key, params, needles in cases:
        rendered = translate.t(key, **params)
        for needle in needles:
            assert needle in rendered, f"{key}: {needle!r} not in {rendered!r}"


def test_colors_usage_renders_as_literal_placeholder():
    """{{color_type}} must render as the literal text {color_type}, never substituted."""
    rendered = translate.t("cfg.colors.usage")
    assert "{color_type}" in rendered, (
        f"Expected literal {{color_type}} in output, got: {rendered!r}"
    )


def test_type_keys_all_static():
    """Wizard type keys resolve to real (non-echoed) static text."""
    translate.set_locale("en-US")
    for key in ("mcp.wizard.type.sse", "mcp.wizard.type.http", "mcp.wizard.type.stdio"):
        val = translate.t(key)
        assert val and val != key


def test_add_model_failed_interpolates_error_param():
    """Guard against a param-name typo (e.g. ``{err}`` vs ``{error}``)."""
    translate.set_locale("en-US")
    rendered = translate.t("cmd.add_model.failed", error="XYZ")
    assert "XYZ" in rendered
    assert "{error}" not in rendered


@pytest.mark.parametrize(
    "module_name,attr",
    [
        ("code_puppy.cli_runner", "interactive_mode"),
        ("code_puppy.command_line.config_commands", "handle_unpin_command"),
        ("code_puppy.command_line.core_commands", "handle_cd_command"),
        ("code_puppy.mcp_.config_wizard", None),
        ("code_puppy.command_line.session_commands", None),
        ("code_puppy_core_plugins.claude_code_oauth.register_callbacks", None),
    ],
    ids=[
        "cli_runner",
        "config_commands",
        "core_commands",
        "config_wizard",
        "session_commands",
        "register_callbacks",
    ],
)
def test_module_imports_cleanly(module_name, attr):
    """Extracted modules must import without syntax/import errors."""
    import importlib

    mod = importlib.import_module(module_name)
    if attr:
        assert hasattr(mod, attr)
