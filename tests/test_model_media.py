"""Tests for code_puppy.model_media.supported_binary_media_types.

The registry and catalog are synthetic (no network, no user config). One test
resolves against the bundled models.dev snapshot to prove the real key shape.
"""

import pytest

from code_puppy import model_media
from code_puppy.model_factory import ModelFactory
from code_puppy.models_dev_parser import (
    ModelInfo,
    ModelsDevRegistry,
    bundled_json_path,
    extra_model_key,
)

PDF = ["application/pdf"]


class _FakeRegistry:
    def __init__(self, models):
        self._models = models
        self.get_models_calls = 0

    def get_models(self):
        self.get_models_calls += 1
        return list(self._models)


class _RaisingRegistry:
    def get_models(self):
        raise RuntimeError("boom")


def _model(provider, model_id, input_modalities):
    return ModelInfo(
        provider_id=provider,
        model_id=model_id,
        name=model_id,
        input_modalities=input_modalities,
    )


@pytest.fixture(autouse=True)
def logged(monkeypatch):
    """Capture log_error calls so tests never write the real errors.log."""
    calls = []
    monkeypatch.setattr(
        model_media, "log_error", lambda exc, context=None: calls.append((exc, context))
    )
    return calls


@pytest.fixture
def use(monkeypatch):
    """Install a fake registry and catalog; returns a setter for both."""

    def _install(registry=None, catalog=None):
        monkeypatch.setattr(model_media, "get_registry", lambda: registry)
        monkeypatch.setattr(ModelFactory, "load_config", lambda: catalog or {})
        return registry

    return _install


@pytest.fixture
def registry():
    return _FakeRegistry(
        [
            _model("google", "gemini-pdf", ["text", "image", "pdf"]),
            _model("openai", "gpt-text", ["text", "image"]),
            _model("azure", "shared-a", ["text", "pdf"]),
            _model("vertex", "shared-a", ["text", "pdf"]),
            _model("azure", "split", ["text", "pdf"]),
            _model("vertex", "split", ["text"]),
        ]
    )


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("google-gemini-pdf", PDF),
        ("google/gemini-pdf", PDF),
        ("openai-gpt-text", []),
    ],
)
def test_exact_key_uses_registry_modalities(use, registry, model_name, expected):
    use(registry=registry, catalog={})
    assert model_media.supported_binary_media_types(model_name) == expected


def test_unknown_key_without_catalog_entry_is_unknown(use, registry):
    use(registry=registry, catalog={})
    assert model_media.supported_binary_media_types("nope-nothing") == []


def test_catalog_alias_resolves_through_bare_name(use, registry):
    use(registry=registry, catalog={"my-alias": {"name": "gemini-pdf"}})
    assert model_media.supported_binary_media_types("my-alias") == PDF


@pytest.mark.parametrize(
    ("catalog_name", "expected"),
    [
        ("shared-a", PDF),  # two providers, both pdf
        ("split", []),  # two providers disagree
        ("gpt-text", []),  # single non-pdf provider
        ("missing", []),  # no registry model with that id
    ],
)
def test_bare_name_match_requires_provider_agreement(
    use, registry, catalog_name, expected
):
    use(registry=registry, catalog={"alias": {"name": catalog_name}})
    assert model_media.supported_binary_media_types("alias") == expected


@pytest.mark.parametrize("model_name", [None, ""])
def test_none_or_empty_name_is_unknown(use, registry, model_name):
    use(registry=registry, catalog={})
    assert model_media.supported_binary_media_types(model_name) == []


def test_missing_registry_is_unknown(use):
    use(registry=None, catalog={"alias": {"name": "gemini-pdf"}})
    assert model_media.supported_binary_media_types("alias") == []


def test_registry_failure_is_unknown(use):
    use(registry=_RaisingRegistry(), catalog={})
    assert model_media.supported_binary_media_types("google-gemini-pdf") == []


def test_catalog_failure_does_not_block_exact_match(monkeypatch, registry):
    monkeypatch.setattr(model_media, "get_registry", lambda: registry)

    def _broken_catalog():
        raise OSError("unreadable")

    monkeypatch.setattr(ModelFactory, "load_config", _broken_catalog)
    assert model_media.supported_binary_media_types("google-gemini-pdf") == PDF
    assert model_media.supported_binary_media_types("alias") == []


