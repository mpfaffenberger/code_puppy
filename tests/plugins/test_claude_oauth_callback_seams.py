"""Regression tests for the decoupled Claude Code OAuth callback seams."""

from __future__ import annotations

import asyncio
import gc
import json
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import httpx2
import pytest

from code_puppy import callbacks
from code_puppy.claude_cache_client import ClaudeCacheAsyncClient
from code_puppy.model_factory import ModelFactory

PLUGIN_NAME = "claude_code_oauth"


@pytest.fixture
def isolate_callback_phases() -> Iterator[Callable[[str], None]]:
    """Clear requested phases and restore callbacks plus ownership afterward."""
    saved: dict[str, list[tuple[Callable, str | None]]] = {}

    def isolate(phase: str) -> None:
        if phase in saved:
            return
        saved[phase] = [
            (callback, callbacks.get_callback_owner(callback))
            for callback in callbacks.get_callbacks(phase, include_disabled=True)
        ]
        callbacks.clear_callbacks(phase)

    yield isolate

    callbacks.clear_loading_context()
    for phase, registered in saved.items():
        callbacks.clear_callbacks(phase)
        for callback, owner in registered:
            if owner:
                callbacks.set_loading_context(owner)
            callbacks.register_callback(phase, callback)
            callbacks.clear_loading_context()


@pytest.fixture
def install_provider(isolate_callback_phases, monkeypatch):
    """Install one owned provider and optionally disable its plugin owner."""

    def install(phase: str, provider: Callable, *, disabled: bool = False) -> None:
        isolate_callback_phases(phase)
        callbacks.set_loading_context(PLUGIN_NAME)
        try:
            callbacks.register_callback(phase, provider)
        finally:
            callbacks.clear_loading_context()
        monkeypatch.setattr(
            callbacks,
            "_get_disabled_plugins",
            lambda: {PLUGIN_NAME} if disabled else set(),
        )

    return install


def _raising_provider() -> None:
    raise RuntimeError("provider exploded")


@pytest.mark.parametrize("result", [False, True])
def test_auth_hook_returns_real_success_boolean(result, monkeypatch):
    from code_puppy_core_plugins.claude_code_oauth import register_callbacks

    authenticate = MagicMock(return_value=result)
    monkeypatch.setattr(register_callbacks, "_perform_authentication", authenticate)

    assert register_callbacks._hook_authenticate() is result
    authenticate.assert_called_once_with()


@pytest.mark.parametrize(
    ("phase", "dispatcher", "expected"),
    [
        (
            "check_claude_oauth_token_expiry",
            callbacks.on_check_claude_oauth_token_expiry,
            True,
        ),
        (
            "refresh_claude_oauth_token",
            callbacks.on_refresh_claude_oauth_token,
            "access-token",
        ),
        (
            "load_claude_oauth_models",
            callbacks.on_load_claude_oauth_models,
            {"claude": {"type": "claude_code"}},
        ),
        (
            "claude_oauth_authenticate",
            callbacks.on_claude_oauth_authenticate,
            True,
        ),
    ],
)
@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
def test_dispatchers_support_sync_and_async_providers(
    phase, dispatcher, expected, is_async, install_provider
):
    if is_async:

        async def provider():
            return expected

    else:

        def provider():
            return expected

    install_provider(phase, provider)

    assert dispatcher() == [expected]


@pytest.mark.parametrize(
    "phase",
    [
        "check_claude_oauth_token_expiry",
        "refresh_claude_oauth_token",
        "load_claude_oauth_models",
        "claude_oauth_authenticate",
    ],
)
def test_callback_registration_is_idempotent(phase, isolate_callback_phases):
    isolate_callback_phases(phase)

    def provider():
        return None

    callbacks.register_callback(phase, provider)
    callbacks.register_callback(phase, provider)

    assert callbacks.get_callbacks(phase, include_disabled=True) == [provider]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("absent", False),
        ("exception", False),
        ("disabled", False),
        ("valid", True),
    ],
)
def test_token_expiry_seam(case, expected, install_provider, isolate_callback_phases):
    phase = "check_claude_oauth_token_expiry"
    isolate_callback_phases(phase)
    if case == "exception":
        install_provider(phase, _raising_provider)
    elif case == "disabled":
        install_provider(phase, lambda: True, disabled=True)
    elif case == "valid":
        install_provider(phase, lambda: True)

    assert ClaudeCacheAsyncClient._check_stored_token_expiry() is expected


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("absent", None),
        ("exception", None),
        ("disabled", None),
        ("valid", "new-token"),
    ],
)
def test_token_refresh_seam(case, expected, install_provider, isolate_callback_phases):
    phase = "refresh_claude_oauth_token"
    isolate_callback_phases(phase)
    if case == "exception":
        install_provider(phase, _raising_provider)
    elif case == "disabled":
        install_provider(phase, lambda: "new-token", disabled=True)
    elif case == "valid":
        install_provider(phase, lambda: "new-token")

    client = ClaudeCacheAsyncClient(headers={"Authorization": "Bearer old-token"})
    try:
        assert client._refresh_claude_oauth_token() == expected
        if expected:
            assert client.headers["Authorization"] == f"Bearer {expected}"
    finally:
        asyncio.run(client.aclose())


