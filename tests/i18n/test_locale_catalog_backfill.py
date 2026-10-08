"""Runtime and technical-token contracts for the locale catalog backfill."""

import json
import re
from pathlib import Path

import pytest
from rich.text import Text

from code_puppy.i18n import translate

_CATALOG_DIR = Path(__file__).parents[2] / "code_puppy" / "i18n" / "locales"
_LOCALES = tuple(path.stem for path in _CATALOG_DIR.glob("*.json"))
# Names are taken from callers, never inferred from the translated templates.
_REAL_PARAMS = {
    "cfg.set.success": {"key": "theme", "value": "dark"},
    "cfg.pin_model.failed": {"agent": "coder", "error": "failure"},
    "cfg.pin_model.success": {"model": "model-name", "agent": "coder"},
    "cli.agency.status": {"level": "medium"},
    "cli.agent.quit_cancel_timeout": {"seconds": 5},
    "cli.attachments.detected": {"summary": "attachments-summary"},
    "cli.attachments.clipboard_images": {"count": 3},
    "cli.autosave.loaded": {"messages": 42, "tokens": 999},
    "cli.autosave.loaded_path": {"path": "/tmp/image.png"},
    "cli.context.cleared": {"session": "session-name"},
    "cli.error.model_transient": {"error_type": "ConnectionError"},
    "cli.error.no_ports": {"port_base": 8000, "port_end": 8010},
    "cli.headless.executing": {"prompt": "instructions"},
    "cli.initial_command.processing": {"command": "/help"},
    "cli.resume.failed": {"target": "session-target", "error": "failure"},
    "cli.resume.quick_searching": {"scope": "project-scope"},
    "cli.resume.resumed": {"messages": 42, "tokens": 999, "session": "demo"},
    "cmd.refresh_models.summary": {"updated": 42, "unchanged": 999},
    "cmd.refresh_models.updated": {"model_key": "model-name"},
    "codex.imagegen.request_failed": {"detail": ": failure"},
    "credentials.migration_conflict": {"key": "API_KEY"},
    "mcp.http_form.auth_value": {"auth": "oauth"},
    "mcp.http_form.name": {"name": "server-name"},
    "oauth.meta.auth.code": {"code": "ABCD-1234"},
    "oauth.meta.browser.failed": {"error": "failure", "url": "https://example.org"},
    "oauth.meta.logout.external": {"source": "environment"},
    "oauth.meta.status.models": {"models": "model-a, model-b"},
    "subagent.gpt_5_6_recursion_blocked": {"agent": "coder", "depth": 3, "limit": 2},
    "subagent.recursion_limit_reached": {"limit": 2, "agent": "coder"},
}


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("key,params", _REAL_PARAMS.items())
def test_backfilled_keys_render_real_caller_params(locale, key, params):
    translate.set_locale(locale)
    rendered = translate.t(key, **params)
    assert rendered != key
    assert "{" not in rendered and "}" not in rendered
    for value in params.values():
        assert str(value) in rendered


@pytest.mark.parametrize("locale", _LOCALES)
def test_mcp_help_preserves_executable_commands(locale):
    def commands(language):
        translate.set_locale(language)
        return [
            re.split(r"\s{2,}", line)[0]
            for line in translate.t("mcp.custom_install.help").splitlines()[1:]
        ]

    assert commands(locale) == commands("en-US")


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(
    "key,tokens",
    [
        ("cli.prompt_toolkit.installing", ("prompt_toolkit",)),
        ("cli.prompt_toolkit.installed", ("prompt_toolkit",)),
        ("cli.prompt_toolkit.install_error", ("prompt_toolkit",)),
        ("cli.version.update_disabled", ("NO_VERSION_UPDATE", "1", "true")),
        ("cmd.refresh_models.unmatched", ("models.dev",)),
        ("logfire.missing_package", ("enable_logfire", "logfire", "code-puppy")),
        ("mcp.custom_install.no_marketplace", ("/mcp install",)),
        ("mcp.oauth.invalid_method", ("'oauth'",)),
        ("mcp.oauth.header_conflict", ("Authorization",)),
        ("codex.imagegen.usage", ("/codex-imagegen <prompt>",)),
    ],
)
def test_backfilled_keys_preserve_technical_tokens(locale, key, tokens):
    translate.set_locale(locale)
    rendered = translate.t(key, error="failure")
    for token in tokens:
        assert token in rendered


@pytest.mark.parametrize("locale", _LOCALES)
def test_oauth_confirmation_keeps_advertised_parser_token(locale, monkeypatch):
    from code_puppy.mcp_ import config_wizard

    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return "y"

    monkeypatch.setattr(config_wizard, "emit_prompt", answer)
    translate.set_locale(locale)
    assert config_wizard.confirm_ask(translate.t("mcp.oauth.prompt"), default=False)
    assert prompts == [translate.t("mcp.oauth.prompt") + " [y/N]: "]


@pytest.mark.parametrize("locale", _LOCALES)
def test_meta_browser_label_renders_literally(locale):
    translate.set_locale(locale)
    rendered = translate.t("oauth.meta.browser.headless", url="https://example.org")
    assert Text(rendered).plain == rendered


@pytest.mark.parametrize("locale", ("es", "fr-CA"))
def test_reviewed_corruption_does_not_return(locale):
    values = json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    corrupt = re.compile(
        r"Cancelarling|ejecutyo|abyoned|cancelarada|commy|clesond|Cargyo|Instalyo|"
        r"ningún (?:puede|se)|destponibles|utilestation|utilestez|enregesttrée|"
        r"Annulerling|besontr|Supprimerd|cannot invoquer|it était stuck"
    )
    for key, value in values.items():
        forms = [value] if isinstance(value, str) else list(value.values())
        for form in forms:
            assert not corrupt.search(form), key
