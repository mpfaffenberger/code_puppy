"""Context chrome survives idle transitions and initializes before a run."""

from types import SimpleNamespace
from unittest.mock import Mock

from code_puppy.messaging.idle_status import _refresh_context_status


def test_refresh_uses_live_context_formatter(monkeypatch):
    from code_puppy.agents import _compaction
    from code_puppy import token_usage
    from code_puppy.messaging import spinner

    usage = SimpleNamespace(total_tokens=120, capacity=1000, proportion=0.12)
    monkeypatch.setattr(token_usage, "get_current_usage", lambda: usage)
    formatter = Mock(return_value="120/1k tokens (12%) | provider quota")
    writer = Mock()
    monkeypatch.setattr(spinner, "format_context_info", formatter)
    monkeypatch.setattr(_compaction, "update_spinner_context", writer)
    _refresh_context_status()
    formatter.assert_called_once_with(120, 1000, 0.12)
    writer.assert_called_once_with(formatter.return_value)


def test_unavailable_usage_does_not_erase_existing_status(monkeypatch):
    from code_puppy.agents import _compaction
    from code_puppy import token_usage

    monkeypatch.setattr(token_usage, "get_current_usage", lambda: None)
    writer = Mock()
    monkeypatch.setattr(_compaction, "update_spinner_context", writer)
    _refresh_context_status()
    writer.assert_not_called()


def test_refresh_returns_while_worker_is_blocked_and_deduplicates(monkeypatch):
    import threading
    from code_puppy.messaging import idle_status

    entered = threading.Event()
    release = threading.Event()
    done = threading.Event()
    calls = []

    def slow_refresh():
        calls.append(True)
        entered.set()
        release.wait(5)
        done.set()

    monkeypatch.setattr(idle_status, "_refresh_context_status", slow_refresh)
    try:
        idle_status.refresh_context_status()
        assert entered.wait(2)
        assert not done.is_set()
        idle_status.refresh_context_status()
        assert len(calls) == 1
    finally:
        release.set()
        assert done.wait(2)
        # Wait for the worker's finally block before restoring test patches.
        assert idle_status._refresh_lock.acquire(timeout=2)
        idle_status._refresh_lock.release()


def test_turn_end_preserves_context_and_streamed_total(monkeypatch):
    from code_puppy.agents.stream_status import get_stream_status
    from code_puppy.messaging import run_ui

    bar = Mock()
    monkeypatch.setattr(run_ui, "get_bottom_bar", lambda: bar)
    state = get_stream_status(bar, reset=True)
    state.characters = 250
    run_ui._clear_status_row()
    bar.set_status.assert_not_called()
    bar.set_tool_progress.assert_called_with("Streamed ~100 tokens | Idle")
