"""Speculation telemetry stays in chrome, never in the transcript."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic_ai.messages import PartStartEvent, TextPart
from pydantic_ai_harness.code_mode import (
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCodeUpdateEvent,
)
from rich.console import Console

from code_puppy.messaging.speculation_stats import SpeculationStats


def claim(*, ready: bool = True, elapsed_ms: float = 1500.0):
    return SpeculativeCallClaimedEvent(
        tool_call_id="p",
        launch_id="launch",
        nested_tool_call_id="nested",
        wrapped_tool_name="read_file",
        ready_at_claim=ready,
        elapsed_ms=elapsed_ms,
    )


def miss():
    return SpeculativeCallMissedEvent(
        tool_call_id="p",
        sandbox_function="grep",
        wrapped_tool_name="grep",
        nested_tool_call_id="nested",
    )


def test_session_counts_survive_new_snippets():
    stats = SpeculationStats()
    assert stats.handle_event(claim())
    assert stats.handle_event(miss())
    assert stats.handle_event(
        SpeculativeCallEvictedEvent(
            tool_call_id="p",
            launch_id="unused",
            wrapped_tool_name="grep",
            state="ready",
        )
    )
    assert stats.handle_event(
        SpeculativeCodeUpdateEvent(
            tool_call_id="next",
            code="private code",
            closed_statements=1,
        )
    )
    assert stats.handle_event(claim(elapsed_ms=500.0))
    assert (stats.hits, stats.misses, stats.wasted, stats.saved_ms) == (2, 1, 1, 2000.0)
    text = stats.render()
    assert "hits 2" in text
    assert "misses 1" in text
    assert "wasted 1" in text
    assert "spec saved >= 2.0s" in text
    assert "eager saved >= 0.0s" in text
    assert "private code" not in text


def test_status_is_localizable():
    from code_puppy.i18n import pseudo, translate

    previous = translate.get_locale()
    try:
        translate.set_locale(pseudo.PSEUDO_LOCALE)
        text = SpeculationStats().render()
        assert text.startswith("⟦") and text.endswith("⟧")
    finally:
        translate.set_locale(previous)


def test_partial_claim_does_not_overstate_savings():
    stats = SpeculationStats()
    stats.handle_event(claim(ready=False, elapsed_ms=9000.0))
    assert stats.hits == 1
    assert stats.saved_ms == 0.0


def test_eager_totals_accumulate_separately():
    from code_puppy.capabilities.eager_timing import EagerExecutionCompletedEvent

    stats = SpeculationStats()
    for call_id in ("first", "second"):
        assert stats.handle_event(
            EagerExecutionCompletedEvent(
                tool_call_id=call_id,
                saved_ms=199.0,
            )
        )
    assert stats.eager_saved_ms == 398.0
    assert stats.saved_ms == 0.0
    assert stats.hits == 0
    assert "eager saved >= 0.3s" in stats.render()


def test_lower_bound_rounds_down():
    stats = SpeculationStats()
    stats.handle_event(claim(elapsed_ms=199.0))
    assert "spec saved >= 0.1s" in stats.render()


def test_non_speculation_event_falls_through():
    assert not SpeculationStats().handle_event(
        PartStartEvent(index=0, part=TextPart(content="hello"))
    )


@pytest.mark.parametrize(
    "agent_name, visible",
    [
        ("speculative-puppy", True),
        ("code-puppy", False),
        ("custom", False),
    ],
)
def test_status_is_agent_scoped(monkeypatch, agent_name, visible):
    from code_puppy.messaging.speculation_stats import get_speculation_status

    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: agent_name,
    )
    assert (get_speculation_status() is not None) is visible


def test_refresh_hides_row_after_switch(monkeypatch):
    from code_puppy.messaging.speculation_stats import refresh_speculation_status

    bar = Mock()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: "code-puppy",
    )
    refresh_speculation_status()
    bar.set_speculation_status.assert_called_once_with(None)


def test_agent_switch_changes_reserved_rows_without_headless_output(monkeypatch):
    from code_puppy.messaging.bottom_bar import BottomBar
    import code_puppy.messaging.speculation_stats as telemetry

    output = StringIO()
    bar = BottomBar(stream=output, get_size=lambda: (120, 24))
    stats = SpeculationStats(hits=3)
    selected = ["speculative-puppy"]
    monkeypatch.setattr(telemetry, "_stats", stats)
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: selected[0],
    )
    baseline = bar._total_reserved()
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline + 1
    selected[0] = "code-puppy"
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline
    selected[0] = "speculative-puppy"
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline + 1
    assert stats.hits == 3
    assert output.getvalue() == ""


def test_status_lookup_failure_is_harmless(monkeypatch):
    from code_puppy.messaging.speculation_stats import get_speculation_status

    def fail():
        raise RuntimeError("unavailable")

    monkeypatch.setattr("code_puppy.agents.agent_manager.get_current_agent_name", fail)
    assert get_speculation_status() is None


@pytest.mark.parametrize("subagent", [False, True])
async def test_stream_handler_updates_chrome_without_printing_code(
    monkeypatch, subagent
):
    import code_puppy.agents.event_stream_handler as handler
    import code_puppy.messaging.speculation_stats as telemetry

    stats = SpeculationStats()
    bar = Mock()
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    monkeypatch.setattr(telemetry, "_stats", stats)
    monkeypatch.setattr(handler, "is_subagent", lambda: subagent)
    monkeypatch.setattr(handler, "get_streaming_console", lambda: console)
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: "speculative-puppy",
    )

    async def updates():
        yield SpeculativeCodeUpdateEvent(
            tool_call_id="p",
            code="SECRET_SNIPPET",
            closed_statements=1,
        )
        yield claim()
        yield miss()

    await handler.event_stream_handler(SimpleNamespace(), updates())
    assert "SECRET_SNIPPET" not in output.getvalue()
    assert "run_code (streaming" not in output.getvalue()
    assert stats.hits == (0 if subagent else 1)
    if subagent:
        bar.set_speculation_status.assert_not_called()
    else:
        assert "hits 1" in bar.set_speculation_status.call_args.args[0]
        assert "misses 1" in bar.set_speculation_status.call_args.args[0]
