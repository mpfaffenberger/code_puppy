"""Regression coverage for llama.cpp's in-band multimodal decode errors."""

from unittest.mock import patch

import httpx
import openai
import pytest

from code_puppy.agents._diagnostics import emit_exception_diagnostics
from code_puppy.agents._multimodal_error_hint import multimodal_error_hint
from code_puppy.agents._runtime import should_retry_streaming
from code_puppy.i18n import get_locale, load_catalog, set_locale

MESSAGE = "failed to process mtmd chunk"


def api_error(message=MESSAGE, *, body=None):
    return openai.APIError(
        message,
        request=httpx.Request("POST", "http://localhost:8082/v1/chat/completions"),
        body=body,
    )


@pytest.mark.parametrize("message", [MESSAGE, MESSAGE.upper()])
def test_bare_sse_error_has_actionable_hint(message):
    hint = multimodal_error_hint(api_error(message))
    assert "model server" in hint
    assert "llama-server logs" in hint
    assert "projector" in hint
    assert "DFlash" in hint
    assert "does not remove images" in hint


@pytest.mark.parametrize("locale", ["es", "fr-CA"])
def test_hint_uses_translated_catalog_without_english_fallback(locale):
    key = "agent.error.multimodal_processing_hint"
    previous_locale = get_locale()
    try:
        set_locale(locale)
        hint = multimodal_error_hint(api_error())
        assert hint == load_catalog(locale)[key]
        assert hint != load_catalog("en-US")[key]
        for literal in (
            "mtmd",
            "llama-server",
            "DFlash",
            "~/.code_puppy/logs/errors.log",
        ):
            assert literal in hint
    finally:
        set_locale(previous_locale)


def test_nested_provider_body():
    error = api_error("provider failure", body={"error": {"message": MESSAGE}})
    assert multimodal_error_hint(error)


@pytest.mark.parametrize("attribute", ["__cause__", "__context__"])
def test_wrapper_chain(attribute):
    wrapper = RuntimeError("model request failed")
    setattr(wrapper, attribute, api_error())
    assert multimodal_error_hint(wrapper)


def test_nested_exception_group():
    error = ExceptionGroup(
        "task group", [ValueError("other"), ExceptionGroup("inner", [api_error()])]
    )
    assert multimodal_error_hint(error)


def test_cycles_and_unrelated_errors_do_not_match():
    error = RuntimeError("unrelated")
    error.__cause__ = error
    assert multimodal_error_hint(error) is None
    body = {}
    body["error"] = body
    assert multimodal_error_hint(api_error("unrelated", body=body)) is None


def test_deep_chain_is_bounded():
    error = api_error()
    for _ in range(100):
        wrapper = RuntimeError("wrapper")
        wrapper.__cause__ = error
        error = wrapper
    assert multimodal_error_hint(error) is None


def test_hostile_exception_does_not_break_diagnostics():
    class HostileError(Exception):
        def __str__(self):
            raise ValueError("broken string")

        @property
        def body(self):
            raise ValueError("broken property")

    assert multimodal_error_hint(HostileError()) is None


def test_signature_is_not_a_transient_transport_error():
    # A bare SSE APIError has no HTTP 500 status: replaying it unchanged is
    # not a recovery strategy. Preserve the existing retry classification.
    assert not should_retry_streaming(api_error())
    assert multimodal_error_hint(ValueError("image is too large")) is None


def test_diagnostics_emit_one_hint_and_preserve_error():
    error = api_error(body={"message": MESSAGE, "private": "do not display"})
    original_body = error.body.copy()
    with (
        patch("code_puppy.agents._diagnostics.emit_info"),
        patch("code_puppy.agents._diagnostics.emit_warning") as warn,
        patch("code_puppy.agents._diagnostics.log_error") as log,
    ):
        emit_exception_diagnostics(error, group_id="test")
    warn.assert_called_once()
    assert "do not display" not in str(warn.call_args)
    log.assert_called_once_with(
        error, context="Agent run (group_id=test)", include_traceback=True
    )
    assert error.body == original_body


def test_failed_hint_output_still_logs_traceback():
    error = api_error()
    with (
        patch("code_puppy.agents._diagnostics.emit_info"),
        patch("code_puppy.agents._diagnostics.emit_warning", side_effect=OSError),
        patch("code_puppy.agents._diagnostics.log_error") as log,
    ):
        emit_exception_diagnostics(error, group_id="test")
    log.assert_called_once()
