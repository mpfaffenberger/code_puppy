"""Tests for the ``resolve_custom_endpoint_url`` hook.

Lets a plugin redirect a custom model endpoint URL (e.g. through a local
compression/caching proxy) right before a client is built. Mirrors the
test style of test_model_select_hook.py.
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
    register_callback("resolve_custom_endpoint_url", lambda url: None)
    register_callback("resolve_custom_endpoint_url", lambda url: None)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_last_non_none_result_wins():
    register_callback("resolve_custom_endpoint_url", lambda url: None)
    register_callback(
        "resolve_custom_endpoint_url", lambda url: "http://127.0.0.1:8787/v1"
    )
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://127.0.0.1:8787/v1"
    )


def test_earlier_non_none_survives_later_none():
    # "Last non-None wins" means a later None does NOT erase an earlier
    # non-None winner -- only a later non-None result can replace it.
    register_callback(
        "resolve_custom_endpoint_url", lambda url: "http://first-proxy:1"
    )
    register_callback("resolve_custom_endpoint_url", lambda url: None)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://first-proxy:1"
    )


def test_later_non_none_overrides_earlier_non_none():
    # The discriminating case: with two real (non-None) results, "last wins"
    # and "first wins" disagree. This is the case that actually pins the
    # reverse-iteration behavior against a regression to first-wins.
    register_callback("resolve_custom_endpoint_url", lambda url: "http://first:1")
    register_callback("resolve_custom_endpoint_url", lambda url: "http://second:2")
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "http://second:2"
    )


def test_non_string_or_blank_results_are_treated_as_defer():
    # Mirrors on_model_select's guard: a plugin returning "", False, or a
    # non-string must not silently become the new URL.
    register_callback("resolve_custom_endpoint_url", lambda url: "")
    register_callback("resolve_custom_endpoint_url", lambda url: False)
    assert (
        on_resolve_custom_endpoint_url("https://example.com/v1")
        == "https://example.com/v1"
    )


def test_callback_receives_the_original_url():
    seen = {}

    def cb(url):
        seen["url"] = url
        return None

    register_callback("resolve_custom_endpoint_url", cb)
    on_resolve_custom_endpoint_url("https://api.z.ai/api/coding/paas/v4")
    assert seen["url"] == "https://api.z.ai/api/coding/paas/v4"
