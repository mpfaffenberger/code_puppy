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
    text = stats.render().plain
    assert "2 hits" in text
    assert "1 miss " in text
    assert "1 wasted" in text
    assert "saved \u2265 2.0s" in text
    assert "spec 2.0s \u00b7 eager 0.0s" in text
    assert "private code" not in text


def test_clear_starts_fresh_speculation_stats(monkeypatch):
    import code_puppy.messaging.speculation_stats as telemetry
    from code_puppy.command_line.session_commands import handle_clear_command

    agent = Mock()
    clipboard = Mock()
    clipboard.get_pending_count.return_value = 0
    stats = SpeculationStats(
        hits=3, misses=2, wasted=1, saved_ms=1200.0, eager_saved_ms=300.0
    )
    refresh = Mock()
    monkeypatch.setattr(telemetry, "_stats", stats)
    monkeypatch.setattr(telemetry, "refresh_speculation_status", refresh)
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent", lambda: agent
    )
    monkeypatch.setattr(
        "code_puppy.command_line.clipboard.get_clipboard_manager", lambda: clipboard
    )
    monkeypatch.setattr("code_puppy.config.finalize_autosave_session", lambda: "sid")
    monkeypatch.setattr(
        "code_puppy.agents._builder.reset_model_fallback_warnings", Mock()
    )
    monkeypatch.setattr("code_puppy.messaging.emit_warning", Mock())
    monkeypatch.setattr("code_puppy.messaging.emit_system_message", Mock())
    monkeypatch.setattr("code_puppy.messaging.emit_info", Mock())

    assert handle_clear_command("/clear") is True
    assert (
        stats.hits,
        stats.misses,
        stats.wasted,
        stats.saved_ms,
        stats.eager_saved_ms,
    ) == (0, 0, 0, 0.0, 0.0)
    refresh.assert_called_once_with()


def test_status_is_localizable():
    """Every word comes from the catalog; only spacing and separators do not."""
    from code_puppy.i18n import pseudo, translate

    previous = translate.get_locale()
    try:
        translate.set_locale(pseudo.PSEUDO_LOCALE)
        row = SpeculationStats().render()
        words = [
            row.plain[span.start : span.end].strip()
            for span in row.spans
            if row.plain[span.start : span.end].strip(" \u00b7")
        ]
        assert len(words) == 6
        for word in words:
            assert word.startswith("⟦") and word.endswith("⟧"), word
    finally:
        translate.set_locale(previous)


def test_styling_lights_up_only_non_zero_counts_and_savings():
    from code_puppy.capabilities.eager_timing import EagerExecutionCompletedEvent

    stats = SpeculationStats()
    styles = {span.style for span in stats.render().spans}
    assert "bold bright_green" not in styles
    assert "bold red" not in styles

    stats.handle_event(claim(elapsed_ms=1000.0))
    stats.handle_event(EagerExecutionCompletedEvent(tool_call_id="c", saved_ms=500.0))
    stats.handle_event(
        SpeculativeCallEvictedEvent(
            tool_call_id="p", launch_id="u", wrapped_tool_name="grep", state="ready"
        )
    )
    row = stats.render()
    by_text = {row.plain[s.start : s.end]: s.style for s in row.spans}
    assert by_text["1 hit"] == "bold bright_green"
    assert by_text["0 misses"] == "bright_black"
    assert by_text["1 wasted"] == "bold red"
    assert by_text["saved \u2265 1.5s"] == "bold bright_green"
    assert by_text["spec 1.0s \u00b7 eager 0.5s"] == "bright_black"


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
    assert "eager 0.3s" in stats.render().plain


def test_lower_bound_rounds_down():
    stats = SpeculationStats()
    stats.handle_event(claim(elapsed_ms=199.0))
    assert "spec 0.1s" in stats.render().plain


def test_non_speculation_event_falls_through():
    assert not SpeculationStats().handle_event(
        PartStartEvent(index=0, part=TextPart(content="hello"))
    )


_FLAG = "code_puppy.config.get_speculative_code_mode_enabled"


@pytest.mark.parametrize("enabled", [True, False])
def test_status_follows_the_config_flag_for_any_agent(monkeypatch, enabled):
    from code_puppy.messaging.speculation_stats import get_speculation_status

    monkeypatch.setattr(_FLAG, lambda: enabled)
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        lambda: "code-puppy",
    )
    assert (get_speculation_status() is not None) is enabled


def test_refresh_hides_row_when_flag_is_off(monkeypatch):
    from code_puppy.messaging.speculation_stats import refresh_speculation_status

    bar = Mock()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(_FLAG, lambda: False)
    refresh_speculation_status()
    bar.set_speculation_status.assert_called_once_with(None)


def test_toggle_changes_reserved_rows_without_headless_output(monkeypatch):
    from code_puppy.messaging.bottom_bar import BottomBar
    import code_puppy.messaging.speculation_stats as telemetry

    output = StringIO()
    bar = BottomBar(stream=output, get_size=lambda: (120, 24))
    stats = SpeculationStats(hits=3)
    flag = [True]
    monkeypatch.setattr(telemetry, "_stats", stats)
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(_FLAG, lambda: flag[0])
    baseline = bar._total_reserved()
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline + 1
    flag[0] = False
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline
    flag[0] = True
    telemetry.refresh_speculation_status()
    assert bar._total_reserved() == baseline + 1
    assert stats.hits == 3
    assert output.getvalue() == ""


def test_status_lookup_failure_is_harmless(monkeypatch):
    from code_puppy.messaging.speculation_stats import get_speculation_status

    def fail():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(_FLAG, fail)
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
    monkeypatch.setattr(_FLAG, lambda: True)

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
        row = bar.set_speculation_status.call_args.args[0].plain
        assert "1 hit " in row
        assert "1 miss " in row
