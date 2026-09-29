"""Regression tests for the legacy httpx -> httpx2 provider migration.

Guards issue #876: pydantic-ai warns that caller-owned legacy ``httpx.AsyncClient``
support on OpenAI-compatible providers is removed in v3. These tests pin three things:

1. the provider-bound clients are ``httpx2``,
2. building those models raises no ``PydanticAIDeprecationWarning``,
3. the legacy ``httpx`` clients that MCP / Gemini still require keep working unchanged.
"""

import warnings
from unittest.mock import AsyncMock, patch

import httpx
import httpx2
import pytest
from pydantic_ai.exceptions import PydanticAIDeprecationWarning

import code_puppy.http_utils as http_utils
import code_puppy.httpx2_utils as httpx2_utils
from code_puppy.http_retry import RetryingSendMixin
from code_puppy.model_factory import ModelFactory

CUSTOM_ENDPOINT = {
    "url": "https://fake.url/v1",
    "headers": {"X-Api-Key": "$TEST_PROVIDER_KEY"},
    "ca_certs_path": False,
    "api_key": "$TEST_PROVIDER_KEY",
}


@pytest.fixture(autouse=True)
def _provider_key(monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_KEY", "ok")


def _deprecations(caught):
    return [w for w in caught if issubclass(w.category, PydanticAIDeprecationWarning)]


class TestHttpx2ClientFactory:
    def test_factory_returns_httpx2_retrying_client(self):
        client = httpx2_utils.create_async_client(timeout=60)
        try:
            assert isinstance(client, httpx2.AsyncClient)
            assert isinstance(client, httpx2_utils.RetryingAsyncClient)
            # Must NOT be a legacy client, or pydantic-ai warns again.
            assert not isinstance(client, httpx.AsyncClient)
        finally:
            _close_soon(client)

    def test_factory_honours_retry_transport_disable(self, monkeypatch):
        monkeypatch.setenv("CODE_PUPPY_DISABLE_RETRY_TRANSPORT", "true")
        client = httpx2_utils.create_async_client(timeout=60)
        try:
            assert isinstance(client, httpx2.AsyncClient)
            assert not isinstance(client, httpx2_utils.RetryingAsyncClient)
        finally:
            _close_soon(client)

    def test_factory_mirrors_legacy_kwargs(self):
        """Both families must resolve proxy/verify/http2/timeout the same way."""
        legacy = http_utils.create_async_client(timeout=77, headers={"X-A": "1"})
        modern = httpx2_utils.create_async_client(timeout=77, headers={"X-A": "1"})
        try:
            assert legacy.timeout.read == modern.timeout.read == 77
            assert dict(legacy.headers)["x-a"] == dict(modern.headers)["x-a"] == "1"
        finally:
            _close_soon(legacy)
            _close_soon(modern)


class TestRetryMixinShared:
    """The retry algorithm is defined once and reused by both HTTP families."""

    def test_both_retrying_clients_share_the_mixin(self):
        assert issubclass(http_utils.RetryingAsyncClient, RetryingSendMixin)
        assert issubclass(httpx2_utils.RetryingAsyncClient, RetryingSendMixin)

    def test_legacy_client_is_still_legacy_httpx_for_mcp(self):
        """MCP and AsyncAnthropic are typed against legacy httpx - do not migrate them."""
        client = http_utils.create_async_client()
        try:
            assert isinstance(client, httpx.AsyncClient)
            assert not isinstance(client, httpx2.AsyncClient)
        finally:
            _close_soon(client)

    @pytest.mark.parametrize(
        "family,client_cls",
        [
            (httpx, http_utils.RetryingAsyncClient),
            (httpx2, httpx2_utils.RetryingAsyncClient),
        ],
        ids=["httpx", "httpx2"],
    )
    async def test_retry_after_429_shared_by_both_families(self, family, client_cls):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            status = 429 if calls["n"] == 1 else 200
            return family.Response(status, request=request)

        # Request/transport classes are family-specific, the retry logic is not.
        client = client_cls(transport=family.MockTransport(handler), max_retries=2)
        with patch("code_puppy.http_retry.asyncio.sleep", new_callable=AsyncMock):
            response = await client.send(family.Request("GET", "https://fake.url/x"))
        await client.aclose()

        assert response.status_code == 200
        assert calls["n"] == 2


class TestProvidersEmitNoDeprecation:
    """The real bug: building a model must not raise pydantic-ai's v3 warning."""

    @pytest.mark.parametrize(
        ("model_type", "extra"),
        [
            ("custom_openai", {}),
            ("custom_openai", {"use_responses_api": True}),
            ("cerebras", {}),
        ],
        ids=["custom_openai", "custom_openai_responses", "cerebras"],
    )
    def test_get_model_raises_no_deprecation_warning(self, model_type, extra):
        config = {
            "custom": {
                "type": model_type,
                "name": "whatever",
                "custom_endpoint": CUSTOM_ENDPOINT,
                **extra,
            }
        }

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = ModelFactory.get_model("custom", config)

        assert model is not None
        assert _deprecations(caught) == []

    def test_provider_client_is_httpx2(self):
        config = {
            "custom": {
                "type": "custom_openai",
                "name": "whatever",
                "custom_endpoint": CUSTOM_ENDPOINT,
            }
        }
        model = ModelFactory.get_model("custom", config)
        client = model._provider.client._client
        assert isinstance(client, httpx2.AsyncClient)


def _close_soon(client):
    """Fire-and-close an async client created inside a sync test."""
    import asyncio

    try:
        asyncio.run(client.aclose())
    except RuntimeError:  # pragma: no cover - defensive
        pass
