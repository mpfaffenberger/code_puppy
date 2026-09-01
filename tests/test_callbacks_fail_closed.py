"""A security callback that crashes must not read as approval.

`_trigger_callbacks` isolates errors by reporting a crashed callback as `None`.
The two phases carrying a `{"blocked": True}` protocol read `None` as "no
objection" — `command_runner.py` says so in a comment: *"Callbacks can return
None (allow) or a dict with blocked=True (reject)."*

So a plugin that guards tool or shell execution is indistinguishable, on crash,
from one that approved. `register_callback(..., fail_closed=True)` lets such a
callback declare that its failure means deny.

A second, independent path is covered here too: a plugin returning an explicit
`{"blocked": True}` with a non-string reason used to raise inside the caller's
broad `except Exception: pass`, and the tool ran anyway.
"""

import pytest

from code_puppy import callbacks
from code_puppy._pydantic_tool_helpers import _GENERIC_BLOCK_REASON, _block_reason


@pytest.fixture(autouse=True)
def _isolate_blocking_phases():
    for phase in callbacks.BLOCKING_PHASES:
        callbacks.clear_callbacks(phase)
    yield
    for phase in callbacks.BLOCKING_PHASES:
        callbacks.clear_callbacks(phase)


def _boom(*_args, **_kwargs):
    raise RuntimeError("detector exploded on /home/alice/secret-token-abc")


async def _async_boom(*_args, **_kwargs):
    raise RuntimeError("async detector exploded")


class TestDefaultBehaviorUnchanged:
    """Existing callbacks must keep the behavior they were written for."""

    async def test_a_crashed_callback_still_reports_none_by_default(self):
        callbacks.register_callback("pre_tool_call", _boom)

        assert await callbacks.on_pre_tool_call("some_tool", {}) == [None]

    def test_fail_closed_defaults_to_false(self):
        callbacks.register_callback("pre_tool_call", _boom)

        assert ("pre_tool_call", _boom) not in callbacks._fail_closed_callbacks


class TestFailClosedBlocksOnCrash:
    async def test_the_async_dispatcher_reports_a_block(self):
        callbacks.register_callback("pre_tool_call", _async_boom, fail_closed=True)

        results = await callbacks.on_pre_tool_call("dangerous_tool", {})

        assert len(results) == 1
        assert results[0]["blocked"] is True
        assert "_async_boom" in results[0]["error_message"]
        assert "RuntimeError" in results[0]["error_message"]

    async def test_a_sync_callback_on_an_async_phase_reports_a_block(self):
        callbacks.register_callback("run_shell_command", _boom, fail_closed=True)

        results = await callbacks.on_run_shell_command(None, "rm -rf /", None, 60)

        assert results[0]["blocked"] is True

    def test_the_sync_dispatcher_reports_a_block(self):
        callbacks.register_callback("run_shell_command", _boom, fail_closed=True)

        results = callbacks._trigger_callbacks_sync("run_shell_command", None, "cmd")

        assert results[0]["blocked"] is True

    async def test_the_message_carries_the_marker_the_renderer_strips_to(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)

        results = await callbacks.on_pre_tool_call("t", {})

        assert "[BLOCKED]" in results[0]["error_message"]

    async def test_the_exception_text_is_not_shown_to_the_user_or_model(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)

        results = await callbacks.on_pre_tool_call("t", {})

        rendered = results[0]["error_message"] + results[0]["reasoning"]
        assert "secret-token-abc" not in rendered
        assert "/home/alice" not in rendered

    async def test_one_crashed_guard_does_not_suppress_the_others(self):
        def observer(*_args, **_kwargs):
            return {"context_message": "still ran"}

        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)
        callbacks.register_callback("pre_tool_call", observer)

        results = await callbacks.on_pre_tool_call("t", {})

        assert results[0]["blocked"] is True
        assert results[1] == {"context_message": "still ran"}

    async def test_a_healthy_fail_closed_callback_is_untouched(self):
        def allows(*_args, **_kwargs):
            return None

        callbacks.register_callback("pre_tool_call", allows, fail_closed=True)

        assert await callbacks.on_pre_tool_call("t", {}) == [None]

    def test_raise_on_error_still_wins_in_the_sync_dispatcher(self):
        callbacks.register_callback("run_shell_command", _boom, fail_closed=True)

        with pytest.raises(RuntimeError):
            callbacks._trigger_callbacks_sync(
                "run_shell_command", None, "cmd", raise_on_error=True
            )

    async def test_an_unawaitable_async_callback_also_denies(self):
        """The sync trigger cannot await from a running loop; that is undecided,
        not unopposed."""
        callbacks.register_callback("run_shell_command", _async_boom, fail_closed=True)

        results = callbacks._trigger_callbacks_sync("run_shell_command", None, "cmd")

        assert results[0]["blocked"] is True


