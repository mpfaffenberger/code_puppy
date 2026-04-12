import asyncio
import contextlib
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import ConditionalCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import TransformationInput

from code_puppy.command_line.interactive_runtime import (
    PromptRuntimeState,
    clear_active_interactive_runtime,
    register_active_interactive_runtime,
)
from code_puppy.command_line.prompt_toolkit_completion import (
    AttachmentPlaceholderProcessor,
    PromptSubmission,
    clear_active_prompt_surface,
    get_active_prompt_surface_kind,
    get_input_with_combined_completion,
    get_prompt_with_active_model,
    has_active_prompt_surface,
    is_shell_prompt_suspended,
    prompt_for_submission,
    register_active_prompt_surface,
    render_submitted_prompt_echo,
    render_transcript_notice,
    set_shell_prompt_suspended,
)


@pytest.fixture
def active_runtime():
    runtime = PromptRuntimeState()
    register_active_interactive_runtime(runtime)
    yield runtime
    clear_active_interactive_runtime(runtime)


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_submitted_prompt_echo(mock_create_output, mock_print_formatted_text):
    mock_output = MagicMock()
    mock_create_output.return_value = mock_output

    render_submitted_prompt_echo("queued task")

    mock_create_output.assert_called_once()
    mock_print_formatted_text.assert_called_once()
    rendered = mock_print_formatted_text.call_args.args[0]
    assert any("queued task" in text for _style, text in rendered)


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_submitted_prompt_echo_uses_prompt_app_when_available(
    mock_create_output, mock_print_formatted_text, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)
    active_runtime.run_above_prompt = MagicMock(return_value=True)

    render_submitted_prompt_echo("queued task")

    active_runtime.run_above_prompt.assert_called_once()
    session.app.print_text.assert_not_called()
    mock_create_output.assert_not_called()
    mock_print_formatted_text.assert_not_called()


def test_runtime_request_queue_respects_configured_queue_limit(active_runtime):
    with patch(
        "code_puppy.command_line.interactive_runtime.get_queue_limit", return_value=2
    ):
        ok, position, item = active_runtime.request_queue("first")
        assert ok is True
        assert position == 1
        assert item is not None

        ok, position, item = active_runtime.request_queue("second")
        assert ok is True
        assert position == 2
        assert item is not None

        ok, position, item = active_runtime.request_queue("third")
        assert ok is False
        assert position == 2
        assert item is None


