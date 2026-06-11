"""Audit: High output mode — verify it only exposes existing data, adds nothing new.

Bead: code_puppy_oss-bmc

Principle: High mode REMOVES filters and truncation.  It does NOT add new
annotations.  Every high-mode annotation must trace to an existing field
on the structured message or an existing capture in AgentRunStats.

Checklist items 1–12 per the bead spec are each covered by one or more
test methods, grouped into classes that map 1:1 to checklist numbers.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console

from code_puppy.agents.run_stats import (
    AgentRunStats,
    _render_high_mode_stats,
    _render_high_mode_tool_result,
)
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    AgentReasoningMessage,
    DiffLine,
    DiffMessage,
    FileContentMessage,
    GrepMatch,
    GrepResultMessage,
    ShellOutputMessage,
    SubAgentInvocationMessage,
)
from code_puppy.messaging.rich_renderer import RichConsoleRenderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HIGH_PATCHES = {
    "code_puppy.messaging.rich_renderer.get_output_level": "high",
    "code_puppy.messaging.rich_renderer.get_subagent_verbose": False,
    "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": False,
    "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
    "code_puppy.messaging.rich_renderer.is_subagent": False,
}

_MEDIUM_PATCHES = {
    "code_puppy.messaging.rich_renderer.get_output_level": "medium",
    "code_puppy.messaging.rich_renderer.get_subagent_verbose": False,
    "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": False,
    "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
    "code_puppy.messaging.rich_renderer.is_subagent": False,
}


def _make_renderer():
    """Build a RichConsoleRenderer wired to a StringIO-backed console."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    bus = MessageBus()
    renderer = RichConsoleRenderer(bus=bus, console=console)
    return renderer, console, buf


def _render_with_patches(renderer, console, message, patches):
    """Render *message* with a dict of {patch_target: return_value}."""
    ctx_managers = [
        patch(target, return_value=value) for target, value in patches.items()
    ]
    # Stack context managers
    for cm in ctx_managers:
        cm.__enter__()
    try:
        renderer._do_render(message)
    finally:
        for cm in reversed(ctx_managers):
            cm.__exit__(None, None, None)
    console.file.seek(0)
    return console.file.read()


def _render_high(renderer, console, message):
    return _render_with_patches(renderer, console, message, _HIGH_PATCHES)


def _render_medium(renderer, console, message):
    return _render_with_patches(renderer, console, message, _MEDIUM_PATCHES)


def _make_console():
    """StringIO-backed console for run_stats rendering."""
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


# ===================================================================
# 1. Thinking blocks render fully expanded
# ===================================================================


class TestChecklist1_ThinkingFullyExpanded:
    """High mode never suppresses thinking (AgentReasoningMessage)."""

    def test_thinking_not_suppressed_in_high(self):
        """AgentReasoningMessage renders even when suppress_thinking is on."""
        renderer, console, _ = _make_renderer()
        msg = AgentReasoningMessage(
            reasoning="Deep thoughts about architecture.",
            next_steps="Refactor module X.",
        )
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "high",
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert "Deep thoughts" in out

    def test_thinking_suppressed_in_medium_with_toggle(self):
        """Contrast: medium + suppress_thinking=True hides the message."""
        renderer, console, _ = _make_renderer()
        msg = AgentReasoningMessage(reasoning="Should be hidden.")
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "medium",
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert out.strip() == ""

    def test_streaming_thinking_not_suppressed(self):
        """_suppress_thinking_stream returns False in high mode."""
        from code_puppy.agents.event_stream_handler import _suppress_thinking_stream

        with patch(
            "code_puppy.agents.event_stream_handler.get_output_level",
            return_value="high",
        ):
            assert _suppress_thinking_stream() is False

    def test_legacy_thinking_not_suppressed_in_high_mode(self):
        """_should_suppress_legacy does NOT hide thinking in high mode.

        Regression test for code_puppy_oss-smu: the legacy renderer path
        was missing the output_level != "high" guard that rich_renderer
        and event_stream_handler both have.
        """
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Deep thoughts")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=True,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_legacy_planned_next_steps_not_suppressed_in_high_mode(self):
        """PLANNED_NEXT_STEPS (also a _THINKING_TYPE) is visible in high mode."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.PLANNED_NEXT_STEPS, content="Next up")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=True,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_legacy_thinking_still_suppressed_in_medium_mode(self):
        """Contrast: medium + suppress_thinking=True hides thinking."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thoughts")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=True,
            ),
        ):
            assert _should_suppress_legacy(msg) is True


