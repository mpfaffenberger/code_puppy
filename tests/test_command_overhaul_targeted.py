import asyncio
import importlib
import threading
from contextlib import ExitStack
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.interactive_command import BackgroundInteractiveCommand
from code_puppy.command_line.interactive_runtime import get_active_interactive_runtime
from code_puppy.command_line.prompt_toolkit_completion import PromptSubmission


def _renderer():
    renderer = MagicMock()
    renderer.console = MagicMock()
    renderer.console.file = MagicMock()
    renderer.console.file.flush = MagicMock()
    return renderer


def _submission(
    text: str, *, action: str = "submit", allow_command_dispatch: bool = True
):
    return PromptSubmission(
        action=action,
        text=text,
        allow_command_dispatch=allow_command_dispatch,
    )


async def _run_interactive(
    prompt_side_effect, *, run_prompt_side_effect, handle_command
):
    agent = MagicMock()
    agent.get_user_prompt.return_value = "task:"
    fake_agents_pkg = ModuleType("code_puppy.agents")
    fake_agent_manager = ModuleType("code_puppy.agents.agent_manager")
    fake_agent_manager.get_current_agent = MagicMock(return_value=agent)
    fake_agents_pkg.agent_manager = fake_agent_manager
    fake_agents_pkg.get_current_agent = fake_agent_manager.get_current_agent

    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.agents": fake_agents_pkg,
                    "code_puppy.agents.agent_manager": fake_agent_manager,
                    "code_puppy.command_line.command_handler": MagicMock(
                        handle_command=handle_command
                    ),
                },
            )
        )
        cli_runner_module = importlib.import_module("code_puppy.cli_runner")
        stack.enter_context(
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.prompt_for_submission",
                side_effect=prompt_side_effect,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
                return_value="> ",
            )
        )
        stack.enter_context(patch.object(cli_runner_module, "print_truecolor_warning"))
        stack.enter_context(
            patch.object(
                cli_runner_module,
                "get_cancel_agent_display_name",
                return_value="Ctrl+C",
            )
        )
        stack.enter_context(
            patch.object(cli_runner_module, "reset_windows_terminal_ansi")
        )
        stack.enter_context(
            patch.object(cli_runner_module, "reset_windows_terminal_full")
        )
        stack.enter_context(patch.object(cli_runner_module, "save_command_to_history"))
        stack.enter_context(patch("code_puppy.command_line.motd.print_motd"))
        stack.enter_context(
            patch(
                "code_puppy.command_line.onboarding_wizard.should_show_onboarding",
                return_value=False,
            )
        )
        stack.enter_context(
            patch.object(
                cli_runner_module,
                "run_prompt_with_attachments",
                side_effect=run_prompt_side_effect,
            )
        )
        await cli_runner_module.interactive_mode(_renderer())


@pytest.mark.anyio
async def test_busy_slash_text_queues_as_literal_prompt():
    release_first = asyncio.Event()
    queued_started = asyncio.Event()
    started_prompts: list[str] = []
    handle_command = MagicMock(return_value=True)

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("first task")
        if prompt_side_effect.calls == 2:
            release_first.set()
            return _submission(
                "/model",
                action="queue",
                allow_command_dispatch=False,
            )
        await queued_started.wait()
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        started_prompts.append(prompt)
        if prompt == "first task":
            await release_first.wait()
        if prompt == "/model":
            queued_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    assert started_prompts[:2] == ["first task", "/model"]
    handle_command.assert_not_called()


@pytest.mark.anyio
async def test_hooks_list_dispatches_as_idle_command():
    handle_command = MagicMock(return_value=True)

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("/hooks list")
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        raise AssertionError(f"unexpected agent run for {prompt}")

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    handle_command.assert_called_once_with("/hooks list")


def test_chatgpt_auth_returns_background_interactive_command():
    from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
        _handle_custom_command,
        start_chatgpt_oauth_setup,
    )

    result = _handle_custom_command("/chatgpt-auth", "chatgpt-auth")

    assert isinstance(result, BackgroundInteractiveCommand)
    assert result.run is start_chatgpt_oauth_setup


