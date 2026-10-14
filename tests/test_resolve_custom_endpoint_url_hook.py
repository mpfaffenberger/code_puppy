"""Tests for the ``resolve_custom_endpoint_url`` hook.

Lets a plugin redirect a custom model endpoint URL (e.g. through a local
compression/caching proxy) right before a client is built. Mirrors the
test style of test_model_select_hook.py.

Every registered handler below accepts ``**_kwargs`` even when it ignores
them: the hook always calls handlers with ``model_config=...`` as a
keyword argument (see test_handler_receives_model_config_kwarg), so a
handler declared with a bare ``url`` positional-only signature would raise
a TypeError on every call -- caught by the hook's own error isolation, but
silently making the test assert nothing real. ``**_kwargs`` is the
supported way to ignore context you don't need.
"""

from __future__ import annotations

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    on_resolve_custom_endpoint_url,
    register_callback,
)


@pytest.fixture(autouse=True)
def _clean_hook():
    clear_callbacks("resolve_custom_endpoint_url")
    yield
    clear_callbacks("resolve_custom_endpoint_url")


def test_no_callbacks_returns_input_url_unchanged():
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_all_none_results_fall_back_to_input_url():
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: None)
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: None)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_last_non_none_result_wins():
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: None)
    register_callback(
        "resolve_custom_endpoint_url", lambda url, **_kw: "http://127.0.0.1:8787/v1"
    )
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://127.0.0.1:8787/v1"
    )


def test_earlier_non_none_survives_later_none():
    # "Last non-None wins" means a later None does NOT erase an earlier
    # non-None winner -- only a later non-None result can replace it.
    register_callback(
        "resolve_custom_endpoint_url", lambda url, **_kw: "http://first-proxy:1"
    )
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: None)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://first-proxy:1"
    )


def test_later_non_none_overrides_earlier_non_none():
    # The discriminating case: with two real (non-None) results, "last wins"
    # and "first wins" disagree. This is the case that actually pins the
    # last-registered-wins behavior against a regression to first-wins.
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: "http://first:1")
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: "http://second:2")
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://second:2"
    )


def test_conflicting_handlers_log_a_warning(caplog):
    """Two handlers disagreeing on the redirect is exactly the kind of
    silent multi-plugin conflict a user would want surfaced, not swallowed."""
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: "http://first:1")
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: "http://second:2")
    with caplog.at_level("WARNING"):
        on_resolve_custom_endpoint_url("https://example.com/v1")
    assert "disagreed" in caplog.text


def test_non_string_or_blank_results_are_treated_as_defer():
    # Mirrors on_model_select's guard: a plugin returning "", False, or a
    # non-string must not silently become the new URL.
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: "")
    register_callback("resolve_custom_endpoint_url", lambda url, **_kw: False)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_whitespace_padded_result_is_stripped():
    register_callback(
        "resolve_custom_endpoint_url", lambda url, **_kw: "  http://proxy:1  "
    )
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://proxy:1"
    )


def test_non_url_shaped_result_is_rejected_not_forwarded():
    """A handler bug returning garbage must not become a URL httpx later
    fails on confusingly -- it should be treated the same as no handler."""
    register_callback(
        "resolve_custom_endpoint_url", lambda url, **_kw: "not a url at all"
    )
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_raising_handler_falls_back_to_input_url():
    def boom(url, **_kw):
        raise RuntimeError("plugin bug")

    register_callback("resolve_custom_endpoint_url", boom)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_raising_handler_does_not_block_a_later_good_handler():
    def boom(url, **_kw):
        raise RuntimeError("plugin bug")

    register_callback("resolve_custom_endpoint_url", boom)
    register_callback(
        "resolve_custom_endpoint_url", lambda url, **_kw: "http://good-proxy:1"
    )
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://good-proxy:1"
    )


def test_async_handler_in_running_loop_is_ignored_not_awaited():
    """Model builds happen during the async agent run, so a running loop is
    the normal case a real plugin author would hit -- this must not crash,
    and must not silently "work" either (it can't actually await here)."""

    async def async_handler(url, **_kw):
        return "http://should-not-apply:1"

    register_callback("resolve_custom_endpoint_url", async_handler)

    import asyncio

    async def _run():
        return on_resolve_custom_endpoint_url("https://example.com/v1")

    result = asyncio.run(_run())
    assert result == "https://example.com/v1"


def test_callback_receives_the_original_url():
    seen = {}

    def cb(url, **_kw):
        seen["url"] = url
        return None

    register_callback("resolve_custom_endpoint_url", cb)
    on_resolve_custom_endpoint_url("https://api.z.ai/api/coding/paas/v4")
    assert seen["url"] == "https://api.z.ai/api/coding/paas/v4"


def test_handler_receives_model_config_kwarg():
    seen = {}

    def cb(url, *, model_config, **_kw):
        seen["model_config"] = model_config
        return None

    register_callback("resolve_custom_endpoint_url", cb)
    on_resolve_custom_endpoint_url(
        "https://example.com/v1", model_config={"type": "custom_anthropic", "name": "x"}
    )
    assert seen["model_config"] == {"type": "custom_anthropic", "name": "x"}


def test_model_config_defaults_to_empty_dict_when_omitted():
    seen = {}

    def cb(url, *, model_config, **_kw):
        seen["model_config"] = model_config
        return None

    register_callback("resolve_custom_endpoint_url", cb)
    on_resolve_custom_endpoint_url("https://example.com/v1")
    assert seen["model_config"] == {}
