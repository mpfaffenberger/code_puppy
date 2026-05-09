"""Security regression tests for lifecycle callback robustness (P1-02).

Covers:
- agent_run_start fires before agent_run_end
- Callback exception in agent_run_start does not prevent agent_run_end
- agent_run_end always fires even if agent_run_start callback raises
- Mixed async/sync callbacks in lifecycle hooks continue on error
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from code_puppy.callbacks import (
    _callbacks,
    clear_callbacks,
    on_agent_run_end,
    on_agent_run_start,
    register_callback,
)


@pytest.fixture(autouse=True)
def _isolate_callbacks():
    snapshot = {phase: list(cbs) for phase, cbs in _callbacks.items()}
    clear_callbacks()
    yield
    clear_callbacks()
    for phase, cbs in snapshot.items():
        _callbacks[phase].extend(cbs)


# ---------------------------------------------------------------------------
# agent_run_start / agent_run_end ordering
# ---------------------------------------------------------------------------


class TestLifecycleOrdering:
    """agent_run_start must fire before agent_run_end."""

    @pytest.mark.asyncio
    async def test_start_fires_before_end(self):
        order: list[str] = []

        async def on_start(agent_name, model_name, session_id=None):
            order.append("start")

        # agent_run_end passes 7 positional args: agent_name, model_name,
        # session_id, success, error, response_text, metadata
        async def on_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            order.append("end")

        register_callback("agent_run_start", on_start)
        register_callback("agent_run_end", on_end)

        await on_agent_run_start("test-agent", "gpt-4", "sess1")
        await on_agent_run_end("test-agent", "gpt-4", "sess1")

        assert order == ["start", "end"]

    @pytest.mark.asyncio
    async def test_start_and_end_receive_same_identity_args(self):
        captured_start: list[dict[str, Any]] = []
        captured_end: list[dict[str, Any]] = []

        async def on_start(agent_name, model_name, session_id=None):
            captured_start.append(
                {
                    "agent_name": agent_name,
                    "model_name": model_name,
                    "session_id": session_id,
                }
            )

        async def on_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            captured_end.append(
                {
                    "agent_name": agent_name,
                    "model_name": model_name,
                    "session_id": session_id,
                }
            )

        register_callback("agent_run_start", on_start)
        register_callback("agent_run_end", on_end)

        await on_agent_run_start("my-agent", "claude-3", "sess-abc")
        await on_agent_run_end("my-agent", "claude-3", "sess-abc")

        assert captured_start == captured_end


# ---------------------------------------------------------------------------
# Fault tolerance: one bad callback does not block others
# ---------------------------------------------------------------------------


class TestCallbackFaultTolerance:
    """A failing lifecycle callback must not prevent other callbacks."""

    @pytest.mark.asyncio
    async def test_failing_start_callback_does_not_block_others(self):
        results: list[str] = []

        async def bad_start(agent_name, model_name, session_id=None):
            raise RuntimeError("boom in start")

        async def good_start(agent_name, model_name, session_id=None):
            results.append("good_start")

        register_callback("agent_run_start", bad_start)
        register_callback("agent_run_start", good_start)

        with patch("code_puppy.callbacks.logger"):
            await on_agent_run_start("a", "m")

        assert "good_start" in results

    @pytest.mark.asyncio
    async def test_failing_end_callback_does_not_block_others(self):
        results: list[str] = []

        async def bad_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            raise RuntimeError("boom in end")

        async def good_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            results.append("good_end")

        register_callback("agent_run_end", bad_end)
        register_callback("agent_run_end", good_end)

        with patch("code_puppy.callbacks.logger"):
            await on_agent_run_end("a", "m")

        assert "good_end" in results

    @pytest.mark.asyncio
    async def test_failing_start_does_not_prevent_end(self):
        """Even if all start callbacks fail, end callbacks must still fire."""
        end_fired = False

        async def bad_start(agent_name, model_name, session_id=None):
            raise RuntimeError("always fails")

        async def on_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            nonlocal end_fired
            end_fired = True

        register_callback("agent_run_start", bad_start)
        register_callback("agent_run_end", on_end)

        with patch("code_puppy.callbacks.logger"):
            await on_agent_run_start("a", "m")
            await on_agent_run_end("a", "m")

        assert end_fired is True


# ---------------------------------------------------------------------------
# Mixed sync/async callbacks
# ---------------------------------------------------------------------------


class TestMixedSyncAsyncCallbacks:
    """Both sync and async lifecycle callbacks must execute correctly."""

    @pytest.mark.asyncio
    async def test_sync_start_callback_works(self):
        results: list[str] = []

        def sync_start(agent_name, model_name, session_id=None):
            results.append("sync_start")

        register_callback("agent_run_start", sync_start)

        await on_agent_run_start("a", "m")

        assert "sync_start" in results

    @pytest.mark.asyncio
    async def test_sync_end_callback_works(self):
        results: list[str] = []

        def sync_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            results.append("sync_end")

        register_callback("agent_run_end", sync_end)

        await on_agent_run_end("a", "m")

        assert "sync_end" in results

    @pytest.mark.asyncio
    async def test_mixed_sync_async_callbacks_both_fire(self):
        results: list[str] = []

        def sync_cb(agent_name, model_name, session_id=None):
            results.append("sync")

        async def async_cb(agent_name, model_name, session_id=None):
            results.append("async")

        register_callback("agent_run_start", sync_cb)
        register_callback("agent_run_start", async_cb)

        await on_agent_run_start("a", "m")

        assert "sync" in results
        assert "async" in results


# ---------------------------------------------------------------------------
# agent_run_end always fires regardless of success/failure
# ---------------------------------------------------------------------------


class TestEndAlwaysFires:
    """agent_run_end is the finally-block hook — it must always fire."""

    @pytest.mark.asyncio
    async def test_end_fires_with_success_true(self):
        results: list[dict[str, Any]] = []

        async def on_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            results.append({"success": success, "response_text": response_text})

        register_callback("agent_run_end", on_end)

        await on_agent_run_end("a", "m", "s1", True, None, "hello")

        assert len(results) == 1
        assert results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_end_fires_with_success_false(self):
        results: list[dict[str, Any]] = []

        async def on_end(
            agent_name,
            model_name,
            session_id=None,
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        ):
            results.append({"success": success, "error": error})

        register_callback("agent_run_end", on_end)

        err = RuntimeError("died")
        await on_agent_run_end("a", "m", "s1", False, err, None)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error"] is err
