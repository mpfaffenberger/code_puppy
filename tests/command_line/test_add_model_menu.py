"""Tests for the termflow-based add-model browser.

Pure logic (config building, context parsing, extra_models writes) plus
headless drives of the provider/model menus and TextInput flows.
"""

import json
from io import StringIO
from unittest.mock import patch

import pytest

from code_puppy.command_line import add_model_menu as amm
from code_puppy.models_dev_parser import ModelInfo, ProviderInfo


def make_provider(**kw):
    defaults = dict(
        id="acme", name="Acme AI", env=["ACME_API_KEY"], api="https://api.acme.ai/v1"
    )
    defaults.update(kw)
    return ProviderInfo(**defaults)


def make_model(**kw):
    defaults = dict(
        provider_id="acme",
        model_id="acme-large",
        name="Acme Large",
        tool_call=True,
        temperature=True,
        context_length=200000,
    )
    defaults.update(kw)
    return ModelInfo(**defaults)


class FakeRegistry:
    def __init__(self, providers, models):
        self._providers = providers
        self._models = models

    def get_providers(self):
        return self._providers

    def get_models(self, provider_id):
        return [m for m in self._models if m.provider_id == provider_id]


def scripted(factory, keys):
    """Wrap a menu factory so its menus run headlessly on scripted keys."""

    def build(*args, **kwargs):
        script = iter(keys)
        kwargs.setdefault("key_source", lambda: next(script))
        kwargs.setdefault("output", StringIO())
        kwargs.setdefault("size", lambda: (110, 30))
        return factory(*args, **kwargs)

    return build


# -- pure logic --------------------------------------------------------------


class TestProviderIdentity:
    def test_mapped_and_fallback(self):
        assert (
            amm.derive_provider_identity(make_provider(id="together-ai"))
            == "together_ai"
        )
        assert (
            amm.derive_provider_identity(make_provider(id="some-new-guy"))
            == "some_new_guy"
        )


class TestParseContextSize:
    def test_forms(self):
        assert amm.parse_context_size("200000") == 200000
        assert amm.parse_context_size("128k") == 128000
        assert amm.parse_context_size("1M") == 1000000
        assert amm.parse_context_size("1,000") == 1000
        assert amm.parse_context_size("") == 128000
        assert amm.parse_context_size("  ", default=42) == 42
        assert amm.parse_context_size("banana") is None


class TestBuildModelConfig:
    def test_native_openai(self):
        config = amm.build_model_config(
            make_model(), make_provider(id="openai", env=["OPENAI_API_KEY"])
        )
        assert config["type"] == "openai"
        assert "custom_endpoint" not in config

    def test_custom_openai_uses_provider_api(self):
        config = amm.build_model_config(
            make_model(), make_provider(id="groq", env=["GROQ_API_KEY"])
        )
        assert config["type"] == "custom_openai"
        assert config["custom_endpoint"]["api_key"] == "$GROQ_API_KEY"

    def test_custom_openai_endpoint_fallback(self):
        provider = make_provider(id="xai", api="N/A", env=["XAI_API_KEY"])
        config = amm.build_model_config(make_model(), provider)
        assert config["custom_endpoint"]["url"] == amm.PROVIDER_ENDPOINTS["xai"]

    def test_minimax_strips_v1(self):
        provider = make_provider(
            id="minimax",
            api="https://api.minimax.io/anthropic/v1",
            env=["MINIMAX_API_KEY"],
        )
        config = amm.build_model_config(make_model(), provider)
        assert config["type"] == "custom_anthropic"
        assert config["custom_endpoint"]["url"] == "https://api.minimax.io/anthropic"

    def test_supported_settings_variants(self):
        anth = amm.build_model_config(make_model(), make_provider(id="anthropic"))
        assert "extended_thinking" in anth["supported_settings"]
        gpt5 = amm.build_model_config(
            make_model(model_id="gpt-5-codex"), make_provider(id="openai")
        )
        assert gpt5["supported_settings"] == [
            "temperature",
            "top_p",
            "reasoning_effort",
        ]
        fixed_effort = amm.build_model_config(
            make_model(model_id="gpt-5-pro"), make_provider(id="openai")
        )
        assert fixed_effort["supported_settings"] == [
            "temperature",
            "seed",
            "top_p",
        ]
        default = amm.build_model_config(make_model(), make_provider(id="groq"))
        assert default["supported_settings"] == ["temperature", "seed", "top_p"]

    def test_context_length_carried(self):
        config = amm.build_model_config(
            make_model(context_length=42000), make_provider()
        )
        assert config["context_length"] == 42000

    def test_max_output_tokens_carried_from_models_dev(self):
        config = amm.build_model_config(make_model(max_output=64000), make_provider())
        assert config["max_output_tokens"] == 64000

    def test_max_output_tokens_omitted_when_unknown(self):
        config = amm.build_model_config(make_model(max_output=0), make_provider())
        assert "max_output_tokens" not in config