def test_returned_list_is_a_fresh_copy(use, registry):
    use(registry=registry, catalog={})
    first = model_media.supported_binary_media_types("google-gemini-pdf")
    first.append("image/png")
    assert model_media.supported_binary_media_types("google-gemini-pdf") == PDF


def test_index_is_built_once_per_registry_object(monkeypatch, registry):
    current = {"registry": registry}
    monkeypatch.setattr(model_media, "get_registry", lambda: current["registry"])
    monkeypatch.setattr(ModelFactory, "load_config", lambda: {})

    model_media.supported_binary_media_types("google-gemini-pdf")
    model_media.supported_binary_media_types("openai-gpt-text")
    assert registry.get_models_calls == 1

    replacement = _FakeRegistry([_model("google", "gemini-pdf", ["text"])])
    current["registry"] = replacement
    assert model_media.supported_binary_media_types("google-gemini-pdf") == []
    assert replacement.get_models_calls == 1


@pytest.mark.parametrize(
    ("provider", "model_id", "expected"),
    [
        ("vercel", "google/gemini-2.5-flash-lite", PDF),
        ("moonshotai-cn", "kimi-k2-thinking", []),
    ],
)
def test_bundled_snapshot_lookup_by_extra_model_key(
    monkeypatch, provider, model_id, expected
):
    snapshot = ModelsDevRegistry(json_path=bundled_json_path())
    monkeypatch.setattr(model_media, "get_registry", lambda: snapshot)
    monkeypatch.setattr(ModelFactory, "load_config", lambda: {})
    key = extra_model_key(provider, model_id)
    assert model_media.supported_binary_media_types(key) == expected


_LOOKUP_CTX = "model_media::supported_binary_media_types: lookup failed"
_CATALOG_CTX = "model_media::_catalog_entry: catalog load failed"


def _fail_at(monkeypatch, registry, site, exc):
    """Make ``site`` raise ``exc``; "catalog" needs a name only the catalog resolves."""

    def _raise(*_args):
        raise exc

    if site == "registry":
        monkeypatch.setattr(model_media, "get_registry", _raise)
    else:
        monkeypatch.setattr(model_media, "get_registry", lambda: registry)
        monkeypatch.setattr(ModelFactory, "load_config", _raise)


_SITES = [("registry", _LOOKUP_CTX), ("catalog", _CATALOG_CTX)]


@pytest.mark.parametrize(("site", "context"), _SITES)
def test_unexpected_failure_is_logged_once_with_static_context(
    monkeypatch, registry, logged, site, context
):
    error = RuntimeError("boom for /private/path")
    _fail_at(monkeypatch, registry, site, error)

    assert model_media.supported_binary_media_types("alias-model") == []
    assert logged == [(error, context)]


@pytest.mark.parametrize("site", ["registry", "catalog"])
def test_failing_logger_does_not_change_result(monkeypatch, registry, site):
    def _bad_logger(*_args, **_kwargs):
        raise OSError("disk full")

    _fail_at(monkeypatch, registry, site, RuntimeError("boom"))
    monkeypatch.setattr(model_media, "log_error", _bad_logger)
    assert model_media.supported_binary_media_types("alias-model") == []


@pytest.mark.parametrize("site", ["registry", "catalog"])
def test_control_flow_exceptions_propagate_unlogged(
    monkeypatch, registry, logged, site
):
    _fail_at(monkeypatch, registry, site, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        model_media.supported_binary_media_types("alias-model")
    assert logged == []


@pytest.mark.parametrize(
    ("registry_arg", "catalog", "model_name"),
    [
        ("registry", {}, "nope-nothing"),  # unknown
        ("registry", {"alias": {"name": "split"}}, "alias"),  # ambiguous
        (None, {"alias": {"name": "gemini-pdf"}}, "alias"),  # no registry
        ("registry", {}, None),  # empty name
    ],
)
def test_ordinary_unknown_models_are_not_errors(
    use, registry, logged, registry_arg, catalog, model_name
):
    use(registry=registry if registry_arg else None, catalog=catalog)
    assert model_media.supported_binary_media_types(model_name) == []
    assert logged == []