def test_chatgpt_auth_switches_model_only_on_success():
    from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
        start_chatgpt_oauth_setup,
    )

    cancel_event = threading.Event()

    with (
        patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.run_oauth_flow",
            return_value=True,
        ) as mock_flow,
        patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.set_model_and_reload_agent"
        ) as mock_set_model,
    ):
        assert start_chatgpt_oauth_setup(cancel_event) is True

    mock_flow.assert_called_once_with(cancel_event=cancel_event)
    mock_set_model.assert_called_once_with("chatgpt-gpt-5.3-codex")


def test_chatgpt_auth_cancel_does_not_switch_model():
    from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
        start_chatgpt_oauth_setup,
    )

    cancel_event = threading.Event()
    cancel_event.set()

    with (
        patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.run_oauth_flow",
            return_value=False,
        ),
        patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.set_model_and_reload_agent"
        ) as mock_set_model,
    ):
        assert start_chatgpt_oauth_setup(cancel_event) is False

    mock_set_model.assert_not_called()


def test_claude_auth_returns_background_interactive_command():
    from code_puppy.plugins.claude_code_oauth.register_callbacks import (
        _handle_custom_command,
        start_claude_code_oauth_setup,
    )

    result = _handle_custom_command("/claude-code-auth", "claude-code-auth")

    assert isinstance(result, BackgroundInteractiveCommand)
    assert result.run is start_claude_code_oauth_setup


def test_antigravity_add_returns_background_interactive_command():
    from code_puppy.plugins.antigravity_oauth.register_callbacks import (
        _handle_custom_command,
    )

    with patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
        return_value=MagicMock(account_count=1),
    ):
        result = _handle_custom_command("/antigravity-add", "antigravity-add")

    assert isinstance(result, BackgroundInteractiveCommand)


@pytest.mark.anyio
async def test_interject_during_background_command_cancels_cleanly():
    wait_started = asyncio.Event()
    interject_started = asyncio.Event()
    loop = asyncio.get_running_loop()
    started_prompts: list[str] = []

    def auth_wait(cancel_event: threading.Event) -> None:
        loop.call_soon_threadsafe(wait_started.set)
        cancel_event.wait(timeout=5)

    handle_command = MagicMock(
        side_effect=lambda command: (
            BackgroundInteractiveCommand(run=auth_wait)
            if command == "/claude-code-auth"
            else True
        )
    )

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("/claude-code-auth")
        if prompt_side_effect.calls == 2:
            await wait_started.wait()
            return _submission("please continue", action="interject")
        await interject_started.wait()
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        started_prompts.append(prompt)
        if prompt.startswith("user interjects - please continue"):
            interject_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    assert len(started_prompts) == 1
    assert started_prompts[0].startswith("user interjects - please continue - ")
    assert "continue the interrupted task" in started_prompts[0]
    handle_command.assert_called_once_with("/claude-code-auth")


