"""Tests for the append-only termflow speculation record.

The panel's contract is chronological and write-once: code lines print when
their statement closes and are never repainted, outcome lines append as their
events arrive, and the session line closes each cycle. Assertions read the
recorded console transcript, which doubles as proof there is no frame
repainting for a Live region to flicker over.
"""

from __future__ import annotations

from rich.console import Console

from pydantic_ai_harness.code_mode import (
    EagerPrefixCommittedEvent,
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
    SpeculativeCodeUpdateEvent,
)

from code_puppy.messaging.speculation_panel import (
    SpeculationPanel,
    _closed_boundary_line,
    get_speculation_panel,
)

CODE = 'a = await grep(search_string="Speculation")\nb = await read_file(file_path="x.py")\nprint(a, b'


def _console() -> Console:
    return Console(record=True, width=120, force_terminal=False)


def _update(code: str, closed: int) -> SpeculativeCodeUpdateEvent:
    return SpeculativeCodeUpdateEvent(
        tool_call_id="p1", code=code, closed_statements=closed
    )


def _launch(
    launch_id: str = "p1__spec_1", line: int = 1
) -> SpeculativeCallLaunchedEvent:
    return SpeculativeCallLaunchedEvent(
        tool_call_id="p1",
        launch_id=launch_id,
        sandbox_function="grep",
        wrapped_tool_name="grep",
        arguments={"search_string": "Speculation"},
        line_start=line,
        line_end=line,
        phase="streaming",
    )


class TestClosedBoundary:
    def test_no_closed_statements(self):
        assert _closed_boundary_line(CODE, 0) == 0

    def test_partial_close(self):
        assert _closed_boundary_line(CODE, 1) == 1
        assert _closed_boundary_line(CODE, 2) == 2

    def test_multiline_statement_spans_to_its_end(self):
        code = "x = [\n    1,\n]\ny = 2"
        assert _closed_boundary_line(code, 1) == 3

    def test_unparsable_code_returns_zero(self):
        assert _closed_boundary_line("def :", 1) == 0


class TestSpeculationPanelLifecycle:
    def test_update_opens_a_cycle(self):
        panel = SpeculationPanel()
        assert not panel.active

        assert panel.handle_event(_update(CODE, 1), _console())
        assert panel.active

        panel.finalize()
        assert not panel.active

    def test_non_speculation_events_fall_through(self):
        panel = SpeculationPanel()
        assert not panel.handle_event(object(), _console())
        assert not panel.active

    def test_finalize_when_idle_is_a_no_op(self):
        panel = SpeculationPanel()
        console = _console()
        panel.finalize()
        assert console.export_text() == ""

    def test_stream_end_finalizes_a_streaming_cycle(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_stream_end()
        assert not panel.active
        assert "speculation this session" in console.export_text()

    def test_stream_end_keeps_an_executing_cycle_alive(self):
        """Outcome events flush in a later handler invocation; the gap must not
        finalize the cycle out from under them."""
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_part_end()
        panel.on_stream_end()
        assert panel.active
        panel.finalize()


class TestAppendOnlyCode:
    def test_closed_lines_print_once_and_are_never_repainted(self):
        """The flicker cure is structural: a printed line is never touched again."""
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.handle_event(_update(CODE, 1), console)
        panel.handle_event(_update(CODE, 2), console)
        panel.finalize()
        text = console.export_text()
        assert text.count('a = await grep(search_string="Speculation")') == 1
        assert text.count('b = await read_file(file_path="x.py")') == 1

    def test_open_tail_stays_unprinted_until_part_end(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 2), console)
        assert "print(a, b" not in console.export_text()

        panel.on_part_end()
        text = console.export_text()
        assert "print(a, b" in text
        assert "executing..." in text

    def test_lines_carry_gutter_numbers(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 2), console)
        text = console.export_text()
        assert "1 │" in text
        assert "2 │" in text