class TestExtraModelsWrite:
    def test_adds_then_reports_duplicate(self, tmp_path):
        target = tmp_path / "extra_models.json"
        with patch.object(amm, "EXTRA_MODELS_FILE", str(target)):
            assert amm.add_model_to_extra_config(make_model(), make_provider()) is True
            data = json.loads(target.read_text())
            assert "acme-acme-large" in data
            # Second add: keeps file intact, still returns True.
            assert amm.add_model_to_extra_config(make_model(), make_provider()) is True
            assert len(json.loads(target.read_text())) == 1

    def test_non_dict_file_rejected(self, tmp_path):
        target = tmp_path / "extra_models.json"
        target.write_text("[]")
        with patch.object(amm, "EXTRA_MODELS_FILE", str(target)):
            assert amm.add_model_to_extra_config(make_model(), make_provider()) is False


class TestMissingEnvVars:
    def test_reports_only_unset(self, monkeypatch):
        provider = make_provider(env=["SET_ONE", "UNSET_ONE"])
        monkeypatch.setenv("SET_ONE", "x")
        monkeypatch.delenv("UNSET_ONE", raising=False)
        assert amm.missing_env_vars(provider) == ["UNSET_ONE"]


class TestCustomModelInfo:
    def test_defaults(self):
        info = amm.create_custom_model_info("acme", "my-model", 64000)
        assert info.tool_call is True
        assert info.max_output == 16000
        assert info.context_length == 64000


# -- previews ----------------------------------------------------------------


class TestDetailPreviews:
    def test_provider_details_flags_unsupported_and_credentials(self):
        provider = make_provider(id="amazon-bedrock", env=["AWS_THING"])
        text = amm.provider_details(provider)
        assert "UNSUPPORTED" in text
        assert "AWS_THING" in text

    def test_model_details_warns_on_no_tool_call(self):
        text = amm.model_details(make_model(tool_call=False), make_provider())
        assert "NO TOOL CALLING" in text

    def test_custom_model_details_mentions_provider(self):
        assert "Acme AI" in amm.custom_model_details(make_provider())


# -- menus (headless) --------------------------------------------------------


class TestMenus:
    def test_provider_menu_search_and_select(self):
        providers = [make_provider(), make_provider(id="zeta", name="Zeta", env=[])]
        menu = amm.build_provider_menu(
            providers,
            key_source=iter(["z", "enter"]).__next__,
            output=StringIO(),
            size=lambda: (110, 30),
        )
        result = menu.run()
        assert result.item.value.id == "zeta"

    def test_provider_menu_ctrl_e_returns_sentinel(self):
        menu = amm.build_provider_menu(
            [make_provider()],
            key_source=iter(["ctrl-e"]).__next__,
            output=StringIO(),
            size=lambda: (110, 30),
        )
        result = menu.run()
        kind, provider = result.item.value
        assert kind == amm._EDIT_CREDENTIALS
        assert provider.id == "acme"

    def test_models_menu_lists_custom_entry_last(self):
        out = StringIO()
        menu = amm.build_models_menu(
            make_provider(),
            [make_model()],
            key_source=iter(["down", "enter"]).__next__,
            output=out,
            size=lambda: (110, 30),
        )
        result = menu.run()
        assert result.item.value == amm._CUSTOM_MODEL_VALUE
        assert "Custom model" in out.getvalue()

    def test_confirm_no_tool_call_defaults_no(self):
        assert (
            amm.confirm_no_tool_call(
                make_model(tool_call=False),
                key_source=iter(["enter"]).__next__,
                output=StringIO(),
                size=lambda: (110, 30),
            )
            is False
        )
        assert (
            amm.confirm_no_tool_call(
                make_model(tool_call=False),
                key_source=iter(["down", "enter"]).__next__,
                output=StringIO(),
                size=lambda: (110, 30),
            )
            is True
        )


# -- TextInput flows (headless) ----------------------------------------------