class TestPhaseRestriction:
    def test_rejected_on_a_phase_that_cannot_act_on_a_block(self):
        with pytest.raises(ValueError, match="only meaningful on phases"):
            callbacks.register_callback("startup", _boom, fail_closed=True)

    def test_the_rejected_registration_leaves_no_trace(self):
        with pytest.raises(ValueError):
            callbacks.register_callback("startup", _boom, fail_closed=True)

        assert _boom not in callbacks.get_callbacks("startup")


class TestPolicyIsPerPhaseNotPerCallable:
    async def test_one_phase_opting_in_does_not_bind_another(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)
        callbacks.register_callback("run_shell_command", _boom)

        blocking = await callbacks.on_pre_tool_call("t", {})
        permissive = await callbacks.on_run_shell_command(None, "ls", None, 60)

        assert blocking[0]["blocked"] is True
        assert permissive == [None]

    async def test_a_repeat_registration_can_tighten_the_policy(self):
        callbacks.register_callback("pre_tool_call", _boom)
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)

        results = await callbacks.on_pre_tool_call("t", {})

        assert len(results) == 1, "the duplicate must not register twice"
        assert results[0]["blocked"] is True


class TestRegistryHousekeeping:
    def test_unregister_drops_the_marking(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)
        callbacks.unregister_callback("pre_tool_call", _boom)

        assert ("pre_tool_call", _boom) not in callbacks._fail_closed_callbacks

    def test_unregister_leaves_another_phase_alone(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)
        callbacks.register_callback("run_shell_command", _boom, fail_closed=True)

        callbacks.unregister_callback("pre_tool_call", _boom)

        assert ("run_shell_command", _boom) in callbacks._fail_closed_callbacks

    def test_clearing_one_phase_drops_only_its_markings(self):
        callbacks.register_callback("pre_tool_call", _boom, fail_closed=True)
        callbacks.register_callback("run_shell_command", _boom, fail_closed=True)

        callbacks.clear_callbacks("pre_tool_call")

        assert ("pre_tool_call", _boom) not in callbacks._fail_closed_callbacks
        assert ("run_shell_command", _boom) in callbacks._fail_closed_callbacks

    def test_unregistering_an_unknown_callback_is_false(self):
        assert callbacks.unregister_callback("pre_tool_call", _boom) is False


class TestBlockReasonRendering:
    """An explicit deny must render as a deny whatever the plugin supplied."""

    def test_a_non_string_reason_still_renders_a_deny(self):
        assert _block_reason({"blocked": True, "reason": 123}) == "123"

    def test_a_reason_whose_str_raises_falls_back_to_generic_text(self):
        class Hostile:
            def __str__(self):
                raise RuntimeError("nope")

            def __bool__(self):
                return True

        assert (
            _block_reason({"blocked": True, "reason": Hostile()})
            == _GENERIC_BLOCK_REASON
        )

    def test_a_reason_whose_truthiness_raises_still_renders_a_deny(self):
        class Unbooleanable:
            def __bool__(self):
                raise RuntimeError("nope")

        assert (
            _block_reason({"blocked": True, "error_message": Unbooleanable()})
            == _GENERIC_BLOCK_REASON
        )

    def test_the_marker_still_trims_the_prefix(self):
        assert (
            _block_reason({"blocked": True, "reason": "noise [BLOCKED] the real one"})
            == "[BLOCKED] the real one"
        )

    def test_error_message_wins_over_reason(self):
        assert (
            _block_reason(
                {"blocked": True, "error_message": "from error_message", "reason": "x"}
            )
            == "from error_message"
        )

    def test_an_absent_or_blank_reason_gets_the_generic_text(self):
        assert _block_reason({"blocked": True}) == _GENERIC_BLOCK_REASON
        assert _block_reason({"blocked": True, "reason": " "}) == _GENERIC_BLOCK_REASON
