"""Shared fixtures/helpers for the cli_runner test split.

Used by test_cli_runner_main.py, test_cli_runner_interactive.py,
test_cli_runner_continuation.py, and test_cli_runner_edges.py. Not itself a
test module (no ``test_`` prefix): pytest will not collect it.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, call, patch

# Helpers
# ---------------------------------------------------------------------------


def _sync_input(fn):
    """Adapt async-mock classic-input fns to the plain input() seam."""
    import inspect as _inspect

    def _call(*args, **kwargs):
        result = fn(*args, **kwargs)
        if _inspect.iscoroutine(result):
            # Async mocks complete without awaiting anything; drive them
            # synchronously (we are already inside the event loop).
            try:
                result.send(None)
            except StopIteration as stop:
                return stop.value
            raise RuntimeError("async input mock did not finish synchronously")
        return result

    return _call


def _mock_renderer():
    r = MagicMock()
    r.console = MagicMock()
    r.console.file = MagicMock()
    r.console.file.flush = MagicMock()
    r.start = MagicMock()
    r.stop = MagicMock()
    return r


def _mock_parse_result(
    prompt="hello", warnings=None, attachments=None, link_attachments=None
):
    m = MagicMock()
    m.prompt = prompt
    m.warnings = warnings or []
    m.attachments = attachments or []
    m.link_attachments = link_attachments or []
    return m


def _mock_clipboard(images=None):
    mgr = MagicMock()
    mgr.get_pending_images.return_value = images or []
    mgr.get_pending_count.return_value = len(images) if images else 0
    mgr.clear_pending = MagicMock()
    return mgr


def _apply_patches(stack, patches_dict):
    """Apply a dict of patches using an ExitStack."""
    for target, value in patches_dict.items():
        stack.enter_context(patch(target, value))


def _assert_core_plugins_message_once(mock_emit, version):
    expected = call(f"Core plugins version: {version}")
    assert mock_emit.call_args_list.count(expected) == 1


def _base_main_patches():
    """Return a dict of common patches needed for main()."""
    return {
        "code_puppy.cli_entry.find_available_port": MagicMock(return_value=8090),
        "code_puppy.cli_entry.ensure_config_exists": MagicMock(),
        "code_puppy.cli_entry.validate_cancel_agent_key": MagicMock(),
        "code_puppy.cli_entry.initialize_command_history_file": MagicMock(),
        "code_puppy.cli_entry.default_version_mismatch_behavior": MagicMock(),
        "code_puppy.interactive_runner.print_truecolor_warning": MagicMock(),
        "code_puppy.cli_runner.reset_unix_terminal": MagicMock(),
        "code_puppy.interactive_runner.reset_windows_terminal_ansi": MagicMock(),
        "code_puppy.interactive_runner.reset_windows_terminal_full": MagicMock(),
        "code_puppy.cli_entry.callbacks": MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[]),
        ),
        "code_puppy.cli_runner.plugins": MagicMock(),
        "code_puppy.config.load_api_keys_to_environment": MagicMock(),
    }


def _interactive_patches():
    return {
        "code_puppy.interactive_runner.print_truecolor_warning": MagicMock(),
        "code_puppy.interactive_runner.reset_windows_terminal_ansi": MagicMock(),
        "code_puppy.interactive_runner.reset_windows_terminal_full": MagicMock(),
        "code_puppy.interactive_runner.save_command_to_history": MagicMock(),
        "code_puppy.interactive_runner.finalize_autosave_session": MagicMock(
            return_value="session-1"
        ),
        "code_puppy.command_line.onboarding_wizard.should_show_onboarding": MagicMock(
            return_value=False
        ),
        "code_puppy.config.auto_save_session_if_enabled": MagicMock(),
    }


async def _run_interactive(
    renderer,
    patches_dict,
    input_fn,
    agent=None,
    initial_command=None,
    extra_patches=None,
):
    """Helper to run interactive_mode with patching."""
    if agent is None:
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

    with ExitStack() as stack:
        _apply_patches(stack, patches_dict)
        stack.enter_context(patch("builtins.input", _sync_input(input_fn)))
        stack.enter_context(
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            )
        )
        if extra_patches:
            _apply_patches(stack, extra_patches)

        from code_puppy.cli_runner import interactive_mode

        await interactive_mode(renderer, initial_command=initial_command)


def _scripted_input(*steps):
    """Build an async fake ``input()`` that yields the given literal steps in
    order, raising any step that is an exception (instance or class), then
    returning ``/exit`` for all further calls."""
    state = {"n": 0}

    async def fake_input(*a, **kw):
        idx = state["n"]
        state["n"] += 1
        if idx < len(steps):
            step = steps[idx]
            if isinstance(step, BaseException) or (
                isinstance(step, type) and issubclass(step, BaseException)
            ):
                raise step
            return step
        return "/exit"

    return fake_input
