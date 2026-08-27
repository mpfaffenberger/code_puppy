"""Tests for the live speculative CodeMode panel (`messaging.speculation_panel`)."""

from __future__ import annotations

from rich.console import Console

from pydantic_ai_harness.code_mode import (
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
    return Console(record=True, width=100, force_terminal=False)


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

    def test_launch_settle_claim_reveal(self):
        panel = SpeculationPanel()
        console = _console()

        panel.handle_event(_update(CODE, 1), console)
        panel.handle_event(_launch(), console)
        panel.handle_event(
            SpeculativeCallSettledEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                outcome="ready",
                elapsed_ms=48.0,
            ),
            console,
        )
        panel.on_part_end()
        assert panel.active
        panel.handle_event(
            SpeculativeCallClaimedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_1",
                nested_tool_call_id="p1__1",
                wrapped_tool_name="grep",
                ready_at_claim=True,
                elapsed_ms=48.0,
            ),
            console,
        )
        panel.finalize()

        output = console.export_text()
        assert "run_code" in output
        assert "hit" in output
        assert "hits 1 (48ms hidden)" in output
        assert "grep" in output
        # The panel box has no left border: content flows flush-left.
        for line in output.splitlines():
            assert not line.startswith("\u2502")
            assert not line.startswith("\u256d")
            assert not line.startswith("\u2570")

    def test_miss_and_eviction_annotate_the_reveal(self):
        panel = SpeculationPanel()
        console = _console()

        panel.handle_event(_update(CODE, 2), console)
        panel.handle_event(_launch("p1__spec_9", line=2), console)
        panel.on_part_end()
        panel.handle_event(
            SpeculativeCallMissedEvent(
                tool_call_id="p1",
                sandbox_function="read_file",
                wrapped_tool_name="read_file",
                nested_tool_call_id="p1__2",
            ),
            console,
        )
        panel.handle_event(
            SpeculativeCallEvictedEvent(
                tool_call_id="p1",
                launch_id="p1__spec_9",
                wrapped_tool_name="grep",
                state="pending",
            ),
            console,
        )
        panel.finalize()

        output = console.export_text()
        assert "misses 1" in output
        assert "wasted 1" in output

    def test_outcomes_with_no_cycle_print_one_liners(self):
        panel = SpeculationPanel()
        console = _console()

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
            SpeculativeCallClaimedEvent(
                tool_call_id="p1",
                launch_id="unknown",
                nested_tool_call_id="p1__1",
                wrapped_tool_name="grep",
                ready_at_claim=True,
                elapsed_ms=10.0,
            ),
            console,
        )

        output = console.export_text()
        assert "speculation miss: grep ran cold" in output
        assert "speculation hit: grep ran 10ms" in output
        assert not panel.active

    def test_finalize_is_idempotent(self):
        panel = SpeculationPanel()
        panel.finalize()
        panel.handle_event(_update(CODE, 1), _console())
        panel.finalize()
        panel.finalize()
        assert not panel.active


class TestSingleton:
    def test_shared_instance(self):
        assert get_speculation_panel() is get_speculation_panel()


class TestHandlerRouting:
    async def test_stream_handler_routes_events_to_the_panel(self, monkeypatch):
        from types import SimpleNamespace

        import code_puppy.agents.event_stream_handler as esh

        handled = []

        class _SpyPanel:
            active = False

            def handle_event(self, event, console):
                if isinstance(event, SpeculativeCodeUpdateEvent):
                    handled.append(("event", event.code))
                    return True
                return False

            def on_part_end(self):
                handled.append(("part_end", None))

            def finalize(self):
                handled.append(("finalize", None))

        monkeypatch.setattr(
            "code_puppy.messaging.speculation_panel.get_speculation_panel",
            lambda: _SpyPanel(),
        )

        async def events():
            yield _update(CODE, 1)

        await esh.event_stream_handler(SimpleNamespace(), events())

        assert ("event", CODE) in handled
        assert ("finalize", None) in handled
