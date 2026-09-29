"""Tests for the vLLM ``/add_model`` path (URL -> /v1/models -> pick)."""

import json
from unittest.mock import patch

import httpx
import pytest

from code_puppy.command_line import add_model_menu as amm
from code_puppy.command_line import add_model_vllm as vllm


# -- URL normalization --------------------------------------------------------


class TestUrlHelpers:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://localhost:8000", "http://localhost:8000"),
            ("http://localhost:8000/", "http://localhost:8000"),
            ("  http://host:8000/v1  ", "http://host:8000"),
            ("http://host:8000/v1/models", "http://host:8000"),
            ("https://vllm.internal", "https://vllm.internal"),
            ("", ""),
        ],
    )
    def test_normalize_base_url(self, raw, expected):
        assert vllm.normalize_base_url(raw) == expected

    def test_endpoints_rebuilt_without_doubling(self):
        assert vllm.openai_endpoint("http://h:1/v1") == "http://h:1/v1"
        assert vllm.models_endpoint("http://h:1") == "http://h:1/v1/models"
        assert vllm.models_endpoint("http://h:1/v1/models") == "http://h:1/v1/models"


# -- fetching -----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class TestFetchModels:
    @pytest.mark.parametrize(
        "base",
        ["http://h:1", "http://h:1/", "http://h:1/v1", "http://h:1/v1/models"],
    )
    def test_requests_exactly_v1_models(self, base):
        seen = []

        def spy(url, timeout, headers):
            seen.append(url)
            return _FakeResponse({"data": []})

        vllm.fetch_vllm_model_ids(base, http_get=spy)
        assert seen == ["http://h:1/v1/models"]

    def test_happy_path_strips_and_filters(self):
        payload = {"data": [{"id": "m1"}, {"id": " m2 "}, {}, {"id": ""}]}
        ids = vllm.fetch_vllm_model_ids(
            "http://localhost:8000",
            http_get=lambda url, timeout, headers: _FakeResponse(payload),
        )
        assert ids == ["m1", "m2"]

    def test_transport_error_becomes_fetch_error(self):
        def boom(url, timeout, headers):
            raise httpx.ConnectError("refused")

        with pytest.raises(vllm.VllmFetchError):
            vllm.fetch_vllm_model_ids("http://h:1", http_get=boom)

    def test_non_json_body_becomes_fetch_error(self):
        def bad_json(url, timeout, headers):
            raise ValueError("no json")

        with pytest.raises(vllm.VllmFetchError):
            vllm.fetch_vllm_model_ids("http://h:1", http_get=bad_json)

    def test_missing_data_list_becomes_fetch_error(self):
        with pytest.raises(vllm.VllmFetchError):
            vllm.fetch_vllm_model_ids(
                "http://h:1",
                http_get=lambda url, timeout, headers: _FakeResponse({"oops": 1}),
            )


class TestResolveApiKeyRef:
    def test_placeholder_and_blank_are_none(self):
        assert vllm.resolve_api_key_ref("EMPTY") is None
        assert vllm.resolve_api_key_ref("") is None

    def test_env_ref_resolves_through_credential_store(self, monkeypatch):
        monkeypatch.setattr(
            vllm, "get_credential_value", lambda n: "sk-x" if n == "MY_KEY" else None
        )
        assert vllm.resolve_api_key_ref("$MY_KEY") == "sk-x"
        assert vllm.resolve_api_key_ref("$NOPE") is None

    def test_literal_passes_through(self):
        assert vllm.resolve_api_key_ref("literal") == "literal"


# -- config -------------------------------------------------------------------


class TestBuildConfig:
    def test_custom_openai_shape(self):
        config = vllm.build_vllm_model_config("llama-3", "http://h:1", "$VLLM_API_KEY")
        assert config["type"] == "custom_openai"
        assert config["provider"] == "vllm"
        assert config["name"] == "llama-3"
        assert config["custom_endpoint"] == {
            "url": "http://h:1/v1",
            "api_key": "$VLLM_API_KEY",
        }