class TestOutcomeLines:
    def test_launch_settle_claim(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.handle_event(_launch(), console)
        panel.handle_event(
            SpeculativeCallSettledEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                outcome="ready",
                elapsed_ms=113.0,
            ),
            console,
        )
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallClaimedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                nested_tool_call_id="p1__1",
                wrapped_tool_name="grep",
                ready_at_claim=True,
                elapsed_ms=600.0,
            ),
            console,
        )
        panel.finalize()
        text = console.export_text()
        assert '>> grep(search_string=\'Speculation\') launched at line 1' in text
        assert ".. grep ready after 113ms" in text
        assert "== hit grep (600ms hidden)" in text

    def test_partial_hit_notes_the_mid_flight_claim(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallClaimedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                nested_tool_call_id="p1__1",
                wrapped_tool_name="grep",
                ready_at_claim=False,
                elapsed_ms=250.0,
            ),
            console,
        )
        panel.finalize()
        assert "claimed mid-flight" in console.export_text()

    def test_miss_and_eviction(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallMissedEvent(
                tool_call_id="p1",
                sandbox_function="grep",
                wrapped_tool_name="grep",
                nested_tool_call_id="p1__1",
            ),
            console,
        )
        panel.handle_event(
            SpeculativeCallEvictedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_2",
                wrapped_tool_name="read_file",
                state="pending",
            ),
            console,
        )
        panel.finalize()
        text = console.export_text()
        assert "-- miss grep (ran cold, no matching launch)" in text
        assert "xx wasted read_file (pending)" in text

    def test_execution_prefetch_launch_is_labelled(self):
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        event = SpeculativeCallLaunchedEvent(
            tool_call_id="p1",
            launch_id="p1__spec_9",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            arguments={"search_string": "Speculation"},
            line_start=1,
            line_end=1,
            phase="execution",
        )
        panel.handle_event(event, console)
        assert "prefetched at execution" in console.export_text()


class TestSessionTotals:
    def test_totals_accumulate_across_cycles(self):
        panel = SpeculationPanel()

        first = _console()
        panel.handle_event(_update(CODE, 1), first)
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallClaimedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                nested_tool_call_id="p1__1",
                wrapped_tool_name="grep",
                ready_at_claim=True,
                elapsed_ms=600.0,
            ),
            first,
        )
        panel.finalize()
        assert "speculation this session: hits 1 (0.6s hidden)" in first.export_text()

        second = _console()
        panel.handle_event(_update(CODE, 1), second)
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallMissedEvent(
                tool_call_id="p2",
                sandbox_function="grep",
                wrapped_tool_name="grep",
                nested_tool_call_id="p2__1",
            ),
            second,
        )
        panel.finalize()
        text = second.export_text()
        assert "hits 1 (0.6s hidden)" in text
        assert "misses 1" in text


class TestEagerCommit:
    def test_eager_commit_prints_and_accumulates(self):
        panel = SpeculationPanel()

        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_part_end()
        handled = panel.handle_event(
            EagerPrefixCommittedEvent(
                tool_call_id="p1",
                statements=4,
                executed_ms=5200.0,
                waited_ms=200.0,
            ),
            console,
        )
        assert handled
        panel.finalize()
        text = console.export_text()
        assert "eager ran 4 stmts during generation (5.0s hidden)" in text
        assert "eager 5.0s hidden" in text

        second = _console()
        panel.handle_event(_update(CODE, 1), second)
        panel.on_part_end()
        panel.handle_event(
            EagerPrefixCommittedEvent(
                tool_call_id="p2",
                statements=1,
                executed_ms=1300.0,
                waited_ms=300.0,
            ),
            second,
        )
        panel.finalize()
        assert "eager 6.0s hidden" in second.export_text()

    def test_wait_dominated_commit_reports_zero_hidden(self):
        """A prefix the dispatch fully waited for hid nothing; never show negative time."""
        panel = SpeculationPanel()
        console = _console()
        panel.handle_event(_update(CODE, 1), console)
        panel.on_part_end()
        panel.handle_event(
            EagerPrefixCommittedEvent(
                tool_call_id="p3",
                statements=2,
                executed_ms=100.0,
                waited_ms=900.0,
            ),
            console,
        )
        panel.finalize()
        assert "eager ran 2 stmts during generation (0.0s hidden)" in console.export_text()


class TestSingleton:
    def test_get_speculation_panel_returns_one_instance(self):
        assert get_speculation_panel() is get_speculation_panel()