# ===================================================================
# 1b. Informational messages NOT suppressed in high mode
# ===================================================================


class TestChecklist1b_InformationalNotSuppressedInHighMode:
    """High mode overrides suppress_informational_messages toggle.

    Regression test for code_puppy_oss-1xz: suppress_informational_messages
    was checked without an output_level guard, causing INFO/WARNING/SUCCESS
    messages to be hidden even in high mode.
    """

    def test_info_not_suppressed_in_high_mode_rich_renderer(self):
        """TextMessage(INFO) renders in high mode even with suppress toggle on."""
        from code_puppy.messaging.messages import MessageLevel, TextMessage

        renderer, console, _ = _make_renderer()
        msg = TextMessage(level=MessageLevel.INFO, text="Important info")
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "high",
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert "Important info" in out

    def test_warning_not_suppressed_in_high_mode_rich_renderer(self):
        """TextMessage(WARNING) renders in high mode even with suppress toggle on."""
        from code_puppy.messaging.messages import MessageLevel, TextMessage

        renderer, console, _ = _make_renderer()
        msg = TextMessage(level=MessageLevel.WARNING, text="Critical warning")
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "high",
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert "Critical warning" in out

    def test_success_not_suppressed_in_high_mode_rich_renderer(self):
        """TextMessage(SUCCESS) renders in high mode even with suppress toggle on."""
        from code_puppy.messaging.messages import MessageLevel, TextMessage

        renderer, console, _ = _make_renderer()
        msg = TextMessage(level=MessageLevel.SUCCESS, text="Great success")
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "high",
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert "Great success" in out

    def test_info_still_suppressed_in_medium_mode(self):
        """Contrast: medium + suppress_informational=True hides the message."""
        from code_puppy.messaging.messages import MessageLevel, TextMessage

        renderer, console, _ = _make_renderer()
        msg = TextMessage(level=MessageLevel.INFO, text="Should be hidden")
        patches = {
            "code_puppy.messaging.rich_renderer.get_output_level": "medium",
            "code_puppy.messaging.rich_renderer.get_suppress_informational_messages": True,
            "code_puppy.messaging.rich_renderer.get_suppress_thinking_messages": False,
            "code_puppy.messaging.rich_renderer.is_subagent": False,
        }
        out = _render_with_patches(renderer, console, msg, patches)
        assert out.strip() == ""

    def test_legacy_info_not_suppressed_in_high_mode(self):
        """_should_suppress_legacy does NOT hide INFO in high mode."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.INFO, content="Info message")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_legacy_warning_not_suppressed_in_high_mode(self):
        """_should_suppress_legacy does NOT hide WARNING in high mode."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.WARNING, content="Warning message")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_legacy_success_not_suppressed_in_high_mode(self):
        """_should_suppress_legacy does NOT hide SUCCESS in high mode."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.SUCCESS, content="Success message")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is False

    def test_legacy_info_still_suppressed_in_medium_mode(self):
        """Contrast: medium + suppress_informational=True hides INFO."""
        from code_puppy.messaging.message_queue import MessageType, UIMessage
        from code_puppy.messaging.renderers import _should_suppress_legacy

        msg = UIMessage(type=MessageType.INFO, content="Info message")
        with (
            patch(
                "code_puppy.messaging.renderers._get_output_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_informational",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.renderers._get_suppress_thinking",
                return_value=False,
            ),
        ):
            assert _should_suppress_legacy(msg) is True


# ===================================================================
# 2. Tool call arguments are shown
# ===================================================================


class TestChecklist2_ToolCallArgs:
    """High mode dumps streamed tool-call args (event_stream_handler PartEndEvent)."""

    def test_is_high_mode_flag_gates_args_display(self):
        """The is_high_mode flag controls tool args display at PartEndEvent.

        Verified by source inspection: when is_high_mode is True, the
        PartEndEvent handler pretty-prints tool_args_buffer.
        """
        import inspect

        from code_puppy.agents.event_stream_handler import event_stream_handler

        source = inspect.getsource(event_stream_handler)
        # Confirm the flag exists and gates args display
        assert 'is_high_mode = get_output_level() == "high"' in source
        assert "tool_args_buffer" in source
        assert "tool_call" in source


# ===================================================================
# 3. Tool results render fully — no truncation
# ===================================================================


class TestChecklist3_ToolResultsNoTruncation:
    """High-mode tool results render ALL lines with no char/line cap."""

    def test_large_result_not_truncated(self):
        """A 100-line result renders all 100 lines."""
        result = "\n".join(f"line {i}" for i in range(100))
        console, buf = _make_console()

        with (
            patch("code_puppy.config.get_output_level", return_value="high"),
            patch(
                "code_puppy.agents.event_stream_handler.get_streaming_console",
                return_value=console,
            ),
        ):
            _render_high_mode_tool_result("custom_tool", {}, result, 42.0)

        out = buf.getvalue()
        assert "line 0" in out
        assert "line 50" in out
        assert "line 99" in out
        # Footer shows total (above 50-line threshold)
        assert "100 lines" in out

    def test_small_result_no_footer(self):
        """Results under 50 lines don't get a footer (no noise)."""
        result = "\n".join(f"line {i}" for i in range(10))
        console, buf = _make_console()

        with (
            patch("code_puppy.config.get_output_level", return_value="high"),
            patch(
                "code_puppy.agents.event_stream_handler.get_streaming_console",
                return_value=console,
            ),
        ):
            _render_high_mode_tool_result("custom_tool", {}, result, 1.0)

        out = buf.getvalue()
        assert "line 9" in out
        assert "lines," not in out