@pytest.mark.anyio
async def test_queue_during_background_command_drains_after_wait_completes():
    wait_started = asyncio.Event()
    queued_started = asyncio.Event()
    release_wait = threading.Event()
    loop = asyncio.get_running_loop()
    started_prompts: list[str] = []

    def auth_wait(cancel_event: threading.Event) -> None:
        loop.call_soon_threadsafe(wait_started.set)
        while not cancel_event.is_set():
            if release_wait.wait(timeout=0.05):
                return

    handle_command = MagicMock(
        side_effect=lambda command: (
            BackgroundInteractiveCommand(run=auth_wait)
            if command == "/claude-code-auth"
            else True
        )
    )

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("/claude-code-auth")
        if prompt_side_effect.calls == 2:
            await wait_started.wait()
            release_wait.set()
            return _submission("report later", action="queue")
        await queued_started.wait()
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        started_prompts.append(prompt)
        if prompt == "report later":
            queued_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    assert started_prompts == ["report later"]
    handle_command.assert_called_once_with("/claude-code-auth")


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_reason", ["ctrl_c", "ctrl+k"])
async def test_manual_cancel_pauses_queued_prompts_until_user_acts(cancel_reason: str):
    first_cancelled = asyncio.Event()
    queued_started = asyncio.Event()
    started_prompts: list[str] = []
    handle_command = MagicMock(return_value=True)

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("first task")
        if prompt_side_effect.calls == 2:
            return _submission("queued task", action="queue")
        if prompt_side_effect.calls == 3:
            runtime = get_active_interactive_runtime()
            assert runtime is not None
            assert runtime.request_active_cancel(cancel_reason) is True
            return _submission("")

        await first_cancelled.wait()
        await asyncio.sleep(0.05)
        runtime = get_active_interactive_runtime()
        assert runtime is not None
        assert runtime.is_queue_autodrain_suppressed() is True
        assert [item.text for item in runtime.queue] == ["queued task"]
        assert queued_started.is_set() is False
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        started_prompts.append(prompt)
        if prompt == "first task":
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                first_cancelled.set()
                raise
        if prompt == "queued task":
            queued_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    assert started_prompts == ["first task"]


@pytest.mark.anyio
async def test_manual_cancel_queue_pause_clears_after_new_submission():
    first_cancelled = asyncio.Event()
    queued_started = asyncio.Event()
    started_prompts: list[str] = []
    handle_command = MagicMock(return_value=True)

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("first task")
        if prompt_side_effect.calls == 2:
            return _submission("queued task", action="queue")
        if prompt_side_effect.calls == 3:
            runtime = get_active_interactive_runtime()
            assert runtime is not None
            assert runtime.request_active_cancel("ctrl_c") is True
            return _submission("")
        if prompt_side_effect.calls == 4:
            await first_cancelled.wait()
            await asyncio.sleep(0.05)
            runtime = get_active_interactive_runtime()
            assert runtime is not None
            assert runtime.is_queue_autodrain_suppressed() is True
            assert [item.text for item in runtime.queue] == ["queued task"]
            return _submission("resume task")

        await queued_started.wait()
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        started_prompts.append(prompt)
        if prompt == "first task":
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                first_cancelled.set()
                raise
        if prompt == "queued task":
            queued_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    await _run_interactive(
        prompt_side_effect,
        run_prompt_side_effect=run_prompt_side_effect,
        handle_command=handle_command,
    )

    assert started_prompts[:3] == ["first task", "resume task", "queued task"]


@pytest.mark.anyio
async def test_wiggum_manual_cancel_does_not_emit_followup_input_cancelled():
    run_started = asyncio.Event()
    run_cancelled = asyncio.Event()
    handle_command = MagicMock(return_value=True)
    warning_messages: list[str] = []
    wiggum_active = {"value": False}

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("first task")
        if prompt_side_effect.calls == 2:
            await run_started.wait()
            runtime = get_active_interactive_runtime()
            assert runtime is not None
            assert runtime.request_active_cancel("ctrl_c") is True
            return _submission("")
        if prompt_side_effect.calls == 3:
            await run_cancelled.wait()
            raise KeyboardInterrupt
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        wiggum_active["value"] = True
        run_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            run_cancelled.set()
            raise

    def fake_is_wiggum_active():
        return wiggum_active["value"]

    def fake_stop_wiggum():
        wiggum_active["value"] = False

    with (
        patch(
            "code_puppy.command_line.wiggum_state.is_wiggum_active",
            side_effect=fake_is_wiggum_active,
        ),
        patch(
            "code_puppy.command_line.wiggum_state.stop_wiggum",
            side_effect=fake_stop_wiggum,
        ),
        patch(
            "code_puppy.messaging.emit_warning",
            side_effect=warning_messages.append,
        ),
    ):
        await _run_interactive(
            prompt_side_effect,
            run_prompt_side_effect=run_prompt_side_effect,
            handle_command=handle_command,
        )

    assert any("🍩 Wiggum loop stopped" in message for message in warning_messages)
    assert "\nInput cancelled" not in warning_messages