class TestCredentialFlows:
    def _keys(self, *keys):
        script = iter(keys)
        return {
            "key_source": lambda: next(script),
            "output": StringIO(),
            "size": lambda: (90, 20),
        }

    def test_prompt_saves_typed_credential(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)
        with patch.object(amm, "set_config_value") as mock_set:
            ok = amm.prompt_for_credentials(
                make_provider(), **self._keys("s", "k", "enter")
            )
        assert ok is True
        mock_set.assert_called_once_with("ACME_API_KEY", "sk")
        import os

        assert os.environ.pop("ACME_API_KEY") == "sk"

    def test_prompt_empty_skips(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)
        with patch.object(amm, "set_config_value") as mock_set:
            assert amm.prompt_for_credentials(make_provider(), **self._keys("enter"))
        mock_set.assert_not_called()

    def test_prompt_escape_cancels(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)
        assert (
            amm.prompt_for_credentials(make_provider(), **self._keys("escape")) is False
        )

    def test_prompt_noop_when_all_set(self, monkeypatch):
        monkeypatch.setenv("ACME_API_KEY", "present")
        assert amm.prompt_for_credentials(make_provider()) is True

    def test_editor_saves_via_save_credential(self):
        with patch.object(amm, "save_credential") as mock_save:
            ok = amm.edit_provider_credentials(
                make_provider(), **self._keys("n", "e", "w", "enter")
            )
        assert ok is True
        mock_save.assert_called_once_with("ACME_API_KEY", "new")

    def test_editor_empty_keeps_current(self):
        with patch.object(amm, "save_credential") as mock_save:
            assert amm.edit_provider_credentials(make_provider(), **self._keys("enter"))
        mock_save.assert_not_called()


class TestProviderCredentialFlowHook:
    """The provider_credential_flow seam in prompt_for_credentials."""

    def _keys(self, *keys):
        script = iter(keys)
        return {
            "key_source": lambda: next(script),
            "output": StringIO(),
            "size": lambda: (90, 20),
        }

    def test_hook_handles_credential_skips_manual_prompt(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)

        def fake_hook(*, provider_id, env_var):
            assert provider_id == "acme"
            assert env_var == "ACME_API_KEY"
            monkeypatch.setenv(env_var, "oauth-minted")
            return True

        with patch("code_puppy.callbacks.on_provider_credential_flow", fake_hook):
            # No keys scripted: reaching the TextInput would blow up the test.
            assert amm.prompt_for_credentials(make_provider(), **self._keys()) is True

    def test_hook_true_without_env_falls_back_to_manual(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)
        with (
            patch(
                "code_puppy.callbacks.on_provider_credential_flow",
                lambda **kw: True,  # lies: never actually sets the env var
            ),
            patch.object(amm, "set_config_value") as mock_set,
        ):
            ok = amm.prompt_for_credentials(
                make_provider(), **self._keys("s", "k", "enter")
            )
        assert ok is True
        mock_set.assert_called_once_with("ACME_API_KEY", "sk")
        import os

        assert os.environ.pop("ACME_API_KEY") == "sk"

    def test_hook_deferring_falls_back_to_manual(self, monkeypatch):
        monkeypatch.delenv("ACME_API_KEY", raising=False)
        with (
            patch(
                "code_puppy.callbacks.on_provider_credential_flow",
                lambda **kw: False,
            ),
            patch.object(amm, "set_config_value") as mock_set,
        ):
            ok = amm.prompt_for_credentials(
                make_provider(), **self._keys("s", "k", "enter")
            )
        assert ok is True
        mock_set.assert_called_once_with("ACME_API_KEY", "sk")
        import os

        assert os.environ.pop("ACME_API_KEY") == "sk"

    def test_on_provider_credential_flow_short_circuits(self):
        from code_puppy import callbacks

        calls = []

        def first(**kw):
            calls.append("first")
            return True

        def second(**kw):
            calls.append("second")
            return True

        callbacks.register_callback("provider_credential_flow", first)
        callbacks.register_callback("provider_credential_flow", second)
        try:
            assert (
                callbacks.on_provider_credential_flow(
                    provider_id="acme", env_var="ACME_API_KEY"
                )
                is True
            )
            assert calls == ["first"]
        finally:
            callbacks.unregister_callback("provider_credential_flow", first)
            callbacks.unregister_callback("provider_credential_flow", second)

    def test_on_provider_credential_flow_isolates_errors(self):
        from code_puppy import callbacks

        def boom(**kw):
            raise RuntimeError("kaboom")

        def fine(**kw):
            return True

        callbacks.register_callback("provider_credential_flow", boom)
        callbacks.register_callback("provider_credential_flow", fine)
        try:
            assert (
                callbacks.on_provider_credential_flow(
                    provider_id="acme", env_var="ACME_API_KEY"
                )
                is True
            )
        finally:
            callbacks.unregister_callback("provider_credential_flow", boom)
            callbacks.unregister_callback("provider_credential_flow", fine)

    def test_on_provider_credential_flow_no_callbacks(self):
        from code_puppy import callbacks

        assert (
            callbacks.on_provider_credential_flow(
                provider_id="acme", env_var="ACME_API_KEY"
            )
            is False
        )


class TestCustomModelPrompt:
    def _keys(self, *keys):
        script = iter(keys)
        return {
            "key_source": lambda: next(script),
            "output": StringIO(),
            "size": lambda: (90, 20),
        }

    def test_happy_path_with_k_suffix(self):
        result = amm.prompt_for_custom_model(
            make_provider(), **self._keys("m", "1", "enter", "6", "4", "k", "enter")
        )
        assert result == ("m1", 64000)

    def test_empty_context_defaults(self):
        result = amm.prompt_for_custom_model(
            make_provider(), **self._keys("m", "enter", "enter")
        )
        assert result == ("m", 128000)

    def test_cancel_returns_none(self):
        assert (
            amm.prompt_for_custom_model(make_provider(), **self._keys("escape")) is None
        )