def test_runtime_request_interject_respects_configured_queue_limit(active_runtime):
    with patch(
        "code_puppy.command_line.interactive_runtime.get_queue_limit", return_value=1
    ):
        ok, position, item = active_runtime.request_interject("now")
        assert ok is True
        assert position == 1
        assert item is not None

        ok, position, item = active_runtime.request_interject("later")
        assert ok is False
        assert position == 1
        assert item is None


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_transcript_notice(mock_create_output, mock_print_formatted_text):
    mock_output = MagicMock()
    mock_create_output.return_value = mock_output

    render_transcript_notice("[QUEUE TRIGGERED] queued task")

    mock_create_output.assert_called_once()
    mock_print_formatted_text.assert_called_once()
    rendered = mock_print_formatted_text.call_args.args[0]
    assert any("[QUEUE TRIGGERED] queued task" in text for _style, text in rendered)


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_transcript_notice_uses_prompt_app_when_available(
    mock_create_output, mock_print_formatted_text, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)
    active_runtime.run_above_prompt = MagicMock(return_value=True)

    render_transcript_notice("[QUEUE TRIGGERED] queued task")

    active_runtime.run_above_prompt.assert_called_once()
    session.app.print_text.assert_not_called()
    mock_create_output.assert_not_called()
    mock_print_formatted_text.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.patch_stdout")
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion.merge_completers")
async def test_prompt_for_submission_allows_at_completion_while_busy_but_blocks_it_in_chooser(
    mock_merge_completers,
    mock_prompt_session_cls,
    mock_patch_stdout,
    active_runtime,
):
    active_runtime.running = True
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test input")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_merge_completers.return_value = MagicMock()
    mock_patch_stdout.return_value.__enter__ = MagicMock()
    mock_patch_stdout.return_value.__exit__ = MagicMock(return_value=False)

    await prompt_for_submission()

    attachment_completer = mock_merge_completers.call_args.args[0][0]
    assert isinstance(attachment_completer, ConditionalCompleter)
    assert attachment_completer.filter() is True

    active_runtime.set_pending_submission("queued task")
    assert attachment_completer.filter() is False


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion._interrupt_shell_from_prompt")
async def test_get_input_key_binding_ctrl_c_shell_interrupt_suppresses_queue_autodrain(
    mock_interrupt_shell, mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    ctrl_c_binding = next(
        binding_obj for binding_obj in bindings.bindings if binding_obj.keys == ("c-c",)
    )

    active_runtime.notify_shell_started()
    active_runtime.request_queue("queued task")
    active_runtime.set_pending_submission("draft")

    buffer = Buffer(document=Document(text="chooser text", cursor_position=11))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    ctrl_c_binding.handler(mock_event)

    mock_interrupt_shell.assert_called_once_with("Ctrl-C")
    assert active_runtime.is_queue_autodrain_suppressed() is True
    assert active_runtime.has_pending_submission() is False
    assert buffer.text == ""
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion._interrupt_shell_from_prompt")
async def test_get_input_key_binding_configured_cancel_shell_interrupt_suppresses_queue_autodrain(
    mock_interrupt_shell, mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    with patch(
        "code_puppy.command_line.prompt_toolkit_completion.get_value",
        side_effect=lambda key, default=None: "ctrl+k"
        if key == "cancel_agent_key"
        else default,
    ):
        await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    ctrl_k_binding = next(
        binding_obj for binding_obj in bindings.bindings if binding_obj.keys == ("c-k",)
    )

    active_runtime.notify_shell_started()
    active_runtime.request_queue("queued task")
    active_runtime.set_pending_submission("draft")

    buffer = Buffer(document=Document(text="chooser text", cursor_position=11))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    ctrl_k_binding.handler(mock_event)

    mock_interrupt_shell.assert_called_once_with("CTRL+K")
    assert active_runtime.is_queue_autodrain_suppressed() is True
    assert active_runtime.has_pending_submission() is False
    assert buffer.text == ""
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_key_binding_escape_drops_pending_submission(
    mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    escape_binding = next(
        binding_obj
        for binding_obj in bindings.bindings
        if binding_obj.keys == (Keys.Escape,)
    )

    active_runtime.set_pending_submission("queued task")

    buffer = Buffer(document=Document(text="stray chooser text", cursor_position=18))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    escape_binding.handler(mock_event)

    assert active_runtime.has_pending_submission() is False
    assert buffer.text == ""
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_key_binding_up_restores_pending_submission(
    mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    up_binding = next(
        binding_obj
        for binding_obj in bindings.bindings
        if binding_obj.keys == (Keys.Up,)
    )

    assert up_binding.filter() is False

    active_runtime.set_pending_submission("queued task")
    assert up_binding.filter() is True

    buffer = Buffer(document=Document(text="stray chooser text", cursor_position=18))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    up_binding.handler(mock_event)

    assert active_runtime.has_pending_submission() is False
    assert buffer.text == "queued task"
    assert buffer.cursor_position == len("queued task")
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_key_binding_edit_restores_pending_submission(
    mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    edit_binding = next(
        binding_obj for binding_obj in bindings.bindings if binding_obj.keys == ("e",)
    )

    assert edit_binding.filter() is False

    active_runtime.set_pending_submission("queued task")
    assert edit_binding.filter() is True

    buffer = Buffer(document=Document(text="stray chooser text", cursor_position=18))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    edit_binding.handler(mock_event)

    assert active_runtime.has_pending_submission() is False
    assert buffer.text == "queued task"
    assert buffer.cursor_position == len("queued task")
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_empty_enter_recalls_next_paused_queue_prompt(
    mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    enter_binding = next(
        binding_obj
        for binding_obj in bindings.bindings
        if binding_obj.keys == (Keys.ControlM,)
    )

    active_runtime.request_queue("queued task", allow_command_dispatch=False)
    active_runtime.suppress_queue_autodrain()

    buffer = Buffer(document=Document(text="", cursor_position=0))
    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.current_buffer = buffer

    enter_binding.handler(mock_event)

    assert buffer.text == "queued task"
    assert buffer.cursor_position == len("queued task")
    assert len(active_runtime.queue) == 1
    assert active_runtime.queue[0].text == "queued task"
    assert active_runtime.queue[0].allow_command_dispatch is False
    mock_event.app.exit.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.patch_stdout")
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_prompt_for_submission_recalled_queue_preserves_policy_and_dequeues_on_submit(
    mock_prompt_session_cls, mock_patch_stdout, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.default_buffer = Buffer(
        document=Document(text="", cursor_position=0)
    )
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_patch_stdout.return_value.__enter__ = MagicMock()
    mock_patch_stdout.return_value.__exit__ = MagicMock(return_value=False)

    active_runtime.request_queue("/agent", allow_command_dispatch=False)
    active_runtime.suppress_queue_autodrain()

    async def fake_prompt_async(*args, **kwargs):
        bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
        enter_binding = next(
            binding_obj
            for binding_obj in bindings.bindings
            if binding_obj.keys == (Keys.ControlM,)
        )
        mock_event = MagicMock()
        mock_event.app = MagicMock()
        mock_event.app.current_buffer = mock_session_instance.default_buffer
        enter_binding.handler(mock_event)
        return mock_session_instance.default_buffer.text

    mock_session_instance.prompt_async = AsyncMock(side_effect=fake_prompt_async)

    result = await prompt_for_submission()

    assert result == PromptSubmission(
        action="submit",
        text="/agent",
        echo_in_transcript=False,
        allow_command_dispatch=False,
    )
    assert active_runtime.queue == []


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_chooser_makes_buffer_read_only(
    mock_prompt_session_cls, active_runtime
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_session_instance.default_buffer = MagicMock()
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    read_only_filter = mock_session_instance.default_buffer.read_only
    assert read_only_filter() is False

    active_runtime.set_pending_submission("queued task")
    assert read_only_filter() is True

    active_runtime.set_pending_submission(None)
    assert read_only_filter() is False


def test_prompt_runtime_registry_round_trip(active_runtime):
    session = MagicMock()
    session.app = MagicMock()

    clear_active_prompt_surface()
    register_active_prompt_surface("main", session)

    assert has_active_prompt_surface() is True
    assert get_active_prompt_surface_kind() == "main"
    assert is_shell_prompt_suspended() is False

    session.app.invalidate.reset_mock()
    set_shell_prompt_suspended(True)
    assert is_shell_prompt_suspended() is True
    session.app.invalidate.assert_called_once()

    set_shell_prompt_suspended(False)
    clear_active_prompt_surface(session)
    assert has_active_prompt_surface() is False
    assert get_active_prompt_surface_kind() is None
    assert is_shell_prompt_suspended() is False


def test_spinner_invalidation_yields_to_recent_prompt_redraw(
    monkeypatch, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)
    session.app.invalidate.reset_mock()

    samples = iter([10.0, 10.02, 10.12])
    monkeypatch.setattr(
        "code_puppy.command_line.interactive_runtime.time.monotonic",
        lambda: next(samples),
    )

    active_runtime.invalidate_prompt()
    session.app.invalidate.assert_called_once()

    session.app.invalidate.reset_mock()
    active_runtime.invalidate_prompt_for_spinner()
    session.app.invalidate.assert_not_called()

    active_runtime.invalidate_prompt_for_spinner()
    session.app.invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_run_above_prompt_async_serializes_callbacks(active_runtime, monkeypatch):
    session = MagicMock()
    session.app = MagicMock()
    session.app.loop = asyncio.get_running_loop()
    active_runtime.register_prompt_surface(session)

    active_count = 0
    max_active = 0
    seen: list[str] = []

    async def fake_run_in_terminal(func):
        nonlocal active_count, max_active
        active_count += 1
        max_active = max(max_active, active_count)
        await asyncio.sleep(0.01)
        func()
        await asyncio.sleep(0.01)
        active_count -= 1

    monkeypatch.setattr(
        "prompt_toolkit.application.run_in_terminal",
        fake_run_in_terminal,
    )

    first = asyncio.create_task(
        active_runtime.run_above_prompt_async(lambda: seen.append("first"))
    )
    await asyncio.sleep(0)
    second = asyncio.create_task(
        active_runtime.run_above_prompt_async(lambda: seen.append("second"))
    )

    assert await first is True
    assert await second is True
    assert seen == ["first", "second"]
    assert max_active == 1


@pytest.mark.asyncio
async def test_run_above_prompt_sync_and_async_share_serialization(
    active_runtime, monkeypatch
):
    session = MagicMock()
    session.app = MagicMock()
    session.app.loop = asyncio.get_running_loop()
    active_runtime.register_prompt_surface(session)

    active_count = 0
    max_active = 0
    seen: list[str] = []
    sync_result: dict[str, bool] = {}

    async def fake_run_in_terminal(func):
        nonlocal active_count, max_active
        active_count += 1
        max_active = max(max_active, active_count)
        await asyncio.sleep(0.01)
        func()
        await asyncio.sleep(0.01)
        active_count -= 1

    monkeypatch.setattr(
        "prompt_toolkit.application.run_in_terminal",
        fake_run_in_terminal,
    )

    async_task = asyncio.create_task(
        active_runtime.run_above_prompt_async(lambda: seen.append("async"))
    )
    await asyncio.sleep(0.005)

    def call_sync() -> None:
        sync_result["ok"] = active_runtime.run_above_prompt(
            lambda: seen.append("sync"),
            timeout=1.0,
        )

    thread = threading.Thread(target=call_sync)
    thread.start()

    assert await async_task is True
    for _ in range(50):
        if "ok" in sync_result:
            break
        await asyncio.sleep(0.01)
    thread.join()

    assert sync_result == {"ok": True}
    assert seen == ["async", "sync"]
    assert max_active == 1


def test_get_prompt_with_active_model_omits_shell_status(monkeypatch, active_runtime):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    set_shell_prompt_suspended(True)

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with patch(
        "code_puppy.command_line.prompt_toolkit_completion._get_current_agent_for_prompt",
        return_value=agent,
    ):
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))):
            rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "shell running" not in rendered
    clear_active_prompt_surface()


def test_get_prompt_with_active_model_shows_thinking_status(
    monkeypatch, active_runtime
):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    active_runtime.running = True
    active_runtime.prompt_status_started_at = 0.0

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.interactive_runtime.time.monotonic",
        lambda: 0.18,
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion._get_current_agent_for_prompt",
            return_value=agent,
        ),
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.SpinnerBase.get_context_info",
            return_value="Tokens: 1,650/272,000 (0.6% used)",
        ),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
    ):
        rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "Buddy is thinking..." in rendered
    assert "(  🐶  ) " in rendered
    assert "Tokens: 1,650/272,000 (0.6% used)" in rendered
    assert rendered.index("Buddy is thinking...") < rendered.index("─" * 80)
    clear_active_prompt_surface()


def test_get_prompt_with_active_model_shows_pending_hint_copy(
    monkeypatch, active_runtime
):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    active_runtime.set_pending_submission("queued task")

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion._get_current_agent_for_prompt",
            return_value=agent,
        ),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
    ):
        rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "[i]nterject [q]ueue [e]dit [esc]ape" in rendered
    clear_active_prompt_surface()