# -- orchestration ------------------------------------------------------------


class _FakeResult:
    def __init__(self, value):
        self.cancelled = value is None
        self.item = None if value is None else type("I", (), {"value": value})()


class _FakeMenu:
    def __init__(self, value):
        self._value = value

    def run(self):
        return _FakeResult(self._value)


class TestRunVllmFlow:
    def _flow(self, tmp_path, credential="sk-test", **kw):
        target = tmp_path / "extra.json"
        defaults = dict(
            url_prompt=lambda: "http://localhost:8000",
            fetch_models=lambda base, api_key=None: ["llama-3", "mistral-7b"],
            models_menu_factory=lambda base, ids: _FakeMenu("llama-3"),
            api_key_prompt=lambda: "$VLLM_API_KEY",
        )
        defaults.update(kw)
        with (
            patch.object(amm, "EXTRA_MODELS_FILE", str(target)),
            patch.object(vllm, "get_credential_value", lambda n: credential),
        ):
            added = vllm.run_vllm_flow(**defaults)
        return added, target

    def test_happy_path_persists_key_ref(self, tmp_path):
        added, target = self._flow(tmp_path)
        assert added is True
        data = json.loads(target.read_text())
        assert data["vllm-llama-3"]["custom_endpoint"] == {
            "url": "http://localhost:8000/v1",
            "api_key": "$VLLM_API_KEY",
        }

    def test_new_key_then_explicit_second_model_selection(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vllm, "credential_env_var_names", lambda: set())
        monkeypatch.setattr(vllm, "is_credential_set", lambda name: False)
        script = _keys("s", "k", "enter", "down", "enter")
        with patch.object(vllm, "save_credential") as save:
            added, target = self._flow(
                tmp_path,
                api_key_prompt=lambda: "$" + vllm.prompt_for_new_vllm_api_key(**script),
                models_menu_factory=lambda base, ids: vllm.build_vllm_models_menu(
                    base, ids, **script
                ),
            )
        assert added
        save.assert_called_once_with("VLLM_API_KEY0", "sk")
        data = json.loads(target.read_text())
        assert list(data) == ["vllm-mistral-7b"]
        assert data["vllm-mistral-7b"]["custom_endpoint"]["api_key"] == "$VLLM_API_KEY0"

    def test_placeholder_ref_passes_through(self, tmp_path):
        added, target = self._flow(tmp_path, api_key_prompt=lambda: "EMPTY")
        assert added is True
        data = json.loads(target.read_text())
        assert data["vllm-llama-3"]["custom_endpoint"]["api_key"] == "EMPTY"

    def test_key_step_cancelled(self, tmp_path):
        added, target = self._flow(tmp_path, api_key_prompt=lambda: None)
        assert added is False
        assert not target.exists()

    def test_key_is_chosen_before_fetch_and_forwarded(self, tmp_path, monkeypatch):
        """A gated server 401s on /v1/models, so the key must precede the fetch."""
        monkeypatch.setattr(vllm, "get_credential_value", lambda n: "sk-live")
        order = []

        def fetch(base, api_key=None):
            order.append(("fetch", api_key))
            return ["llama-3"]

        def key():
            order.append(("key", None))
            return "$VLLM_API_KEY"

        added, _ = self._flow(
            tmp_path, credential="sk-live", fetch_models=fetch, api_key_prompt=key
        )
        assert added is True
        assert order == [("key", None), ("fetch", "sk-live")]

    def test_fetch_error_after_key_writes_nothing(self, tmp_path):
        def boom(base, api_key=None):
            raise vllm.VllmFetchError("401 Unauthorized")

        added, target = self._flow(tmp_path, fetch_models=boom)
        assert added is False
        assert not target.exists()

    def test_empty_saved_key_refuses_before_fetch(self, tmp_path):
        """A chosen-but-blank $ENV must not go out as an anonymous request."""
        fetched = []

        def fetch(base, api_key=None):
            fetched.append(api_key)
            return ["llama-3"]

        with patch.object(vllm, "emit_error") as err:
            added, target = self._flow(tmp_path, credential=None, fetch_models=fetch)
        assert added is False
        assert fetched == []
        assert not target.exists()
        assert "VLLM_API_KEY" in err.call_args.args[0]

    @pytest.mark.parametrize(
        "error, authenticated, expected_key",
        [
            ("401 Unauthorized", False, "hint_401_anon"),
            ("401 Unauthorized", True, "hint_401_authed"),
            ("403 Forbidden", True, "hint_403"),
        ],
    )
    def test_auth_failure_hint(self, error, authenticated, expected_key):
        from code_puppy.i18n import t

        hint = vllm._auth_failure_hint(error, authenticated=authenticated)
        assert hint == t(f"model_menu.vllm.{expected_key}")

    def test_non_auth_failure_has_no_hint(self):
        assert vllm._auth_failure_hint("Connection refused", authenticated=True) is None

    def test_403_surfaces_a_hint(self, tmp_path):
        def boom(base, api_key=None):
            raise vllm.VllmFetchError("Client error '403 Forbidden'")

        with patch.object(vllm, "emit_warning") as warn:
            added, _ = self._flow(tmp_path, fetch_models=boom)
        assert added is False
        assert "rejected" in warn.call_args.args[0]

    def test_url_cancelled(self):
        assert vllm.run_vllm_flow(url_prompt=lambda: None) is False

    def test_fetch_error_reported(self):
        def boom(base, api_key=None):
            raise vllm.VllmFetchError("refused")

        assert (
            vllm.run_vllm_flow(
                url_prompt=lambda: "http://h:1",
                api_key_prompt=lambda: "EMPTY",
                fetch_models=boom,
            )
            is False
        )

    def test_no_models_served(self):
        assert (
            vllm.run_vllm_flow(
                url_prompt=lambda: "http://h:1",
                api_key_prompt=lambda: "EMPTY",
                fetch_models=lambda base, api_key=None: [],
            )
            is False
        )

    def test_menu_cancelled(self):
        assert (
            vllm.run_vllm_flow(
                url_prompt=lambda: "http://h:1",
                api_key_prompt=lambda: "EMPTY",
                fetch_models=lambda base, api_key=None: ["m"],
                models_menu_factory=lambda base, ids: _FakeMenu(None),
            )
            is False
        )


