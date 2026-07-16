"""Tests for the fork plugin (/fork, /forks, /fork cancel)."""

from __future__ import annotations

import asyncio
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rich.console import Console, Group
from rich.text import Text

from code_puppy.messaging.messages import MessageLevel
from code_puppy.plugins.fork import register_callbacks as rc

_AGENTS = {"code-puppy": "the default pup", "qa-kitten": "meow"}


@pytest.fixture(autouse=True)
def fresh_forks():
    rc._forks.clear()
    yield
    for record in rc._forks.values():
        if not record.task.done():
            record.task.cancel()
    rc._forks.clear()


@pytest.fixture(autouse=True)
def fake_agent_manager():
    with (
        patch(
            "code_puppy.agents.agent_manager.get_available_agents",
            return_value=dict(_AGENTS),
        ),
        patch(
            "code_puppy.agents.agent_manager.get_current_agent_name",
            return_value="code-puppy",
        ),
    ):
        yield


def _fake_impl(response="did the thing", error=None, session_id="sess-abc123"):
    async def impl(
        context,
        agent_name,
        prompt,
        session_id_=None,
        model_name=None,
        emit_response_message=True,
    ):
        assert emit_response_message is False
        return SimpleNamespace(
            response=response,
            agent_name=agent_name,
            session_id=session_id,
            error=error,
        )

    return impl


async def _wait_for_forks():
    tasks = [r.task for r in rc._forks.values()]
    await asyncio.gather(*tasks, return_exceptions=True)
    # Done-callbacks run via call_soon; yield once so they fire.
    await asyncio.sleep(0)


# =========================================================================
# Parsing + dispatch
# =========================================================================


def test_parse_no_agent_prefix():
    assert rc._parse_fork_args("do a thing") == (None, "do a thing")


def test_parse_agent_prefix():
    assert rc._parse_fork_args("@qa-kitten test the login page") == (
        "qa-kitten",
        "test the login page",
    )


def test_parse_agent_prefix_without_prompt():
    assert rc._parse_fork_args("@qa-kitten") == ("qa-kitten", "")


def test_unrelated_command_returns_none():
    assert rc._handle_custom_command("/other", "other") is None


def test_help_lists_both_commands():
    names = [name for name, _ in rc._custom_help()]
    assert names == ["fork", "forks"]


# =========================================================================
# /fork argument validation (sync paths, no loop needed)
# =========================================================================


def test_fork_bare_shows_usage():
    infos = []
    with patch.object(rc, "_emit_info", infos.append):
        assert rc._handle_fork("/fork") is True
    assert any("Usage" in str(m) for m in infos)


def test_fork_agent_but_no_prompt_warns():
    warnings = []
    with patch.object(rc, "_emit_warning", warnings.append):
        assert rc._handle_fork("/fork @qa-kitten") is True
    assert warnings and not rc._forks


def test_fork_unknown_agent_warns_with_available_list():
    warnings = []
    with patch.object(rc, "_emit_warning", warnings.append):
        assert rc._handle_fork("/fork @nonexistent do stuff") is True
    assert warnings and "qa-kitten" in warnings[0]
    assert not rc._forks


def test_fork_without_event_loop_warns():
    warnings = []
    with patch.object(rc, "_emit_warning", warnings.append):
        assert rc._handle_fork("/fork do a thing") is True
    assert any("event loop" in str(m) for m in warnings)
    assert not rc._forks


def test_fork_cancel_non_numeric_id_warns():
    warnings = []
    with patch.object(rc, "_emit_warning", warnings.append):
        assert rc._handle_fork("/fork cancel nope") is True
    assert warnings


def test_fork_cancel_unknown_id_warns():
    warnings = []
    with patch.object(rc, "_emit_warning", warnings.append):
        assert rc._handle_fork("/fork cancel 999") is True
    assert any("999" in str(m) for m in warnings)


# =========================================================================
# Fork lifecycle (async)
# =========================================================================


def test_started_message_is_rich_and_theme_aware():
    from code_puppy.messaging.rich_renderer import DEFAULT_STYLES

    with patch.dict(
        DEFAULT_STYLES,
        {MessageLevel.INFO: "#123456", MessageLevel.DEBUG: "dim #654321"},
    ):
        message = rc._started_message(7, "qa-kitten")

    assert isinstance(message, Text)
    assert message.plain == (
        "fork #7: qa-kitten started in the background — results land when it "
        "finishes (/forks for status)"
    )
    assert "[bold" not in message.plain
    assert message.style == "#123456"
    assert [span.style for span in message.spans] == ["bold", "dim #654321"]


def test_response_message_identifies_fork_and_renders_markdown():
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=100)

    with patch("code_puppy.config.get_banner_color", return_value="dark_orange3"):
        message = rc._response_message(7, "qa-kitten", "**did the thing**")
        console.print(message)

    assert isinstance(message, Group)
    rendered = output.getvalue()
    assert rendered.startswith("\n FORK #7 RESPONSE")
    assert "FORK #7 RESPONSE" in rendered
    assert "qa-kitten" in rendered
    assert "did the thing" in rendered
    assert "AGENT RESPONSE" not in rendered