# -- orchestration -----------------------------------------------------------


class TestRunAddModelFlow:
    def _registry(self, provider=None, model=None):
        provider = provider or make_provider()
        model = model or make_model()
        return FakeRegistry([provider], [model]), provider, model

    def test_full_add_path(self, tmp_path, monkeypatch):
        registry, provider, model = self._registry()
        monkeypatch.setenv("ACME_API_KEY", "set")
        target = tmp_path / "extra.json"
        with patch.object(amm, "EXTRA_MODELS_FILE", str(target)):
            added = amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=scripted(amm.build_provider_menu, ["enter"]),
                models_menu_factory=scripted(amm.build_models_menu, ["enter"]),
            )
        assert added is True
        assert "acme-acme-large" in json.loads(target.read_text())

    def test_cancel_at_providers(self):
        registry, *_ = self._registry()
        assert (
            amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=scripted(amm.build_provider_menu, ["escape"]),
            )
            is False
        )

    def test_escape_in_models_returns_to_providers(self):
        registry, *_ = self._registry()
        provider_scripts = iter([["enter"], ["escape"]])
        models_scripts = iter([["escape"]])

        def provider_factory(providers, **kw):
            return scripted(amm.build_provider_menu, next(provider_scripts))(
                providers, **kw
            )

        def models_factory(provider, models, **kw):
            return scripted(amm.build_models_menu, next(models_scripts))(
                provider, models, **kw
            )

        assert (
            amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=provider_factory,
                models_menu_factory=models_factory,
            )
            is False
        )

    def test_unsupported_provider_blocks_add(self):
        provider = make_provider(id="amazon-bedrock", name="Bedrock", env=[])
        registry = FakeRegistry([provider], [make_model(provider_id="amazon-bedrock")])
        assert (
            amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=scripted(amm.build_provider_menu, ["enter"]),
                models_menu_factory=scripted(amm.build_models_menu, ["enter"]),
            )
            is False
        )

    def test_custom_model_path(self, tmp_path, monkeypatch):
        registry, provider, _ = self._registry()
        monkeypatch.setenv("ACME_API_KEY", "set")
        target = tmp_path / "extra.json"
        with patch.object(amm, "EXTRA_MODELS_FILE", str(target)):
            added = amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=scripted(amm.build_provider_menu, ["enter"]),
                models_menu_factory=scripted(amm.build_models_menu, ["down", "enter"]),
                custom_model_prompt=lambda p: ("shiny-new", 32000),
            )
        assert added is True
        assert "acme-shiny-new" in json.loads(target.read_text())

    def test_no_tool_call_requires_confirmation(self, tmp_path, monkeypatch):
        provider = make_provider()
        model = make_model(tool_call=False)
        registry = FakeRegistry([provider], [model])
        monkeypatch.setenv("ACME_API_KEY", "set")
        target = tmp_path / "extra.json"
        with patch.object(amm, "EXTRA_MODELS_FILE", str(target)):
            added = amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=scripted(amm.build_provider_menu, ["enter"]),
                models_menu_factory=scripted(amm.build_models_menu, ["enter"]),
                tool_call_confirm=lambda m: False,
            )
        assert added is False
        assert not target.exists()

    def test_ctrl_e_edits_credentials_then_reopens(self):
        registry, provider, _ = self._registry()
        edited = []
        provider_scripts = iter([["ctrl-e"], ["escape"]])

        def provider_factory(providers, **kw):
            return scripted(amm.build_provider_menu, next(provider_scripts))(
                providers, **kw
            )

        assert (
            amm.run_add_model_flow(
                registry=registry,
                provider_menu_factory=provider_factory,
                credentials_editor=lambda p: edited.append(p.id) or True,
            )
            is False
        )
        assert edited == ["acme"]

    def test_empty_registry_fails_cleanly(self):
        assert amm.run_add_model_flow(registry=FakeRegistry([], [])) is False


class TestConstants:
    def test_openai_compatible_endpoints_exist(self):
        assert "groq" in amm.PROVIDER_ENDPOINTS
        assert all(v.startswith("https://") for v in amm.PROVIDER_ENDPOINTS.values())

    def test_unsupported_providers_listed(self):
        assert "amazon-bedrock" in amm.UNSUPPORTED_PROVIDERS

    def test_env_hints_cover_major_providers(self):
        assert "OPENAI_API_KEY" in amm.ENV_VAR_HINTS
        assert pytest  # keep import honest