# -- API key selection --------------------------------------------------------


def _keys(*keys):
    from io import StringIO

    script = iter(keys)
    return {
        "key_source": lambda: next(script),
        "output": StringIO(),
        "size": lambda: (100, 24),
    }


class TestSavedCredentialNames:
    def test_only_names_with_values(self, monkeypatch):
        monkeypatch.setattr(
            vllm, "credential_env_var_names", lambda: {"B_API_KEY", "A_API_KEY", "ZZ"}
        )
        monkeypatch.setattr(vllm, "is_credential_set", lambda n: n != "ZZ")
        assert vllm.saved_credential_names() == ["A_API_KEY", "B_API_KEY"]


class TestChooseApiKey:
    def test_none_returns_placeholder(self):
        ref = vllm.choose_vllm_api_key(
            saved=[], menu_factory=lambda saved: _FakeMenu(vllm._KEY_NONE)
        )
        assert ref == "EMPTY"

    def test_saved_key_returns_env_ref(self):
        ref = vllm.choose_vllm_api_key(
            saved=["OPENAI_API_KEY"],
            menu_factory=lambda saved: _FakeMenu("OPENAI_API_KEY"),
        )
        assert ref == "$OPENAI_API_KEY"

    def test_new_key_delegates_to_prompt(self):
        ref = vllm.choose_vllm_api_key(
            saved=[],
            menu_factory=lambda saved: _FakeMenu(vllm._KEY_NEW),
            new_key_prompt=lambda: "MY_VLLM_KEY",
        )
        assert ref == "$MY_VLLM_KEY"

    def test_new_key_cancelled_propagates(self):
        ref = vllm.choose_vllm_api_key(
            saved=[],
            menu_factory=lambda saved: _FakeMenu(vllm._KEY_NEW),
            new_key_prompt=lambda: None,
        )
        assert ref is None

    def test_menu_cancelled(self):
        assert (
            vllm.choose_vllm_api_key(saved=[], menu_factory=lambda s: _FakeMenu(None))
            is None
        )

    def test_menu_lists_saved_keys_after_sentinels(self, monkeypatch):
        monkeypatch.setattr(vllm, "credential_display", lambda n: "set (…abcd)")
        menu = vllm.build_vllm_api_key_menu(
            ["GROQ_API_KEY"], **_keys("down", "down", "enter")
        )
        assert menu.run().item.value == "GROQ_API_KEY"