async def test_fork_success_emits_response_and_completion_banner():
    infos, responses, successes = [], [], []
    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(),
        ),
        patch.object(rc, "_emit_info", infos.append),
        patch.object(rc, "_emit_agent_response", responses.append),
        patch.object(rc, "_emit_success", successes.append),
    ):
        assert rc._handle_fork("/fork @qa-kitten test everything") is True
        assert len(rc._forks) == 1
        await _wait_for_forks()

    record = next(iter(rc._forks.values()))
    assert record.status == "done"
    assert record.agent_name == "qa-kitten"
    assert record.session_id == "sess-abc123"
    assert any(
        isinstance(m, Text) and "started in the background" in m.plain for m in infos
    )
    assert len(responses) == 1
    assert isinstance(responses[0], Group)
    assert any("finished" in str(m) for m in successes)


async def test_fork_publishes_completion_lifecycle_event():
    lifecycle_events = []

    async def capture(*args):
        lifecycle_events.append(args)

    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(),
        ),
        patch("code_puppy.callbacks.on_post_tool_call", new=capture),
        patch.object(rc, "_emit_info"),
        patch.object(rc, "_emit_success"),
    ):
        rc._handle_fork("/fork @qa-kitten inspect lifecycle")
        await _wait_for_forks()

    assert len(lifecycle_events) == 1
    tool_name, tool_args, result, duration_ms, context = lifecycle_events[0]
    assert tool_name == "invoke_agent"
    assert tool_args == {
        "agent_name": "qa-kitten",
        "prompt": "inspect lifecycle",
    }
    assert result.session_id == "sess-abc123"
    assert duration_ms >= 0
    assert context == {"detached_fork": True}


async def test_fork_defaults_to_current_agent():
    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(),
        ),
        patch.object(rc, "_emit_info"),
        patch.object(rc, "_emit_success"),
    ):
        rc._handle_fork("/fork summarize the repo")
        await _wait_for_forks()

    record = next(iter(rc._forks.values()))
    assert record.agent_name == "code-puppy"
    assert record.prompt == "summarize the repo"


async def test_fork_reports_result_error_as_failure():
    errors = []
    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(error="model exploded\ntraceback junk"),
        ),
        patch.object(rc, "_emit_info"),
        patch.object(rc, "_emit_error", errors.append),
    ):
        rc._handle_fork("/fork doomed prompt")
        await _wait_for_forks()

    record = next(iter(rc._forks.values()))
    assert record.status == "failed"
    # Only the first line of the error should appear in the banner.
    assert any("model exploded" in str(m) for m in errors)
    assert not any("traceback junk" in str(m) for m in errors)


async def test_fork_reports_crash_as_failure():
    async def boom(
        context,
        agent_name,
        prompt,
        session_id=None,
        model_name=None,
        emit_response_message=True,
    ):
        assert emit_response_message is False
        raise RuntimeError("kaboom")

    errors = []
    with (
        patch("code_puppy.tools.subagent_invocation._invoke_agent_impl", new=boom),
        patch.object(rc, "_emit_info"),
        patch.object(rc, "_emit_error", errors.append),
    ):
        rc._handle_fork("/fork crash me")
        await _wait_for_forks()

    record = next(iter(rc._forks.values()))
    assert record.status == "failed"
    assert any("kaboom" in str(m) for m in errors)


async def test_fork_cancel_running_fork():
    started = asyncio.Event()

    async def slow(
        context,
        agent_name,
        prompt,
        session_id=None,
        model_name=None,
        emit_response_message=True,
    ):
        assert emit_response_message is False
        started.set()
        await asyncio.sleep(60)

    warnings = []
    with (
        patch("code_puppy.tools.subagent_invocation._invoke_agent_impl", new=slow),
        patch.object(rc, "_emit_info"),
        patch.object(rc, "_emit_warning", warnings.append),
    ):
        rc._handle_fork("/fork slow task")
        await started.wait()
        fork_id = next(iter(rc._forks))
        rc._handle_fork(f"/fork cancel {fork_id}")
        await _wait_for_forks()

    record = rc._forks[fork_id]
    assert record.status == "cancelled"
    assert any("cancelled" in str(m) for m in warnings)


async def test_fork_cancel_finished_fork_is_noop():
    infos = []
    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(),
        ),
        patch.object(rc, "_emit_info", infos.append),
        patch.object(rc, "_emit_success"),
    ):
        rc._handle_fork("/fork quick task")
        await _wait_for_forks()
        fork_id = next(iter(rc._forks))
        rc._handle_fork(f"/fork cancel {fork_id}")

    assert rc._forks[fork_id].status == "done"
    assert any("already done" in str(m) for m in infos)


# =========================================================================
# /forks status listing
# =========================================================================


def test_forks_empty_shows_hint():
    infos = []
    with patch.object(rc, "_emit_info", infos.append):
        assert rc._handle_forks("/forks") is True
    assert any("No forks yet" in str(m) for m in infos)


async def test_forks_lists_records_in_a_table():
    emitted = []
    with (
        patch(
            "code_puppy.tools.subagent_invocation._invoke_agent_impl",
            new=_fake_impl(),
        ),
        patch.object(rc, "_emit_info", emitted.append),
        patch.object(rc, "_emit_success"),
    ):
        rc._handle_fork("/fork @qa-kitten check stuff")
        await _wait_for_forks()
        rc._handle_forks("/forks")

    from rich.table import Table

    tables = [m for m in emitted if isinstance(m, Table)]
    assert len(tables) == 1