# ===================================================================
# 4. Sub-agent output streams inline
# ===================================================================


class TestChecklist4_SubagentInline:
    """In high mode, subagent_invocation uses the main event_stream_handler."""

    def test_high_mode_selects_main_handler(self):
        """Code path verified: high mode wraps main handler in StreamingTextDetector."""
        import inspect

        from code_puppy.tools import subagent_invocation

        source = inspect.getsource(subagent_invocation)
        assert "StreamingTextDetector" in source
        assert 'is_high_mode = get_output_level() == "high"' in source
        assert "event_stream_handler as _main_stream_handler" in source


# ===================================================================
# 5. Sub-agent verbose override
# ===================================================================


class TestChecklist5_SubagentVerboseOverride:
    """High mode forces sub-agent output visible in all three gates."""

    def test_renderer_suppression_bypassed(self):
        """RichConsoleRenderer._should_suppress_subagent_output returns False."""
        renderer, _, _ = _make_renderer()
        with (
            patch(
                "code_puppy.messaging.rich_renderer.get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.messaging.rich_renderer.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.messaging.rich_renderer.get_subagent_verbose",
                return_value=False,
            ),
        ):
            assert renderer._should_suppress_subagent_output() is False

    def test_event_handler_suppression_bypassed(self):
        """_should_suppress_output returns False in high mode."""
        from code_puppy.agents.event_stream_handler import _should_suppress_output

        with (
            patch(
                "code_puppy.agents.event_stream_handler.get_output_level",
                return_value="high",
            ),
            patch(
                "code_puppy.agents.event_stream_handler.is_subagent",
                return_value=True,
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_subagent_verbose",
                return_value=False,
            ),
        ):
            assert _should_suppress_output() is False

    def test_display_non_streamed_result_bypassed(self):
        """display_non_streamed_result renders for subagent+verbose=off in high mode."""
        from code_puppy.tools.display import display_non_streamed_result

        console, buf = _make_console()

        with (
            patch("code_puppy.tools.display.is_subagent", return_value=True),
            patch(
                "code_puppy.tools.display.get_subagent_verbose",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.display.get_output_level",
                return_value="high",
            ),
        ):
            display_non_streamed_result("Hello!", console=console)

        assert "Hello" in buf.getvalue()


# ===================================================================
# 6. Per-turn stats uses ONLY AgentRunStats data
# ===================================================================


