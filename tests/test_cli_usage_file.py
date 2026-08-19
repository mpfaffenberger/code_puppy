"""Tests for machine-readable headless usage output."""

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.cli_runner import _write_usage_file, execute_single_prompt


def test_write_usage_file_creates_parent_and_serializes_fields(tmp_path):
    target = tmp_path / "nested" / "usage.json"
    usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=34,
        cache_read_tokens=56,
        cache_write_tokens=7,
        requests=3,
        tool_calls=9,
        cost=Decimal("0.0125"),
    )

    _write_usage_file(target, usage)

    assert json.loads(target.read_text()) == {
        "input_tokens": 120,
        "output_tokens": 34,
        "cache_read_tokens": 56,
        "cache_write_tokens": 7,
        "requests": 3,
        "tool_calls": 9,
        "cost_usd": 0.0125,
    }
    assert list(target.parent.glob("*.tmp")) == []


@pytest.mark.anyio
async def test_execute_single_prompt_writes_result_usage(tmp_path):
    target = tmp_path / "usage.json"
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=4,
        cache_read_tokens=3,
        cache_write_tokens=2,
        requests=1,
        tool_calls=2,
        cost=None,
    )
    result = MagicMock(output="done")
    result.usage = usage
    result.all_messages.return_value = []
    agent = MagicMock()
    renderer = MagicMock()

    with (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="do it"),
        ),
        patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
        patch(
            "code_puppy.cli_runner.run_prompt_with_attachments",
            new=AsyncMock(return_value=(result, MagicMock())),
        ),
        patch("code_puppy.messaging.get_message_bus"),
        patch("code_puppy.session_lifecycle.persist_named_session"),
        patch("code_puppy.config.record_quick_resume_sessions"),
    ):
        await execute_single_prompt("do it", renderer, usage_file=target)

    assert json.loads(target.read_text())["input_tokens"] == 10


def test_write_usage_file_allows_unknown_cost(tmp_path):
    target = tmp_path / "usage.json"

    _write_usage_file(target, SimpleNamespace())

    assert json.loads(target.read_text()) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "requests": 0,
        "tool_calls": 0,
        "cost_usd": None,
    }