@contextmanager
def _claude_models_config(monkeypatch, tmp_path):
    import code_puppy.config as config
    import code_puppy.model_factory as model_factory

    claude_file = tmp_path / "claude_models.json"
    fallback = {"fallback-model": {"type": "claude_code", "name": "fallback"}}
    claude_file.write_text(json.dumps(fallback), encoding="utf-8")
    missing = tmp_path / "missing.json"

    monkeypatch.setattr(model_factory, "EXTRA_MODELS_FILE", str(missing))
    monkeypatch.setattr(config, "CHATGPT_MODELS_FILE", str(missing))
    monkeypatch.setattr(config, "CLAUDE_MODELS_FILE", str(claude_file))
    monkeypatch.setattr(config, "GEMINI_MODELS_FILE", str(missing))
    monkeypatch.setattr(config, "COPILOT_MODELS_FILE", str(missing))
    yield fallback


@pytest.mark.parametrize(
    ("case", "expected_model"),
    [
        ("absent", "fallback-model"),
        ("exception", "fallback-model"),
        ("disabled", "fallback-model"),
        ("valid", "provider-model"),
    ],
)
def test_filtered_model_loading_seam(
    case,
    expected_model,
    install_provider,
    isolate_callback_phases,
    monkeypatch,
    tmp_path,
):
    for phase in (
        "load_model_config",
        "load_models_config",
        "load_model_descriptions",
        "load_claude_oauth_models",
    ):
        isolate_callback_phases(phase)

    phase = "load_claude_oauth_models"
    provider_models = {"provider-model": {"type": "claude_code", "name": "provider"}}
    if case == "exception":
        install_provider(phase, _raising_provider)
    elif case == "disabled":
        install_provider(phase, lambda: provider_models, disabled=True)
    elif case == "valid":
        install_provider(phase, lambda: provider_models)

    with _claude_models_config(monkeypatch, tmp_path):
        loaded = ModelFactory.load_config()

    assert expected_model in loaded
    assert ("fallback-model" in loaded) is (case != "valid")


@pytest.mark.parametrize(
    ("case", "should_switch"),
    [
        ("absent", False),
        ("exception", False),
        ("disabled", False),
        ("valid", True),
    ],
)
def test_tutorial_authentication_seam(
    case,
    should_switch,
    install_provider,
    isolate_callback_phases,
    monkeypatch,
):
    import concurrent.futures

    from code_puppy.command_line import onboarding_wizard
    from code_puppy.command_line.core_commands import handle_tutorial_command
    from code_puppy import model_switching

    phase = "claude_oauth_authenticate"
    isolate_callback_phases(phase)
    if case == "exception":
        install_provider(phase, _raising_provider)
    elif case == "disabled":
        install_provider(phase, lambda: True, disabled=True)
    elif case == "valid":
        install_provider(phase, lambda: True)

    executor = MagicMock()
    executor.return_value.__enter__.return_value.submit.return_value.result.return_value = "claude"
    switch_model = MagicMock()
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", executor)
    monkeypatch.setattr(onboarding_wizard, "reset_onboarding", MagicMock())
    monkeypatch.setattr(onboarding_wizard, "require_model_setup_if_needed", MagicMock())
    monkeypatch.setattr(model_switching, "set_model_and_reload_agent", switch_model)

    assert handle_tutorial_command("/tutorial") is True
    assert switch_model.called is should_switch


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expiry_raises", "expected_token"),
    [(False, "new-token"), (True, "old-token")],
    ids=["async-provider-result", "async-provider-exception-fallback"],
)
async def test_real_send_awaits_async_oauth_providers_without_runtime_warning(
    expiry_raises,
    expected_token,
    install_provider,
    isolate_callback_phases,
    monkeypatch,
):
    expiry_phase = "check_claude_oauth_token_expiry"
    refresh_phase = "refresh_claude_oauth_token"
    isolate_callback_phases(expiry_phase)
    isolate_callback_phases(refresh_phase)

    async def expiry_provider():
        if expiry_raises:
            raise RuntimeError("expiry provider exploded")
        return True

    async def refresh_provider():
        return "new-token"

    install_provider(expiry_phase, expiry_provider)
    install_provider(refresh_phase, refresh_provider)

    captured = {}

    async def fake_send(self, request, *args, **kwargs):
        captured["authorization"] = request.headers.get("Authorization")
        return httpx2.Response(200, request=request, json={})

    # ClaudeCacheAsyncClient rides httpx2 (the anthropic>=1 SDK's client).
    monkeypatch.setattr(httpx2.AsyncClient, "send", fake_send)
    client = ClaudeCacheAsyncClient(headers={"Authorization": "Bearer old-token"})
    request = httpx2.Request(
        "GET",
        "https://api.anthropic.com/health",
        headers={"Authorization": "Bearer old-token"},
    )

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            response = await client.send(request)
            gc.collect()
            await asyncio.sleep(0)
    finally:
        await client.aclose()

    assert response.status_code == 200
    assert captured["authorization"] == f"Bearer {expected_token}"
    assert not [warning for warning in caught if warning.category is RuntimeWarning]


@pytest.mark.asyncio
async def test_sync_dispatcher_closes_async_provider_inside_running_loop(
    install_provider,
):
    phase = "refresh_claude_oauth_token"

    async def provider():
        return "unused-token"

    install_provider(phase, provider)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert callbacks.on_refresh_claude_oauth_token() == [None]
        gc.collect()
        await asyncio.sleep(0)

    assert not [warning for warning in caught if warning.category is RuntimeWarning]