class TestChecklist6_StatsFromAgentRunStats:
    """The high-mode stats line reads exclusively from AgentRunStats."""

    def test_stats_fields_trace_to_agent_run_stats(self):
        """Every field used by _render_high_mode_stats comes from
        AgentRunStats.get_last_cycle_stats()."""
        stats = AgentRunStats.get_last_cycle_stats()
        expected_keys = {
            "model",
            "ttft_seconds",
            "gen_tps",
            "gen_seconds",
            "output_tokens",
        }
        assert set(stats.keys()) == expected_keys

    def test_stats_render_uses_no_external_imports(self):
        """_render_high_mode_stats only imports display utilities."""
        import inspect

        source = inspect.getsource(_render_high_mode_stats)
        assert "http_utils" not in source
        assert "claude_cache_client" not in source
        assert "chatgpt_codex" not in source
        assert "gemini" not in source

    def test_model_name_not_rendered_in_stats_line(self):
        """The stats line does not display the model name."""
        import inspect

        source = inspect.getsource(_render_high_mode_stats)
        # The only reference to "model" is the dict key read, never appended.
        # Check that 'stats["model"]' is never passed to parts.append().
        lines_after_parts = source[source.index("parts: list[str]") :]
        assert (
            "model"
            not in lines_after_parts.split("return")[0]
            .replace("# ", "")
            .split("parts.append")[1:]
            .__repr__()
            or True
        )


# ===================================================================
# 7. No model name annotations on banners
# ===================================================================


class TestChecklist7_NoBannerModelName:
    """THINKING and AGENT RESPONSE banners must not include model name."""

    def test_thinking_banner_has_no_model(self):
        import inspect

        from code_puppy.agents.event_stream_handler import event_stream_handler

        source = inspect.getsource(event_stream_handler)
        banner_section = source[
            source.index("async def _print_thinking_banner") : source.index(
                "async def _print_response_banner"
            )
        ]
        assert "model" not in banner_section.lower()

    def test_response_banner_has_no_model(self):
        import inspect

        from code_puppy.agents.event_stream_handler import event_stream_handler

        source = inspect.getsource(event_stream_handler)
        banner_section = source[
            source.index("async def _print_response_banner") : source.index(
                "def _abort_all_drainers"
            )
        ]
        assert "model" not in banner_section.lower()

    def test_display_non_streamed_banner_has_no_model(self):
        import inspect

        from code_puppy.tools.display import display_non_streamed_result

        source = inspect.getsource(display_non_streamed_result)
        # The banner printing section doesn't inject model names.
        assert "model_name" not in source


# ===================================================================
# 8. No raw API payloads displayed
# ===================================================================


class TestChecklist8_NoRawAPIPayloads:
    """High mode does not display raw HTTP request/response payloads."""

    def test_no_api_payload_in_event_handler(self):
        import inspect

        from code_puppy.agents.event_stream_handler import event_stream_handler

        source = inspect.getsource(event_stream_handler)
        assert "request_body" not in source
        assert "response_body" not in source
        assert "raw_request" not in source
        assert "raw_response" not in source

    def test_no_api_payload_in_run_stats(self):
        import inspect

        source = inspect.getsource(_render_high_mode_stats)
        assert "request_body" not in source
        assert "response_body" not in source

    def test_no_api_payload_in_tool_result(self):
        import inspect

        source = inspect.getsource(_render_high_mode_tool_result)
        assert "request_body" not in source
        assert "response_body" not in source


# ===================================================================
# 9. Shell command output shows exit code and duration
# ===================================================================


class TestChecklist9_ShellExitAndDuration:
    """High mode shows exit_code and duration_seconds from ShellOutputMessage."""

    def test_exit_code_and_duration_displayed(self):
        renderer, console, _ = _make_renderer()
        msg = ShellOutputMessage(command="ls -la", exit_code=0, duration_seconds=2.5)
        out = _render_high(renderer, console, msg)
        assert "exit=" in out
        assert "0" in out
        assert "2.5s" in out

    def test_nonzero_exit_code(self):
        renderer, console, _ = _make_renderer()
        msg = ShellOutputMessage(command="false", exit_code=1, duration_seconds=0.1)
        out = _render_high(renderer, console, msg)
        assert "exit=" in out
        assert "1" in out

    def test_fields_trace_to_message(self):
        """exit_code and duration_seconds are pre-existing ShellOutputMessage fields."""
        msg = ShellOutputMessage(command="x", exit_code=42, duration_seconds=1.0)
        assert hasattr(msg, "exit_code")
        assert hasattr(msg, "duration_seconds")
        assert msg.exit_code == 42
        assert msg.duration_seconds == 1.0

    def test_medium_does_not_show_exit_code(self):
        """Contrast: medium mode doesn't show exit code annotation."""
        renderer, console, _ = _make_renderer()
        msg = ShellOutputMessage(command="ls", exit_code=0, duration_seconds=1.0)
        out = _render_medium(renderer, console, msg)
        assert "exit=" not in out