class TestNewKeyPrompt:
    @pytest.fixture(autouse=True)
    def isolated_credentials(self, monkeypatch):
        monkeypatch.setattr(vllm, "credential_env_var_names", lambda: set())
        monkeypatch.setattr(vllm, "is_credential_set", lambda name: False)

    def test_default_env_name(self):
        with patch.object(vllm, "save_credential") as mock_save:
            env = vllm.prompt_for_new_vllm_api_key(**_keys("s", "k", "enter"))
        assert env == "VLLM_API_KEY0"
        mock_save.assert_called_once_with("VLLM_API_KEY0", "sk")

    def test_skips_existing_references_and_orphaned_keys(self, monkeypatch):
        monkeypatch.setattr(vllm, "credential_env_var_names", lambda: {"VLLM_API_KEY0"})
        monkeypatch.setattr(
            vllm, "is_credential_set", lambda name: name == "VLLM_API_KEY1"
        )
        with patch.object(vllm, "save_credential") as mock_save:
            env = vllm.prompt_for_new_vllm_api_key(**_keys("s", "k", "enter"))
        assert env == "VLLM_API_KEY2"
        mock_save.assert_called_once_with("VLLM_API_KEY2", "sk")

    def test_empty_key_cancels(self):
        with patch.object(vllm, "save_credential") as mock_save:
            assert vllm.prompt_for_new_vllm_api_key(**_keys("enter")) is None
        mock_save.assert_not_called()

    def test_escape_on_key_cancels(self):
        with patch.object(vllm, "save_credential") as mock_save:
            assert vllm.prompt_for_new_vllm_api_key(**_keys("escape")) is None
        mock_save.assert_not_called()


# -- wiring into the provider browser -----------------------------------------


class _Registry:
    def get_providers(self):
        from code_puppy.models_dev_parser import ProviderInfo

        return [ProviderInfo(id="acme", name="Acme", env=[], api="https://x/v1")]

    def get_models(self, provider_id):
        return []


class TestSentinelWiring:
    def test_vllm_entry_is_searchable_in_provider_menu(self):
        from io import StringIO

        menu = amm.build_provider_menu(
            _Registry().get_providers(),
            key_source=iter(["v", "l", "enter"]).__next__,
            output=StringIO(),
            size=lambda: (110, 30),
        )
        assert menu.run().item.value == amm._VLLM_PROVIDER_VALUE

    def test_flow_routes_sentinel_to_vllm(self):
        with patch.object(vllm, "run_vllm_flow", return_value=True) as mock_flow:
            added = amm.run_add_model_flow(
                registry=_Registry(),
                provider_menu_factory=lambda providers, **kw: _FakeMenu(
                    amm._VLLM_PROVIDER_VALUE
                ),
            )
        assert added is True
        mock_flow.assert_called_once_with()