@pytest.mark.anyio
async def test_wiggum_manual_cancel_keeps_queued_prompts_paused():
    run_started = asyncio.Event()
    run_cancelled = asyncio.Event()
    queued_started = asyncio.Event()
    handle_command = MagicMock(return_value=True)
    wiggum_active = {"value": False}

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("first task")
        if prompt_side_effect.calls == 2:
            return _submission("queued task", action="queue")
        if prompt_side_effect.calls == 3:
            await run_started.wait()
            runtime = get_active_interactive_runtime()
            assert runtime is not None
            assert runtime.request_active_cancel("ctrl_c") is True
            return _submission("")
        if prompt_side_effect.calls == 4:
            await run_cancelled.wait()
            raise KeyboardInterrupt

        await asyncio.sleep(0.05)
        runtime = get_active_interactive_runtime()
        assert runtime is not None
        assert runtime.is_queue_autodrain_suppressed() is True
        assert [item.text for item in runtime.queue] == ["queued task"]
        assert queued_started.is_set() is False
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        if prompt == "first task":
            wiggum_active["value"] = True
            run_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                run_cancelled.set()
                raise
        if prompt == "queued task":
            queued_started.set()
        result = MagicMock()
        result.output = f"response for {prompt}"
        result.all_messages.return_value = []
        return result, MagicMock()

    def fake_is_wiggum_active():
        return wiggum_active["value"]

    def fake_stop_wiggum():
        wiggum_active["value"] = False

    with (
        patch(
            "code_puppy.command_line.wiggum_state.is_wiggum_active",
            side_effect=fake_is_wiggum_active,
        ),
        patch(
            "code_puppy.command_line.wiggum_state.stop_wiggum",
            side_effect=fake_stop_wiggum,
        ),
    ):
        await _run_interactive(
            prompt_side_effect,
            run_prompt_side_effect=run_prompt_side_effect,
            handle_command=handle_command,
        )


@pytest.mark.anyio
async def test_background_command_wait_does_not_autosave():
    wait_started = asyncio.Event()
    cancel_seen = threading.Event()
    loop = asyncio.get_running_loop()
    handle_command = MagicMock()

    def auth_wait(cancel_event: threading.Event) -> None:
        loop.call_soon_threadsafe(wait_started.set)
        cancel_event.wait(timeout=5)
        if cancel_event.is_set():
            cancel_seen.set()

    handle_command.side_effect = lambda command: (
        BackgroundInteractiveCommand(run=auth_wait)
        if command == "/claude-code-auth"
        else True
    )

    async def prompt_side_effect(*_args, **_kwargs):
        prompt_side_effect.calls += 1
        if prompt_side_effect.calls == 1:
            return _submission("/claude-code-auth")
        await wait_started.wait()
        return _submission("/exit")

    prompt_side_effect.calls = 0

    async def run_prompt_side_effect(_agent, prompt, **_kwargs):
        raise AssertionError(f"unexpected agent run for {prompt}")

    with patch("code_puppy.config.auto_save_session_if_enabled") as mock_autosave:
        await _run_interactive(
            prompt_side_effect,
            run_prompt_side_effect=run_prompt_side_effect,
            handle_command=handle_command,
        )

    assert cancel_seen.is_set()
    mock_autosave.assert_not_called()
    handle_command.assert_called_once_with("/claude-code-auth")


@pytest.mark.anyio
async def test_mark_idle_if_task_is_idempotent_for_finished_background_work():
    from code_puppy.command_line.interactive_runtime import PromptRuntimeState

    runtime = PromptRuntimeState()

    async def noop() -> None:
        return

    task = asyncio.create_task(noop())
    runtime.mark_running(task, kind="interactive_command")
    await task

    assert runtime.mark_idle_if_task(task) is True
    assert runtime.mark_idle_if_task(task) is False
    assert runtime.bg_task is None