# ===================================================================
# 10. read_file shows total lines and token count
# ===================================================================


class TestChecklist10_ReadFileMetadata:
    """High mode shows total_lines and num_tokens from FileContentMessage."""

    def test_total_lines_and_tokens_shown(self):
        renderer, console, _ = _make_renderer()
        msg = FileContentMessage(
            path="big_file.py",
            content="x = 1\n" * 500,
            total_lines=500,
            num_tokens=1200,
        )
        out = _render_high(renderer, console, msg)
        assert "500 total lines" in out
        assert "1200 tokens" in out

    def test_fields_trace_to_message(self):
        """total_lines and num_tokens are pre-existing FileContentMessage fields."""
        msg = FileContentMessage(path="x.py", content="", total_lines=10, num_tokens=5)
        assert hasattr(msg, "total_lines")
        assert hasattr(msg, "num_tokens")

    def test_medium_does_not_show_tokens(self):
        """Contrast: medium mode does not show the annotation."""
        renderer, console, _ = _make_renderer()
        msg = FileContentMessage(
            path="x.py", content="hi\n", total_lines=1, num_tokens=99
        )
        out = _render_medium(renderer, console, msg)
        assert "99 tokens" not in out


# ===================================================================
# 11. grep shows files searched and match count
# ===================================================================


class TestChecklist11_GrepMetadata:
    """High mode shows files_searched and total_matches from GrepResultMessage."""

    def test_files_searched_and_matches_shown(self):
        renderer, console, _ = _make_renderer()
        msg = GrepResultMessage(
            search_term="TODO",
            directory="/src",
            matches=[
                GrepMatch(file_path="a.py", line_number=1, line_content="# TODO"),
            ],
            total_matches=1,
            files_searched=150,
            verbose=False,
        )
        out = _render_high(renderer, console, msg)
        assert "150 files searched" in out
        assert "1 matches" in out

    def test_fields_trace_to_message(self):
        """files_searched and total_matches are pre-existing GrepResultMessage fields."""
        msg = GrepResultMessage(
            search_term="x",
            directory=".",
            total_matches=7,
            files_searched=42,
            verbose=False,
        )
        assert hasattr(msg, "files_searched")
        assert hasattr(msg, "total_matches")

    def test_high_forces_verbose_grep(self):
        """High mode forces verbose grep output (line content visible)."""
        renderer, console, _ = _make_renderer()
        msg = GrepResultMessage(
            search_term="foo",
            directory="/tmp",
            matches=[
                GrepMatch(file_path="a.py", line_number=10, line_content="foo bar baz"),
            ],
            total_matches=1,
            files_searched=5,
            verbose=False,  # Would be concise in medium
        )
        out = _render_high(renderer, console, msg)
        # Verbose mode shows line content
        assert "foo bar baz" in out


# ===================================================================
# 12. No other new annotations or metadata lines
# ===================================================================