def test_get_prompt_with_active_model_shows_ephemeral_status(monkeypatch, active_runtime):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    active_runtime.running = True
    active_runtime.prompt_status_started_at = 0.0
    active_runtime.set_prompt_ephemeral_status("🔧 Calling list_files... 11 token(s)")
    active_runtime.set_prompt_ephemeral_preview(
        "\n".join(
            [
                "line 1",
                "line 2",
                "line 3",
                "line 4",
                "line 5",
                "line 6",
                "line 7",
                "line 8",
            ]
        )
    )

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.interactive_runtime.time.monotonic",
        lambda: 0.18,
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion._get_current_agent_for_prompt",
            return_value=agent,
        ),
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.SpinnerBase.get_context_info",
            return_value="",
        ),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
    ):
        rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "🔧 Calling list_files... 11 token(s)" in rendered
    assert "line 1" not in rendered
    assert "line 2" not in rendered
    assert "line 3" in rendered
    assert "line 8" in rendered
    assert rendered.index("🔧 Calling list_files... 11 token(s)") < rendered.index(
        "line 3"
    )
    active_runtime.clear_prompt_ephemeral_status()
    active_runtime.clear_prompt_ephemeral_preview()
    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion._get_current_agent_for_prompt",
            return_value=agent,
        ),
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.SpinnerBase.get_context_info",
            return_value="",
        ),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
    ):
        cleared = "".join(text for _style, text in get_prompt_with_active_model())

    assert "🔧 Calling list_files... 11 token(s)" not in cleared
    assert "line 8" not in cleared
    clear_active_prompt_surface()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_registers_active_prompt_surface(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()

    async def fake_prompt_async(*args, **kwargs):
        assert has_active_prompt_surface() is True
        assert get_active_prompt_surface_kind() == "main"
        set_shell_prompt_suspended(True)
        assert is_shell_prompt_suspended() is True
        set_shell_prompt_suspended(False)
        return "test input"

    session.prompt_async = AsyncMock(side_effect=fake_prompt_async)
    mock_prompt_session_cls.return_value = session

    result = await get_input_with_combined_completion()

    assert result == "test input"
    assert has_active_prompt_surface() is False
    assert is_shell_prompt_suspended() is False


@pytest.mark.asyncio
async def test_prompt_runtime_refreshes_spinner_while_running(active_runtime):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)

    worker = asyncio.create_task(asyncio.sleep(1))
    active_runtime.mark_running(worker)
    session.app.invalidate.reset_mock()

    try:
        await asyncio.sleep(0.12)
        assert session.app.invalidate.called
        assert active_runtime.prompt_status_task is not None
    finally:
        active_runtime.mark_idle()
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    await asyncio.sleep(0)
    assert active_runtime.prompt_status_task is None


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_ctrl_x_interrupts_shell_when_prompt_is_suspended(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()
    session.prompt_async = AsyncMock(return_value="done")
    mock_prompt_session_cls.return_value = session

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    ctrl_x_handler = next(
        binding.handler
        for binding in bindings.bindings
        if binding.keys == (Keys.ControlX,)
    )

    register_active_prompt_surface("main", session)
    set_shell_prompt_suspended(True)

    mock_event = MagicMock()
    mock_event.app = MagicMock()

    with patch(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes",
        return_value=1,
    ) as mock_kill:
        with patch("code_puppy.messaging.emit_warning"):
            ctrl_x_handler(mock_event)

    mock_kill.assert_called_once()
    mock_event.app.exit.assert_not_called()
    clear_active_prompt_surface()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_prompt_for_submission_returns_inline_queue_action(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()
    session.prompt_async = AsyncMock(
        return_value=PromptSubmission(action="queue", text="queued task")
    )
    mock_prompt_session_cls.return_value = session

    result = await prompt_for_submission()

    assert result == PromptSubmission(
        action="queue",
        text="queued task",
        echo_in_transcript=False,
    )


@pytest.mark.asyncio
async def test_attachment_placeholder_processor_renders_images(tmp_path: Path) -> None:
    image_path = tmp_path / "fluffy pupper.png"
    image_path.write_bytes(b"png")

    processor = AttachmentPlaceholderProcessor()
    document_text = f"describe {image_path} now"
    document = Document(text=document_text, cursor_position=len(document_text))

    fragments = [("", document_text)]
    buffer = Buffer(document=document)
    control = BufferControl(buffer=buffer)
    transformation_input = TransformationInput(
        buffer_control=control,
        document=document,
        lineno=0,
        source_to_display=lambda i: i,
        fragments=fragments,
        width=len(document_text),
        height=1,
    )

    transformed = processor.apply_transformation(transformation_input)
    rendered_text = "".join(text for _style, text in transformed.fragments)

    assert "[png image]" in rendered_text
    assert "fluffy pupper" not in rendered_text


def test_attachment_placeholder_processor_skips_replacement_while_chooser_visible(
    tmp_path: Path, active_runtime
) -> None:
    image_path = tmp_path / "chooser.png"
    image_path.write_bytes(b"png")
    active_runtime.set_pending_submission("queued task")

    processor = AttachmentPlaceholderProcessor()
    document_text = f"describe {image_path} now"
    document = Document(text=document_text, cursor_position=len(document_text))

    fragments = [("", document_text)]
    buffer = Buffer(document=document)
    control = BufferControl(buffer=buffer)
    transformation_input = TransformationInput(
        buffer_control=control,
        document=document,
        lineno=0,
        source_to_display=lambda i: i,
        fragments=fragments,
        width=len(document_text),
        height=1,
    )

    transformed = processor.apply_transformation(transformation_input)
    rendered_text = "".join(text for _style, text in transformed.fragments)

    assert str(image_path) in rendered_text
    assert "[png image]" not in rendered_text
