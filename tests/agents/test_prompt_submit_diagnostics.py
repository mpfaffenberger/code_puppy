"""Prompt-dispatch failures remain observable, secret-free, and fail-open."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from code_puppy import callbacks, error_logging
from code_puppy.agents import _runtime
from tests.agents.test_agent_exception_recovery import (
    DummyAgent,
    DummyResult,
    ScriptedPydanticAgent,
    isolated_runtime_callbacks,  # noqa: F401
)


@pytest.mark.parametrize("raising_dispatch", [False, True])
@pytest.mark.parametrize("failing_logger", [False, True])
async def test_dispatch_failure_logs_once_safely_and_runs(
    monkeypatch, raising_dispatch, failing_logger
):
    secret = "synthetic-private-prompt-and-exception"
    entries = []
    observed = []
    original_log_error = error_logging.log_error

    async def broken_dispatch(*_):
        if raising_dispatch:
            raise RuntimeError(secret)

    def record(error, **kwargs):
        original_log_error(error, **kwargs)
        if failing_logger:
            raise OSError("synthetic unavailable logger")

    monkeypatch.setattr(_runtime, "on_user_prompt_submit", broken_dispatch)
    monkeypatch.setattr(error_logging, "_append_entry", entries.append)
    monkeypatch.setattr(error_logging, "log_error", record)
    callbacks.register_callback(
        "error_logged", lambda error, **kwargs: observed.append((error, kwargs))
    )
    provider = ScriptedPydanticAgent(DummyResult("ok"))

    result = await _runtime.run_with_mcp(DummyAgent(provider), secret)

    assert result.data == "ok"
    assert provider.calls[0]["prompt"] == secret
    assert len(entries) == len(observed) == 1
    assert "prompt-submit dispatch failed" in entries[0]
    assert secret not in entries[0]
    assert "Traceback" not in entries[0]
    error, metadata = observed[0]
    assert str(error) == "prompt-submit dispatch failed"
    assert metadata == {
        "context": "_runtime::apply_user_prompt_submit",
        "include_traceback": False,
    }


async def test_dispatch_failure_never_logs_plugin_controlled_exception_name(
    monkeypatch, tmp_path
):
    private_name = "synthetic_private_prompt_in_exception_name"
    private_message = "synthetic_private_exception_message"
    failure = type(private_name, (Exception,), {})(private_message)
    log_file = tmp_path / "errors.log"
    observed = []
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))
    monkeypatch.setattr(
        _runtime, "on_user_prompt_submit", AsyncMock(side_effect=failure)
    )
    callbacks.register_callback(
        "error_logged", lambda error, **kwargs: observed.append((error, kwargs))
    )

    result = await _runtime.apply_user_prompt_submit("synthetic user task", "session")

    assert result == "synthetic user task"
    entry = log_file.read_text(encoding="utf-8")
    assert entry.count("Context: _runtime::apply_user_prompt_submit") == 1
    assert private_name not in entry
    assert private_message not in entry
    assert "synthetic user task" not in entry
    assert "Traceback" not in entry
    assert len(observed) == 1
    error, metadata = observed[0]
    assert type(error) is RuntimeError
    assert str(error) == "prompt-submit dispatch failed"
    assert metadata == {
        "context": "_runtime::apply_user_prompt_submit",
        "include_traceback": False,
    }


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt])
async def test_prompt_dispatch_control_flow_propagates_without_logging(
    monkeypatch, failure_type
):
    failure = failure_type("synthetic control flow")
    record = AsyncMock()
    monkeypatch.setattr(
        _runtime, "on_user_prompt_submit", AsyncMock(side_effect=failure)
    )
    monkeypatch.setattr(error_logging, "log_error", record)

    with pytest.raises(failure_type) as raised:
        await _runtime.apply_user_prompt_submit("prompt", "session")

    assert raised.value is failure
    record.assert_not_called()