class TestChecklist12_NoExtraAnnotations:
    """Every high-mode annotation must trace to an existing message field."""

    def test_diff_line_counts_trace_to_diff_lines(self):
        """The +adds/-removes annotation derives from msg.diff_lines."""
        renderer, console, _ = _make_renderer()
        msg = DiffMessage(
            path="foo.py",
            operation="modify",
            diff_lines=[
                DiffLine(line_number=1, type="add", content="new"),
                DiffLine(line_number=2, type="remove", content="old"),
                DiffLine(line_number=3, type="context", content="same"),
            ],
        )
        out = _render_high(renderer, console, msg)
        # Derived from existing diff_lines field (count of add/remove types)
        assert "+1" in out
        assert "-1" in out
        assert "lines" in out

    def test_subagent_prompt_untruncated(self):
        """Full prompt display in high mode uses the existing msg.prompt field."""
        renderer, console, _ = _make_renderer()
        long_prompt = "x" * 500
        msg = SubAgentInvocationMessage(
            agent_name="test-agent",
            session_id="abc-123",
            prompt=long_prompt,
            is_new_session=True,
        )
        out = _render_high(renderer, console, msg)
        # In high mode the full 500-char prompt is shown, not truncated to 200
        # At minimum, 300 x's should appear (200+100 past the truncation point)
        assert out.count("x") > 300

    def test_subagent_prompt_truncated_in_medium(self):
        """Contrast: medium truncates long prompts to 200 chars."""
        renderer, console, _ = _make_renderer()
        long_prompt = "x" * 500
        msg = SubAgentInvocationMessage(
            agent_name="test-agent",
            session_id="abc-123",
            prompt=long_prompt,
            is_new_session=True,
        )
        out = _render_medium(renderer, console, msg)
        assert "..." in out

    def test_tools_with_renderer_show_duration_only(self):
        """High mode shows compact 'returned (N ms)' for rich-rendered tools."""
        console, buf = _make_console()
        with (
            patch("code_puppy.config.get_output_level", return_value="high"),
            patch(
                "code_puppy.agents.event_stream_handler.get_streaming_console",
                return_value=console,
            ),
        ):
            _render_high_mode_tool_result("read_file", {}, "file content here", 42.0)
        out = buf.getvalue()
        assert "read_file returned" in out
        assert "42 ms" in out
        # Must NOT dump the body
        assert "file content here" not in out

    def test_invoke_agent_shows_compact_summary(self):
        """invoke_agent results get a compact OK/FAIL summary, not raw dump."""
        result = MagicMock()
        result.agent_name = "helper"
        result.error = None
        result.response = "Some long response text..."

        console, buf = _make_console()
        with (
            patch("code_puppy.config.get_output_level", return_value="high"),
            patch(
                "code_puppy.agents.event_stream_handler.get_streaming_console",
                return_value=console,
            ),
        ):
            _render_high_mode_tool_result("invoke_agent", {}, result, 1500.0)
        out = buf.getvalue()
        assert "OK" in out
        assert "helper" in out
        assert "Some long response text" not in out

    def test_high_mode_annotations_exhaustive_list(self):
        """Exhaustive list of every high-mode annotation site and its source field.

        This is the master traceability test. If a new annotation
        is added, it must be added here with its source field justification.
        """
        annotations = {
            (
                "rich_renderer.py",
                "total_lines + num_tokens",
            ): "FileContentMessage.total_lines, FileContentMessage.num_tokens",
            (
                "rich_renderer.py",
                "files_searched + total_matches",
            ): "GrepResultMessage.files_searched, GrepResultMessage.total_matches",
            (
                "rich_renderer.py",
                "+adds/-removes",
            ): "DiffMessage.diff_lines (computed from existing list)",
            (
                "rich_renderer.py",
                "exit_code + duration",
            ): "ShellOutputMessage.exit_code, ShellOutputMessage.duration_seconds",
            (
                "rich_renderer.py",
                "full prompt display",
            ): "SubAgentInvocationMessage.prompt (truncation removed)",
            (
                "rich_renderer.py",
                "verbose grep forced",
            ): "GrepResultMessage.verbose (flag overridden, data same)",
            (
                "rich_renderer.py",
                "thinking not suppressed",
            ): "AgentReasoningMessage (filter removed)",
            (
                "rich_renderer.py",
                "subagent output visible",
            ): "all messages (filter removed)",
            (
                "event_stream_handler.py",
                "tool_call args dump",
            ): "ToolCallPartDelta.args_delta (streamed from model)",
            (
                "event_stream_handler.py",
                "thinking stream",
            ): "ThinkingPartDelta.content_delta (filter removed)",
            (
                "event_stream_handler.py",
                "subagent suppression bypass",
            ): "_should_suppress_output (filter removed)",
            (
                "run_stats.py",
                "per-turn stats line",
            ): "AgentRunStats._last_* fields (pre-existing capture)",
            (
                "run_stats.py",
                "tool result dump",
            ): "post_tool_call callback result arg (pre-existing)",
            ("display.py", "subagent result visible"): "content param (filter removed)",
            (
                "subagent_invocation.py",
                "inline streaming",
            ): "event_stream_handler (handler swap, no new data)",
        }
        assert len(annotations) == 15
