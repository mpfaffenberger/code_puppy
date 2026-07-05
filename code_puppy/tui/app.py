"""CooperApp: the Textual application shell for Code Puppy's new TUI.

Chat surface: a scrollback log plus a multiline prompt (TextArea, Enter
submits / Shift+Enter newlines).

Phase status
------------
* Phase 1 - full message-type rendering parity (capture bridge) -- DONE
* Phase 2a - real agent turns from the prompt + slash commands + exit -- DONE
* Phase 2 (remaining) - steering/cancel/pause, interactive modals,
  completions, shell passthrough, live token streaming
* Phase 3 - menus as ModalScreens
"""

from __future__ import annotations

import asyncio
from io import StringIO

from rich.console import Console, RenderableType
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, OptionList, Rule, Static, TextArea
from textual.widgets import Markdown as MarkdownWidget
from textual.widgets.markdown import MarkdownStream
from textual.widgets.option_list import Option

from code_puppy.messaging import (
    AgentResponseMessage,
    AnyMessage,
    ConfirmationRequest,
    ConfirmationResponse,
    MessageLevel,
    PauseAgentCommand,
    QuestionRequest,
    QuestionResponse,
    ResumeAgentCommand,
    SelectionRequest,
    SelectionResponse,
    SteerAgentCommand,
    TextMessage,
    UserInputRequest,
    UserInputResponse,
    get_message_bus,
)

from .capture import LegacyCaptureFormatter, RichCaptureFormatter
from .completion import compute_completions
from .renderer import TextualRenderer, message_to_renderable
from .screens.interactive import ConfirmModal, SelectionModal, TextInputModal
from .screens.question import QuestionModal

# Sentinel for "no before-target captured yet" in the render-batch coalescer
# (None is a valid before-target meaning "mount at the bottom").
_UNSET = object()


class CompletionList(OptionList):
    """Completion dropdown that never steals focus from the prompt."""

    can_focus = False


class PromptArea(TextArea):
    """Multiline prompt. Enter submits; Shift+Enter inserts a newline.

    When the completion dropdown is open, Up/Down navigate it, Tab accepts
    the highlighted item, and Escape dismisses it. Enter accepts a *partial*
    completion, but SUBMITS when the highlighted item is already fully typed
    (e.g. a complete ``/model``) -- so bare menu commands open their modal
    instead of getting stuck in argument completion.
    """

    def _on_key(self, event: events.Key) -> None:
        # Vim mode (TUI-only) intercepts keys when no completion popup is open.
        # In INSERT mode the engine only consumes Escape, so typing/completion
        # behave exactly as before. Enter & Ctrl-combos always fall through.
        if (
            getattr(self.app, "vim_enabled", False)
            and not self.app.completion_visible()
        ):
            from .vim_adapter import feed_key

            if feed_key(self, self.app.vim_state, event):
                self.app.update_vim_indicator()
                return

        if self.app.completion_visible():
            if event.key in ("down", "up", "tab", "enter", "escape"):
                event.prevent_default()
                event.stop()
                if event.key == "down":
                    self.app.completion_move(1)
                elif event.key == "up":
                    self.app.completion_move(-1)
                elif event.key == "tab":
                    self.app.accept_completion()
                elif event.key == "enter":
                    if self.app.completion_is_exact():
                        self.app.hide_completions()
                        self.app.submit_prompt(self.text)
                        self.text = ""
                        self.app.reset_vim_mode()
                    elif self.app.accept_completion(submit_if_terminal=True):
                        # Accepted a terminal command and ran it in one go.
                        self.text = ""
                    # else: accepted a partial/argument completion; stay put
                    # so the user can keep typing the next token.
                else:
                    self.app.hide_completions()
                return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.app.submit_prompt(self.text)
            self.text = ""
            self.app.reset_vim_mode()
            return

        # Shift+Enter / Ctrl+J insert a literal newline. Textual's TextArea
        # only inserts "\n" for the bare "enter" key (which we hijack for
        # submit above) -- shift+enter and ctrl+j are neither "printable" nor
        # in its insert table, so without this branch they'd do nothing.
        # ("newline" is Textual's alias for ctrl+j on some terminals.)
        if event.key in ("shift+enter", "ctrl+j", "newline"):
            event.prevent_default()
            event.stop()
            start, end = self.selection
            self.replace("\n", start, end, maintain_selection_offset=False)

    def get_line(self, line_index: int):
        """Italic-cyan the attachment placeholders, matching the classic UI.

        ``get_line`` is Textual's documented hook for layering extra styling
        onto TextArea content; we stylize the [png image]-style placeholders
        here so they read as friendly chips instead of plain text.
        """
        from rich.style import Style

        from .attachments import placeholder_spans

        line = super().get_line(line_index)
        placeholders = [p for p, _ in getattr(self.app, "_attachment_placeholders", [])]
        if placeholders:
            style = Style(color="cyan", italic=True)
            for start, end in placeholder_spans(line.plain, placeholders):
                line.stylize(style, start, end)
        return line


# ---------------------------------------------------------------------------
# Status-bar helpers: convert prompt_toolkit FormattedText → Rich Text
#
# The TUI status bar calls the *same* get_prompt_with_active_model() that the
# classic prompt uses (including all monkey-patches: context_indicator,
# custom statusline command, …).  All we need is a style-string translation
# layer so the prompt_toolkit tuples render correctly in Textual/Rich.
# ---------------------------------------------------------------------------

_ANSI_TO_RICH: dict[str, str] = {
    "ansiblack": "black",
    "ansired": "red",
    "ansigreen": "green",
    "ansiyellow": "yellow",
    "ansiblue": "blue",
    "ansimagenta": "magenta",
    "ansicyan": "cyan",
    "ansiwhite": "white",
    "ansibrightblack": "bright_black",
    "ansibrightred": "bright_red",
    "ansibrightgreen": "bright_green",
    "ansibrightyellow": "bright_yellow",
    "ansibrightblue": "bright_blue",
    "ansibrightmagenta": "bright_magenta",
    "ansibrightcyan": "bright_cyan",
    "ansibrightwhite": "bright_white",
}

# None → skip the fragment entirely (we don't want ">>> " in the status bar).
_PT_CLASS_TO_RICH: dict[str, str | None] = {
    "puppy": "",
    "agent": "bold",
    "model": "bold cyan",
    "cwd": "",
    "context-indicator": "",
    "arrow": None,
}


def _pt_style_to_rich(style_str: str) -> str | None:
    """Translate a prompt_toolkit style string to a Rich style string.

    Returns ``None`` to signal the fragment should be dropped (e.g. the
    ``class:arrow`` / ``>>> `` that belongs in the classic prompt but not
    in the TUI status bar).
    """
    if style_str.startswith("class:"):
        cls = style_str[6:]
        return _PT_CLASS_TO_RICH.get(cls, "")

    parts: list[str] = []
    for token in style_str.split():
        if token in ("bold", "italic", "underline", "reverse"):
            parts.append(token)
        elif token.startswith("fg:"):
            c = token[3:]
            parts.append(_ANSI_TO_RICH.get(c, c))
        elif token.startswith("bg:"):
            c = token[3:]
            parts.append(f"on {_ANSI_TO_RICH.get(c, c)}")
        elif token.startswith("#"):
            parts.append(token)
        # ignore "nobold", "noreverse", etc.
    return " ".join(parts) if parts else ""


class CooperApp(App):
    """Code Puppy's Textual UI (Phase 0 scaffold)."""

    CSS = """
    Screen { background: $surface; }
    #log {
        border: none;
        padding: 0 1;
        background: $surface;
        height: 1fr;
        /* Always reserve the scrollbar gutter so the content width is stable
           whether or not the scrollbar is showing -- otherwise captured Rich
           output (panels, wide lines) renders too wide and clips on the right
           the moment a scrollbar appears. */
        scrollbar-gutter: stable;
    }
    /* Each log entry: no extra vertical gap so output reads as one flow. */
    #log > Static, #log > Markdown {
        margin: 0;
        padding: 0;
        background: transparent;
        height: auto;
    }
    #prompt {
        height: 5;
        border: none;
        border-top: solid $accent;
        border-bottom: solid $accent;
        /* Inset left/right by 1 to line up with the response area's
           `padding: 0 1`. */
        margin: 1 1 0 1;
        /* Vim sub-mode indicator lives on the bottom border, left-aligned. */
        border-subtitle-color: $accent;
        border-subtitle-align: left;
    }
    #completions {
        display: none;
        height: auto;
        max-height: 8;
        border: round $accent;
        background: $surface;
        margin-top: 1;
    }
    #completions.visible { display: block; }
    #subagent-panel {
        display: none;
        height: auto;
        max-height: 5;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    #subagent-panel.visible { display: block; }
    #spinner {
        display: none;
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    #spinner.visible { display: block; }
    /* Footer row: native key hints (left) + status line (fills, right-aligned)
       + a command-palette hint (far right). Blend everything into $surface and
       make the Footer's layered key backgrounds transparent. */
    #footerbar { height: 1; background: $surface; }
    #footerbar Footer { dock: none; width: auto; background: transparent; }
    Footer FooterKey,
    Footer FooterKey .footer-key--key,
    Footer FooterKey .footer-key--description { background: transparent; }
    /* Status line (model / agent / branch / context%), mirroring classic. */
    #statusbar {
        width: 1fr;
        height: 1;
        padding: 0 1;
        background: transparent;
        color: $text-muted;
        text-align: right;
    }
    #palettehint {
        width: auto;
        height: 1;
        padding: 0 1;
        background: transparent;
        color: $text-muted;
    }
    /* Accent rule above each user PROMPT turn (same color as the input box
       borders) so a new turn stands out in the scrollback. */
    /* Dimmed accent timestamp, sitting directly above the rule. */
    #log > Static.prompt-timestamp {
        color: $accent;
        text-opacity: 55%;
        margin-top: 1;
        height: 1;
    }
    #log > Rule.prompt-rule {
        color: $accent;
        /* Left edge flush with the PROMPT banner (x=1, the #log padding);
           the banner widget has no extra left margin, so neither do we. No
           top margin -- the timestamp above provides the inter-turn gap. */
        margin: 0 1 0 0;
        height: 1;
    }
    /* Streamed thinking content: dim prose, slight indent, gap below. */
    #log > Static.thinking-content {
        color: $text-muted;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "quit"),
        ("escape", "cancel_turn", "cancel"),
        ("ctrl+t", "steer", "steer"),
        ("ctrl+g", "queue", "queue"),
        ("ctrl+r", "history", "history"),
        ("ctrl+x", "interrupt_shell", "kill shell"),
    ]
    TITLE = "Code Puppy"
    SUB_TITLE = "ready"

    def __init__(self, initial_command: str | None = None) -> None:
        super().__init__()
        self._initial_command = initial_command
        self._renderer = TextualRenderer(self)
        # Phase 1 capture bridge: reuse the classic Rich formatting verbatim.
        self._formatter = RichCaptureFormatter()
        # Bridge the legacy global MessageQueue (emit_info / QueueConsole) into
        # the TUI - the classic renderers that drain it aren't started here.
        self._legacy_formatter = LegacyCaptureFormatter()
        # Hidden console so the agent's live token streaming never writes to
        # the real terminal (which would corrupt the Textual screen). The
        # final response is rendered from AgentResponseMessage instead.
        self._quiet_console = Console(file=StringIO(), force_terminal=False)
        self._busy = False
        self._agent_worker = None
        self._completion = None
        # Single ordered render pipeline. Bus messages (tool output), legacy-
        # queue messages, and streamed response deltas all flow through ONE
        # FIFO queue drained by ONE consumer, so output renders in true
        # emission order (e.g. GREP output before the response that follows
        # it) instead of racing across channels.
        self._render_q: asyncio.Queue = asyncio.Queue()
        # Inline live markdown streaming for the in-progress response.
        self._md_stream: MarkdownStream | None = None
        self._md_widget: MarkdownWidget | None = None
        # The streamed response's banner widget. While set, tool/bus output
        # mounts ABOVE it so the streaming response stays pinned to the bottom
        # and tool output always lands above it (deterministic ordering, no
        # cross-channel race).
        self._response_anchor: Static | None = None
        self._streamed_this_turn = False
        # Lossless accumulation of the streamed response text + the last part
        # index. The live MarkdownStream renders incrementally and can drop
        # characters at text-part/tool boundaries; at stream stop we rebuild
        # the committed widget from this buffer, which never loses anything.
        self._stream_text = ""
        self._stream_last_index = None
        # --- Render batching (Phase 5 perf) -------------------------------
        # Mounting one widget per bus message is superlinear in the
        # VerticalScroll child count (a `cat bigfile` firehose mounts
        # thousands of widgets and stutters). Instead we BUFFER renderables
        # and flush them on a short timer, coalescing consecutive Text output
        # into a single Static -- one mount per burst, not one per line.
        self._pending: list[tuple[RenderableType, object]] = []
        self._flush_handle = None
        # Streamed response deltas are likewise batched: MarkdownStream
        # re-renders the WHOLE accumulated doc on every write, so writing once
        # per token is O(n^2) over a long response. We coalesce deltas and
        # write them in fewer, larger chunks.
        self._pending_deltas: list[str] = []
        self._delta_handle = None
        # Streaming thinking state. ThinkingPart deltas are batched the same
        # way as text deltas and rendered into a dim Static widget. Cleared by
        # _stop_thinking_stream; indices track which parts are thinking so
        # deltas route correctly without inspecting delta_type again.
        self._thinking_part_indices: set[int] = set()
        self._thinking_widget: Static | None = None
        self._thinking_text_acc: str = ""
        self._thinking_pending_deltas: list[str] = []
        self._thinking_delta_handle = None
        # Animated thinking spinner (mirrors the classic ConsoleSpinner).
        self._spinner_timer = None
        self._spinner_frame = 0
        # Ordered (placeholder, real_path) pairs for dragged attachments whose
        # paths were swapped for friendly [png image] placeholders in the
        # prompt. Expanded back to real paths just before the agent turn.
        self._attachment_placeholders: list[tuple[str, str]] = []
        # Reentrancy guard: our own buffer rewrite posts another Changed.
        self._transforming_attachments = False
        # Track the prompt of the current (or most-recently-run) turn so
        # action_cancel_turn can pass it to on_interactive_turn_cancel.
        self._current_turn_prompt: str = ""

    def register_attachment_placeholders(self, mapping: list[tuple[str, str]]) -> None:
        """Record placeholder->path pairs from a dragged-in attachment paste."""
        self._attachment_placeholders.extend(mapping)

    def _expand_attachment_placeholders(self, text: str) -> str:
        """Swap friendly placeholders back to real paths and reset the map."""
        from .attachments import expand_placeholders

        expanded = expand_placeholders(text, self._attachment_placeholders)
        self._attachment_placeholders = []
        return expanded

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            # Single unified scrollback: every piece of output (captured
            # renderables, markdown responses, the live streaming response) is
            # a child widget mounted in document order. The live response is a
            # Markdown widget streamed in place, so it reads as one continuous
            # flow -- no separate streaming region.
            yield VerticalScroll(id="log")
            # Live sub-agent swarm panel: one row per tracked sub-agent,
            # shown while any sub-agent is running (driven by the
            # subagent_panel_lines_changed hook, registered in on_mount).
            yield Static(id="subagent-panel")
            # Animated '<puppy> is thinking... (puppy) Tokens: ...' status,
            # shown only while a turn is running (mirrors the classic spinner).
            yield Static(id="spinner")
            yield CompletionList(id="completions")
            yield PromptArea(id="prompt", soft_wrap=True)
        with Horizontal(id="footerbar"):
            yield Footer(show_command_palette=False)
            yield Static("[dim]\u2502[/dim] [b]^p[/b] palette", id="palettehint")
            yield Static(id="statusbar")

    def on_mount(self) -> None:
        # Importing command_handler registers all built-in slash commands so
        # completion is populated from the first keystroke (not just after the
        # first /command is dispatched).
        import code_puppy.command_line.command_handler  # noqa: F401

        # Restore the persisted vim-mode preference (TUI-only feature).
        self._init_vim_mode()

        # The classic logo print (cli_runner.run) is skipped in Textual mode
        # because stdout is wiped when the app grabs the screen. Render it here
        # instead, using the shared builder so both UIs stay in sync.
        from code_puppy.startup_banner import build_logo_renderable

        logo = build_logo_renderable()
        if logo is not None:
            self._append_log(logo)

        # Keep the scrollback pinned to the bottom as new output arrives
        # (released automatically when the user scrolls up to read history).
        self.query_one("#log", VerticalScroll).anchor()

        # Register our event loop on the bus so sync callers running on worker
        # threads (e.g. the ask_user_question tool) can drive async request/
        # response round-trips against the UI.
        get_message_bus().set_event_loop(asyncio.get_running_loop())

        # Start the single render consumer BEFORE the renderer thread (which
        # immediately enqueues buffered startup messages). Everything renders
        # through this one FIFO so ordering is deterministic.
        self.run_worker(self._render_loop(), group="render", exclusive=False)

        self._renderer.start()

        # Status bar: render once now, then refresh on a timer (model/agent/
        # branch/context% can change between and during turns).
        self._refresh_statusbar()
        self.set_interval(3.0, self._refresh_statusbar)

        # Bridge the legacy queue: register a listener (the queue's daemon
        # thread invokes it), then drain anything buffered before we attached.
        from code_puppy.messaging.message_queue import (
            get_buffered_startup_messages,
            get_global_queue,
        )

        queue = get_global_queue()
        queue.add_listener(self._on_legacy_message)
        for buffered in get_buffered_startup_messages():
            self.handle_legacy_message(buffered)
        queue.clear_startup_buffer()

        # The help block lives in cli_runner.interactive_mode, which the TUI
        # bypasses -- emit the Textual-appropriate variant here so users get
        # the same orientation (with correct keybindings).
        from code_puppy.startup_banner import emit_interactive_help

        emit_interactive_help(textual=True)

        # The "ready" line goes LAST, through the same legacy FIFO queue as the
        # help above, so it deterministically renders after it. (Emitting it on
        # the bus instead raced ahead of the legacy messages across threads.)
        # The green check normally added by the bus SUCCESS path is baked in.
        from code_puppy.messaging.message_queue import emit_success

        emit_success(
            "\u2713 cooper is ready. Type a task and press Enter. Ctrl+Q to quit."
        )

        # Live token streaming: append response deltas to the transient preview.
        from code_puppy.callbacks import register_callback

        register_callback("stream_event", self._on_stream_event)
        register_callback(
            "subagent_panel_lines_changed", self._on_subagent_panel_lines_changed
        )

        self.query_one("#prompt", PromptArea).focus()
        if self._initial_command:
            self.submit_prompt(self._initial_command)
        else:
            # First-run onboarding (the classic flow lives in interactive_mode,
            # which the TUI bypasses). Safe Textual slide deck instead.
            try:
                from code_puppy.command_line.onboarding_wizard import (
                    should_show_onboarding,
                )

                if should_show_onboarding():
                    from .menus import open_onboarding

                    open_onboarding(self)
            except Exception:
                pass

    def _log_width(self) -> int | None:
        """Usable content width of #log, EXCLUDING the scrollbar gutter.

        ``content_size`` still counts the reserved scrollbar gutter, so
        captured Rich output rendered at that width clips on the right once a
        scrollbar appears. ``scrollable_content_region`` is the true drawable
        width (gutter reserved via ``scrollbar-gutter: stable``).
        """
        log = self.query_one("#log", VerticalScroll)
        return (
            log.scrollable_content_region.width
            or log.content_size.width
            or log.size.width
        ) or None

    # Batching cadence: ~20fps. Long enough to coalesce a firehose burst into
    # one mount, short enough that output still feels live/streaming.
    _FLUSH_INTERVAL = 0.05

    def _append_log(self, renderable: RenderableType, *, before=None) -> None:
        """Queue a renderable to be mounted into the scrollback (batched).

        Renderables are buffered and flushed on a short timer so a firehose of
        small messages mounts as one coalesced Static instead of thousands of
        widgets (which is superlinear in the VerticalScroll child count).
        Defaults to the bottom; pass ``before`` (a mounted widget) to insert
        above it -- used to keep tool output above an actively streaming
        response.
        """
        self._pending.append((renderable, before))
        self._schedule_flush()

    def _append_output(self, renderable: RenderableType) -> None:
        """Mount agent/tool output, keeping it ABOVE a streaming response.

        If a response is streaming inline, its banner is the anchor and output
        mounts just above it; otherwise output appends at the bottom.
        """
        self._append_log(renderable, before=self._response_anchor)

    def _schedule_flush(self) -> None:
        if self._flush_handle is None:
            self._flush_handle = self.set_timer(
                self._FLUSH_INTERVAL, self._flush_output
            )

    def _flush_output(self) -> None:
        """Mount all buffered renderables, coalescing consecutive Text output.

        Consecutive ``Text`` renderables sharing the same ``before`` target are
        joined into a SINGLE Static (newline-separated, matching the stacked
        block layout) so a firehose costs one mount instead of N. Non-Text
        renderables (panels/tables/markdown) mount individually to preserve
        their structure.
        """
        self._flush_handle = None
        if not self._pending:
            return
        items, self._pending = self._pending, []
        try:
            log = self.query_one("#log", VerticalScroll)
        except Exception:
            return
        staged: list[tuple[Static, object]] = []
        run: Text | None = None
        run_before: object = _UNSET

        def _emit_run() -> None:
            nonlocal run, run_before
            if run is not None:
                staged.append((self._make_static(run), run_before))
                run = None
                run_before = _UNSET

        for renderable, before in items:
            if isinstance(renderable, Text):
                if run is not None and before is run_before:
                    run.append("\n")
                    run.append_text(renderable)
                else:
                    _emit_run()
                    run = renderable.copy()
                    run_before = before
            else:
                _emit_run()
                staged.append((self._make_static(renderable), before))
        _emit_run()

        for entry, before in staged:
            if before is not None:
                log.mount(entry, before=before)
            else:
                log.mount(entry)

    @staticmethod
    def _make_static(renderable: RenderableType) -> Static:
        entry = Static(renderable, markup=False)
        # Stash the source renderable for log_text() (Static hides it behind a
        # name-mangled attribute we'd rather not reach into).
        entry._cp_renderable = renderable
        return entry

    def _mount_now(self, widget, *, before=None) -> None:
        """Flush pending output, then mount a live widget directly in order.

        Used for non-buffered widgets (streamed MarkdownWidget, prompt-echo
        rules) so they land AFTER everything queued before them rather than
        racing ahead of the batch.
        """
        self._flush_output()
        log = self.query_one("#log", VerticalScroll)
        if before is not None:
            log.mount(widget, before=before)
        else:
            log.mount(widget)

    def write_renderable(self, renderable: RenderableType) -> None:
        """Mount a renderable into the scrollback."""
        self._append_log(renderable)

    def log_text(self) -> str:
        """Concatenate the plain text of every scrollback entry (for tests)."""
        # Flush buffered output so introspection sees the full scrollback even
        # if the batch timer hasn't fired yet.
        self._flush_output()
        parts: list[str] = []
        for child in self.query_one("#log", VerticalScroll).children:
            if isinstance(child, MarkdownWidget):
                parts.append(child.source or "")
            elif isinstance(child, Static):
                r = getattr(child, "_cp_renderable", None)
                if r is None:
                    continue
                parts.append(r.plain if hasattr(r, "plain") else str(r))
        return "\n".join(parts)

    def handle_bus_message(self, message: AnyMessage) -> None:
        """Render a bus message into the scrollback (runs on the UI thread).

        Uses the Phase 1 capture bridge for full parity with the classic UI.
        Falls back to a minimal renderable only if capture yields nothing for
        a plain TextMessage (defensive; shouldn't normally happen).
        """
        width = self._log_width()

        # The agent's final response. When it streamed live (the common case)
        # the inline markdown widget already holds it -- just finalize. For a
        # non-streaming model, mount it now (at the bottom).
        if isinstance(message, AgentResponseMessage):
            if not self._streamed_this_turn:
                self._append_agent_response_banner()
                if message.is_markdown:
                    # Flush the buffered banner first so the widget lands AFTER
                    # it (a direct mount would otherwise jump ahead of the batch).
                    self._mount_now(MarkdownWidget(message.content))
                else:
                    self._append_log(Text(message.content))
            self._finalize_stream()
            return

        # Interactive requests: the agent is awaiting a response. Show a modal
        # and ALWAYS reply (even on cancel) so the agent never hangs.
        if isinstance(
            message,
            (
                UserInputRequest,
                ConfirmationRequest,
                SelectionRequest,
                QuestionRequest,
            ),
        ):
            self._show_request_modal(message)
            return

        renderable = self._formatter.format(message, width=width)
        if renderable is None:
            # Capture suppressed/skipped this message. Only surface a fallback
            # for plain text so nothing user-facing is silently lost.
            if isinstance(message, TextMessage):
                renderable = message_to_renderable(message)
            else:
                return
        # Keep tool output above an actively streaming response.
        self._append_output(renderable)

    def _echo_prompt(self, text: str) -> None:
        """Echo the user's submitted prompt into the scrollback.

        In classic mode the typed prompt is part of the terminal scrollback; in
        the TUI the prompt lives in a separate widget, so without this a
        scrolled-back response has no visible question above it.
        """
        # Mirror the tool-call banner style ([bold white on <color>] LABEL )
        # so the user's turn is just as prominent as the agent's tool activity.
        from code_puppy.config import get_banner_color

        # A dimmed accent timestamp + horizontal rule above the banner (both in
        # the input-box border color) make each new turn pop in the scrollback.
        from datetime import datetime

        # Flush any buffered output first so this turn header mounts AFTER the
        # previous turn's tail (the four parts below are direct, ordered mounts).
        self._flush_output()
        log = self.query_one("#log", VerticalScroll)
        stamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stamp = Static(stamp_text, classes="prompt-timestamp")
        stamp._cp_renderable = stamp_text
        log.mount(stamp)

        rule = Rule(line_style="solid")
        rule.add_class("prompt-rule")
        rule._cp_renderable = ""  # ignored by log_text()
        log.mount(rule)

        color = get_banner_color("prompt")
        line = Text()
        line.append(" PROMPT ", style=f"bold white on {color}")
        line.append(" ")
        line.append(text, style="bold")
        log.mount(self._make_static(line))

        # Closing rule below the prompt (same accent color + margins) so the
        # turn header reads as a framed block.
        bottom_rule = Rule(line_style="solid")
        bottom_rule.add_class("prompt-rule")
        bottom_rule._cp_renderable = ""
        log.mount(bottom_rule)

    def _agent_response_banner_text(self) -> Text:
        """Build the 'AGENT RESPONSE' banner renderable (classic colors)."""
        from code_puppy.config import get_banner_color

        color = get_banner_color("agent_response")
        line = Text()
        line.append("\n")  # blank line to separate from prior tool output
        line.append(" AGENT RESPONSE ", style=f"bold white on {color}")
        return line

    def _append_agent_response_banner(self) -> None:
        """Mount the 'AGENT RESPONSE' banner at the bottom (non-streamed path)."""
        self._append_log(self._agent_response_banner_text())

    def submit_prompt(self, text: str) -> None:
        """Dispatch a submitted prompt: exit, slash command, or agent turn."""
        text = text.strip()
        if not text or self._busy:
            return
        original = text

        lowered = text.lower()

        # Persist the submission to the shared prompt-history file so /history
        # (Ctrl+R) reflects TUI prompts too. The classic UI gets this for free
        # via prompt_toolkit's FileHistory auto-append; the Textual prompt has
        # no such hook, so mirror it here. Skip bare exit/quit noise. Reuses
        # HistoryStore so the on-disk format matches what the picker reads.
        if lowered not in ("exit", "quit", "/exit", "/quit"):
            try:
                from code_puppy.messaging.editor_history import HistoryStore

                HistoryStore().append(original)
            except Exception:
                pass

        if lowered in ("exit", "quit", "/exit", "/quit"):
            self.exit()
            return
        if lowered == "clear":
            text = "/clear"

        if text.startswith("!"):
            from code_puppy.command_line.shell_passthrough import (
                extract_command,
                is_shell_passthrough,
            )

            if is_shell_passthrough(text):
                self._run_shell_passthrough(extract_command(text))
            else:
                get_message_bus().emit(
                    TextMessage(
                        level=MessageLevel.WARNING,
                        text="Empty command. Usage: !<command> (e.g., !ls -la)",
                    )
                )
            return

        if text.startswith("/"):
            handled = self._dispatch_command(text)
            if handled is True:
                return
            if isinstance(handled, str):
                text = handled  # command returned a prompt to run
            # handled is False -> unknown command, fall through to the agent

        self._echo_prompt(original)
        # Expand any [png image] placeholders back to real paths so attachment
        # parsing can load the bytes (the echo above keeps the friendly form).
        text = self._expand_attachment_placeholders(text)
        self._agent_worker = self._run_agent_turn(text)

    def _show_request_modal(self, message: AnyMessage) -> None:
        """Push the right modal for an interactive request and reply via the bus.

        Every dismissal path provides a response so the agent's awaited Future
        always completes.
        """
        bus = get_message_bus()
        prompt_id = message.prompt_id

        if isinstance(message, UserInputRequest):

            def _on_text(value):
                bus.provide_response(
                    UserInputResponse(prompt_id=prompt_id, value=value or "")
                )

            self.push_screen(TextInputModal(message), _on_text)

        elif isinstance(message, ConfirmationRequest):

            def _on_confirm(result):
                confirmed, feedback = result if result else (False, None)
                bus.provide_response(
                    ConfirmationResponse(
                        prompt_id=prompt_id,
                        confirmed=confirmed,
                        feedback=feedback,
                    )
                )

            self.push_screen(ConfirmModal(message), _on_confirm)

        elif isinstance(message, SelectionRequest):

            def _on_select(result):
                index, value = result if result else (-1, "")
                bus.provide_response(
                    SelectionResponse(
                        prompt_id=prompt_id,
                        selected_index=index,
                        selected_value=value,
                    )
                )

            self.push_screen(SelectionModal(message), _on_select)

        elif isinstance(message, QuestionRequest):

            def _on_questions(result):
                answers, cancelled, timed_out = result if result else ([], True, False)
                bus.provide_response(
                    QuestionResponse(
                        prompt_id=prompt_id,
                        answers=answers,
                        cancelled=cancelled,
                        timed_out=timed_out,
                    )
                )

            self.push_screen(QuestionModal(message), _on_questions)

    # --- Vim mode (TUI-only) ---------------------------------------------
    def _init_vim_mode(self) -> None:
        """Set up vim state and restore the persisted on/off preference."""
        from code_puppy.config import get_value

        from .vim import VimState

        enabled = str(get_value("vim_mode") or "").lower() in ("1", "true", "yes", "on")
        self.vim_enabled = enabled
        self.vim_state = VimState()
        self.update_vim_indicator()

    def toggle_vim_mode(self) -> bool:
        """Flip vim mode on/off, persist it, and return the new state."""
        from code_puppy.config import set_config_value

        from .vim import VimState

        self.vim_enabled = not getattr(self, "vim_enabled", False)
        self.vim_state = VimState()
        try:
            self.query_one("#prompt", PromptArea)._vim_anchor = None
        except Exception:
            pass
        set_config_value("vim_mode", "true" if self.vim_enabled else "false")
        self.update_vim_indicator()
        return self.vim_enabled

    def reset_vim_mode(self) -> None:
        """Return to INSERT mode for a fresh prompt (no-op when disabled)."""
        if not getattr(self, "vim_enabled", False):
            return
        from .vim import VimState

        self.vim_state = VimState()
        try:
            self.query_one("#prompt", PromptArea)._vim_anchor = None
        except Exception:
            pass
        self.update_vim_indicator()

    def update_vim_indicator(self) -> None:
        """Show the current vim sub-mode in the prompt's border title."""
        try:
            prompt = self.query_one("#prompt", PromptArea)
        except Exception:
            return
        if not getattr(self, "vim_enabled", False):
            prompt.border_subtitle = ""
            return
        from .vim import INSERT, NORMAL, VISUAL

        labels = {INSERT: "INSERT", NORMAL: "NORMAL", VISUAL: "VISUAL"}
        prompt.border_subtitle = f" {labels.get(self.vim_state.mode, 'INSERT')} "

    def _dispatch_command(self, command: str):
        """Route a /command through the shared command handler.

        Returns True if fully handled, a str to run as a prompt, or False if
        the command was not recognized.
        """
        from code_puppy.command_line.command_handler import handle_command
        from code_puppy.messaging import emit_error

        from .menus import get_menu_opener, open_autosave_picker

        # Bare menu commands (e.g. /model) open a Textual modal instead of the
        # classic prompt_toolkit menu. With args (e.g. /model gpt-x) we fall
        # through to the normal handler so direct-set still works. Plugin
        # screens (register_screen hook) are resolved here too.
        parts = command[1:].split()
        name = parts[0].lower() if parts else ""

        # /vim toggles the TUI-only vim editing mode for the prompt box.
        if name == "vim" and len(parts) == 1:
            enabled = self.toggle_vim_mode()
            get_message_bus().emit(
                TextMessage(
                    level=MessageLevel.INFO,
                    text=(
                        "Vim mode ON -- ESC for NORMAL, i to insert."
                        if enabled
                        else "Vim mode OFF."
                    ),
                )
            )
            return True

        opener = get_menu_opener(name)
        if opener is not None and len(parts) == 1:
            opener(self)
            return True

        # /mcp install [id] is interactive (classic uses prompt_toolkit +
        # blocking prompts). Route it to the Textual install flow. Other /mcp
        # subcommands only emit via the bus, so they fall through and work.
        if name == "mcp" and len(parts) >= 2 and parts[1].lower() == "install":
            from .mcp_install import open_mcp_install

            open_mcp_install(self, parts[2] if len(parts) >= 3 else None)
            return True

        try:
            result = handle_command(command)
        except Exception as e:  # never let a command crash the UI
            emit_error(f"Command error: {e}")
            return True
        if result == "__AUTOSAVE_LOAD__":
            open_autosave_picker(self)
            return True
        return result

    @work(exclusive=True, group="agent")
    async def _run_agent_turn(self, task: str) -> None:
        """Run one agent turn on a Textual worker, keeping the UI responsive.

        After each run fires ``on_interactive_turn_end`` (mirrors classic's
        interactive loop in cli_runner.py). If any plugin returns a
        continuation dict ``{"prompt": ..., "clear_context": ..., "delay": ...}``
        the turn re-runs with the new prompt — this is what makes /goal and
        /wiggum retry loops work in the TUI.
        """
        import asyncio

        from code_puppy.agents import get_current_agent
        from code_puppy.callbacks import (
            on_interactive_turn_cancel,
            on_interactive_turn_end,
        )
        from code_puppy.cli_runner import run_prompt_with_attachments
        from code_puppy.config import auto_save_session_if_enabled
        from code_puppy.messaging import emit_error

        # Close any leftover stream segment and reset the per-turn flag. The
        # render loop (started in on_mount) mounts deltas + keeps ordering.
        self._finalize_stream()
        self._streamed_this_turn = False
        self._stream_text = ""
        self._stream_last_index = None
        self._set_busy(True)

        continuation_prompt = task
        continuation_result = None
        continuation_success = False
        continuation_error: "BaseException | None" = None
        first_run = True
        self._current_turn_prompt = task

        try:
            while True:
                agent = get_current_agent()

                if not first_run:
                    # Reset stream state for the continuation run.
                    self._finalize_stream()
                    self._streamed_this_turn = False
                    self._stream_text = ""
                    self._stream_last_index = None
                first_run = False

                try:
                    # display_console -> set_streaming_console (route raw stream
                    # output into a black-hole console; the TUI renders via its
                    # own capture bridge). use_run_ui=False: the TUI owns the
                    # screen, so skip the classic bottom-bar run UI. (Main
                    # renamed these from the old spinner_console/use_spinner
                    # during the bottom-bar rewrite.)
                    result, _agent_task = await run_prompt_with_attachments(
                        agent,
                        continuation_prompt,
                        display_console=self._quiet_console,
                        use_run_ui=False,
                    )
                    if result is None:
                        # Cancelled internally (e.g. empty prompt).
                        await on_interactive_turn_cancel(
                            continuation_prompt, reason="cancellation"
                        )
                        return

                    if hasattr(result, "all_messages"):
                        agent.set_message_history(list(result.all_messages()))
                    get_message_bus().emit(
                        AgentResponseMessage(content=result.output, is_markdown=True)
                    )
                    auto_save_session_if_enabled()
                    continuation_result = result
                    continuation_success = True
                    continuation_error = None

                except asyncio.CancelledError:
                    # Worker was hard-cancelled (Escape / action_cancel_turn).
                    # action_cancel_turn fires the cancel hook itself so we
                    # don't double-fire here; just propagate so Textual can
                    # clean up the worker.
                    raise

                except Exception as e:
                    emit_error(f"Agent error: {e}")
                    continuation_result = None
                    continuation_success = False
                    continuation_error = e
                    auto_save_session_if_enabled()

                # --- continuation loop (mirrors cli_runner.py ~line 1171) ---
                continuation_requests = await on_interactive_turn_end(
                    agent,
                    continuation_prompt,
                    continuation_result,
                    success=continuation_success,
                    error=continuation_error,
                )
                continuation = next(
                    (r for r in continuation_requests if isinstance(r, dict)),
                    None,
                )
                if not continuation:
                    break

                next_prompt = str(continuation.get("prompt") or "").strip()
                if not next_prompt:
                    break

                if continuation.get("clear_context", False):
                    try:
                        from code_puppy.config import finalize_autosave_session

                        new_session_id = finalize_autosave_session()
                        agent.clear_message_history()
                        from code_puppy.messaging import emit_system_message

                        emit_system_message(
                            f"Context cleared. Session rotated to: {new_session_id}"
                        )
                    except Exception:
                        agent.clear_message_history()

                delay = float(continuation.get("delay") or 0)
                if delay > 0:
                    await asyncio.sleep(delay)

                continuation_prompt = next_prompt
                self._current_turn_prompt = next_prompt
                continuation_result = None
                continuation_success = False
                continuation_error = None

        finally:
            self._set_busy(False)
            # Drain the next queued prompt only on clean completion — not on
            # cancel (result=None / CancelledError) or unhandled exception.
            if continuation_success:
                self._maybe_run_next_queued()

    def action_cancel_turn(self) -> None:
        """Hard-cancel the running agent turn (Escape).

        Fires ``on_interactive_turn_cancel`` before cancelling the worker so
        plugins like wiggum can clean up their state.
        """
        if not self._busy or self._agent_worker is None:
            return
        import asyncio

        from code_puppy.callbacks import on_interactive_turn_cancel

        # Fire the cancel hook asynchronously (non-blocking best-effort).
        # We can't await here (sync method), so schedule it on the event loop.
        prompt = self._current_turn_prompt
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(on_interactive_turn_cancel(prompt, reason="cancellation"))
        except Exception:
            pass
        try:
            self._agent_worker.cancel()
        except Exception:
            pass
        self._finalize_stream()
        get_message_bus().emit(
            TextMessage(level=MessageLevel.WARNING, text="Turn cancelled.")
        )

    def action_interrupt_shell(self) -> None:
        """Kill any in-flight shell commands (Ctrl+X).

        The TUI-native equivalent of the classic raw-stdin Ctrl+X listener.
        In Textual mode the agent runtime no longer spawns that listener (it
        raced Textual for stdin), so this binding owns the shortcut directly.
        """
        from code_puppy.tools.command_runner import kill_all_running_shell_processes

        killed = kill_all_running_shell_processes()
        if killed:
            get_message_bus().emit(
                TextMessage(
                    level=MessageLevel.WARNING,
                    text=f"Interrupted {killed} running shell command(s).",
                )
            )

    def action_steer(self) -> None:
        """Pause the running agent and inject a steering message (Ctrl+T)."""
        if not self._busy:
            get_message_bus().emit(
                TextMessage(
                    level=MessageLevel.INFO,
                    text="Nothing running to steer. Steering works during a turn.",
                )
            )
            return

        bus = get_message_bus()
        # Pause at the next safe boundary while the user composes a steer.
        bus.provide_response(PauseAgentCommand(reason="steer"))

        def _on_steer(text):
            if text and text.strip():
                bus.provide_response(SteerAgentCommand(text=text.strip(), mode="now"))
            # Always resume, whether or not a steer was provided.
            bus.provide_response(ResumeAgentCommand())

        request = UserInputRequest(
            prompt_id="__steer__", prompt_text="Steer cooper (mid-turn):"
        )
        self.push_screen(TextInputModal(request), _on_steer)

    def action_queue(self) -> None:
        """Open the prompt-queue manager (Ctrl+G)."""
        from .menus import get_menu_opener

        opener = get_menu_opener("queue")
        if opener is not None:
            opener(self)

    def action_history(self) -> None:
        """Open the prompt-history picker (Ctrl+R, classic reverse-search)."""
        from .menus import open_history

        open_history(self)

    @work(thread=True, group="shell")
    def _run_shell_passthrough(self, command: str) -> None:
        """Run a !shell command captured (not inheriting stdio) and emit results.

        The classic passthrough inherits the real stdout, which would corrupt
        the Textual screen; here we capture output and route it through the bus.
        """
        import os
        import subprocess
        import time

        bus = get_message_bus()
        bus.emit(TextMessage(level=MessageLevel.INFO, text=f"$ {command}"))
        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=os.getcwd(),
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.monotonic() - start
            out = (result.stdout or "").rstrip()
            err = (result.stderr or "").rstrip()
            if out:
                bus.emit(TextMessage(level=MessageLevel.INFO, text=out))
            if err:
                bus.emit(TextMessage(level=MessageLevel.WARNING, text=err))
            if result.returncode == 0:
                bus.emit(
                    TextMessage(
                        level=MessageLevel.SUCCESS, text=f"Done ({elapsed:.1f}s)"
                    )
                )
            else:
                bus.emit(
                    TextMessage(
                        level=MessageLevel.ERROR,
                        text=f"Exit code {result.returncode} ({elapsed:.1f}s)",
                    )
                )
        except subprocess.TimeoutExpired:
            bus.emit(
                TextMessage(level=MessageLevel.ERROR, text="Command timed out (120s).")
            )
        except Exception as e:
            bus.emit(TextMessage(level=MessageLevel.ERROR, text=f"Shell error: {e}"))

    # ------------------------------------------------------------------ #
    # Live token streaming (Phase 2 polish)                                #
    # ------------------------------------------------------------------ #
    def _on_stream_event(self, event_type, event_data, agent_session_id=None):
        """Stream response text and thinking deltas live into the log.

        Runs on the app's event loop (the stream callback fires there).
        Thinking parts stream into a dim Static widget; text parts stream into
        a MarkdownWidget. Tool deltas are ignored. All items are queued onto
        the single render pipeline so they're serialized with bus/legacy output
        (one mounter, no concurrent-mount races).
        """
        try:
            # Prompt banner for an auto-injected queued steer. Fired
            # synchronously (same event-loop iteration) from _runtime._do_run
            # so it lands BEFORE the next turn's stream deltas.
            if event_type == "prompt_echo":
                text = event_data.get("text", "")
                if text:
                    # Close any open stream from the previous turn so the
                    # PROMPT banner mounts after that response, not inside it.
                    self._finalize_stream()
                    self.enqueue_render(("prompt_echo", text))
                return

            index = event_data.get("index")

            # ---- Thinking parts (handled before the text-only path) ------
            if (
                event_type == "part_start"
                and event_data.get("part_type") == "ThinkingPart"
            ):
                from code_puppy.config import (
                    get_output_level,
                    get_suppress_thinking_messages,
                )

                if get_output_level() != "high" and get_suppress_thinking_messages():
                    return
                self._thinking_part_indices.add(index)
                self.enqueue_render(("thinking_start",))
                # ThinkingPart.content may already carry opening text.
                part = event_data.get("part")
                initial = getattr(part, "content", None)
                if initial:
                    self.enqueue_render(("thinking_delta", initial))
                return

            if (
                event_type == "part_delta"
                and event_data.get("delta_type") == "ThinkingPartDelta"
            ):
                if index in self._thinking_part_indices:
                    delta = event_data.get("delta")
                    chunk = getattr(delta, "content_delta", None)
                    if chunk:
                        self.enqueue_render(("thinking_delta", chunk))
                return

            if event_type == "part_end" and index in self._thinking_part_indices:
                self._thinking_part_indices.discard(index)
                self.enqueue_render(("thinking_end",))
                return

            # ---- Text parts (original path) ------------------------------
            content = None
            if event_type == "part_start":
                # A new TextPart may already carry its opening text in the
                # start event (it is NOT repeated as a delta) -- capture it or
                # we drop the first characters of the part. Mirrors the classic
                # handler, which seeds its line buffer from part.content.
                if event_data.get("part_type") == "TextPart":
                    part = event_data.get("part")
                    content = getattr(part, "content", None)
            elif event_type == "part_delta":
                if event_data.get("delta_type") != "TextPartDelta":
                    return
                delta = event_data.get("delta")
                content = getattr(delta, "content_delta", None)
            if not content:
                return
            self._streamed_this_turn = True
            # The model emits a fresh text part after each tool call; separate
            # consecutive parts with a blank line so they don't run together.
            if (
                self._stream_last_index is not None
                and index is not None
                and index != self._stream_last_index
            ):
                content = "\n\n" + content
            self._stream_last_index = index
            # Accumulate losslessly (plain concat on the event loop -- no race);
            # the committed widget is rebuilt from this at stop.
            self._stream_text += content
            self.enqueue_render(("delta", content))
        except Exception:
            # Streaming is best-effort polish; never break a turn over it.
            pass

    def enqueue_render(self, item: tuple) -> None:
        """Append an item to the single ordered render pipeline.

        Items: ``("bus", msg)``, ``("legacy", msg)``, ``("delta", content)``,
        ``("end",)``. Must run on the UI loop; cross-thread callers go via
        ``call_from_thread``.
        """
        try:
            self._render_q.put_nowait(item)
        except Exception:
            pass

    async def _render_loop(self) -> None:
        """Drain the render queue in FIFO order -- the ONE place output mounts.

        A single consumer serializes bus messages, legacy-queue messages, and
        streamed deltas, so nothing mounts concurrently. Tool output mounts
        ABOVE the streaming response (via its anchor), keeping the response
        pinned to the bottom regardless of which channel fires first.
        """
        while True:
            try:
                item = await self._render_q.get()
                kind = item[0]
                if kind == "bus":
                    self.handle_bus_message(item[1])
                elif kind == "legacy":
                    self.handle_legacy_message(item[1])
                elif kind == "delta":
                    await self._stream_delta(item[1])
                elif kind == "end":
                    await self._stop_stream()
                elif kind == "thinking_start":
                    await self._start_thinking_stream()
                elif kind == "thinking_delta":
                    await self._thinking_stream_delta(item[1])
                elif kind == "thinking_end":
                    await self._stop_thinking_stream()
                elif kind == "prompt_echo":
                    self._echo_prompt(item[1])
            except Exception:
                # Never let one bad item kill the render loop.
                pass

    # Batch streamed deltas before writing: MarkdownStream re-renders the WHOLE
    # accumulated doc on every write, so per-token writes are O(n^2) over a long
    # response. Coalescing to ~20fps writes makes total cost grow with elapsed
    # time, not token count.
    _DELTA_INTERVAL = 0.05

    async def _stream_delta(self, content: str) -> None:
        """Append a response text delta to the inline markdown widget.

        Lazily mounts the banner + markdown widget at the bottom on the first
        delta (awaited, so the first chunk isn't lost). The banner becomes the
        anchor that keeps subsequent tool output above the response. The actual
        ``MarkdownStream.write`` is deferred and batched (see ``_flush_deltas``).
        """
        if self._md_stream is None:
            # Flush queued tool output first so it mounts ABOVE this banner.
            self._flush_output()
            log = self.query_one("#log", VerticalScroll)
            banner_text = self._agent_response_banner_text()
            banner = Static(banner_text, markup=False)
            banner._cp_renderable = banner_text  # for log_text()
            self._response_anchor = banner
            await log.mount(banner)
            widget = MarkdownWidget()
            self._md_widget = widget
            await log.mount(widget)
            self._md_stream = MarkdownWidget.get_stream(widget)
        self._pending_deltas.append(content)
        self._schedule_delta_flush()

    def _schedule_delta_flush(self) -> None:
        if self._delta_handle is None:
            self._delta_handle = self.set_timer(
                self._DELTA_INTERVAL, self._flush_deltas
            )

    async def _flush_deltas(self) -> None:
        """Write all buffered deltas to the live stream as one chunk."""
        self._delta_handle = None
        if not self._pending_deltas or self._md_stream is None:
            return
        chunk = "".join(self._pending_deltas)
        self._pending_deltas.clear()
        try:
            await self._md_stream.write(chunk)
        except Exception:
            pass

    async def _stop_stream(self) -> None:
        """Stop the inline stream, leaving its widget as scrollback history."""
        # Cancel any pending delta flush; the lossless rebuild below supersedes
        # whatever was still buffered (and writing post-stop would error).
        if self._delta_handle is not None:
            try:
                self._delta_handle.stop()
            except Exception:
                pass
            self._delta_handle = None
        self._pending_deltas.clear()
        if self._md_stream is not None:
            try:
                await self._md_stream.stop()
            except Exception:
                pass
        # Rebuild the committed widget from the lossless buffer so the final
        # history is correct even if incremental rendering dropped characters
        # at part/tool boundaries (the bug this guards against).
        if self._md_widget is not None and self._stream_text:
            try:
                await self._md_widget.update(self._stream_text)
            except Exception:
                pass
        self._md_stream = None
        self._md_widget = None
        self._response_anchor = None
        self._stream_text = ""
        self._stream_last_index = None

    def _finalize_stream(self) -> None:
        """End the current turn's inline stream (queued, ordered).

        Enqueues an end marker so the stop is ordered relative to any deltas
        still in the pipeline; the actual stop happens in the render loop.
        """
        self.enqueue_render(("end",))

    # ------------------------------------------------------------------ #
    # Thinking stream (ThinkingPart deltas → dim Static widget)           #
    # ------------------------------------------------------------------ #

    async def _start_thinking_stream(self) -> None:
        """Mount the THINKING banner + an empty content widget into the log.

        If a text stream is currently active (e.g. a second ThinkingPart
        arriving mid-turn after a tool call), the stream is finalised first
        so the thinking banner always mounts AFTER the preceding response
        text. Each think→respond cycle gets its own Markdown widget and the
        ordering in the scrollback matches the real event order.
        """
        # --- Close any active text stream before mounting the banner. ------
        # Without this, the second (and later) THINKING banners mount at the
        # absolute bottom -- after the already-streaming response -- because
        # _md_stream is still open from the previous text segment.
        if self._md_stream is not None:
            # Drain buffered text deltas into the live stream first so no
            # characters are lost when we stop it.
            if self._pending_deltas:
                if self._delta_handle is not None:
                    try:
                        self._delta_handle.stop()
                    except Exception:
                        pass
                    self._delta_handle = None
                chunk = "".join(self._pending_deltas)
                self._pending_deltas.clear()
                self._stream_text += chunk
                try:
                    await self._md_stream.write(chunk)
                except Exception:
                    pass
            # Lossless rebuild then stop -- mirrors _stop_stream.
            if self._md_widget is not None and self._stream_text:
                try:
                    await self._md_widget.update(self._stream_text)
                except Exception:
                    pass
            try:
                await self._md_stream.stop()
            except Exception:
                pass
            # Per-segment state reset; widgets stay in the DOM as history.
            self._md_stream = None
            self._md_widget = None
            self._response_anchor = None
            self._stream_text = ""
            self._stream_last_index = None

        # --- Mount the banner + empty content widget at the bottom. --------
        self._flush_output()
        from code_puppy.config import get_banner_color

        log = self.query_one("#log", VerticalScroll)
        thinking_color = get_banner_color("thinking")
        banner_text = Text.from_markup(
            f"[bold white on {thinking_color}] THINKING "
            f"[/bold white on {thinking_color}] [dim]\u26a1[/dim]"
        )
        banner = Static(banner_text, markup=False)
        banner._cp_renderable = banner_text
        await log.mount(banner)
        content_widget = Static("", classes="thinking-content")
        content_widget._cp_renderable = ""
        self._thinking_widget = content_widget
        self._thinking_text_acc = ""
        await log.mount(content_widget)

    async def _thinking_stream_delta(self, content: str) -> None:
        """Buffer a thinking text chunk and schedule a batched widget update."""
        if not content:
            return
        self._thinking_pending_deltas.append(content)
        self._schedule_thinking_flush()

    def _schedule_thinking_flush(self) -> None:
        """Arm the thinking-delta flush timer (no-op if already armed)."""
        if self._thinking_delta_handle is None:
            self._thinking_delta_handle = self.set_timer(
                self._DELTA_INTERVAL, self._flush_thinking_deltas
            )

    async def _flush_thinking_deltas(self) -> None:
        """Write all buffered thinking deltas to the Static widget."""
        self._thinking_delta_handle = None
        if not self._thinking_pending_deltas or self._thinking_widget is None:
            return
        chunk = "".join(self._thinking_pending_deltas)
        self._thinking_pending_deltas.clear()
        self._thinking_text_acc += chunk
        try:
            self._thinking_widget.update(Text(self._thinking_text_acc, style="dim"))
        except Exception:
            pass

    async def _stop_thinking_stream(self) -> None:
        """Finalise the thinking widget with a lossless rebuild and clean up.

        Mirrors ``_stop_stream``: cancels any pending timer, drains buffered
        deltas, does a final authoritative update, then clears all state
        (the widget itself stays in the scrollback as history).
        """
        if self._thinking_delta_handle is not None:
            try:
                self._thinking_delta_handle.stop()
            except Exception:
                pass
            self._thinking_delta_handle = None
        # Drain any deltas that didn't make it through the timer.
        if self._thinking_pending_deltas:
            self._thinking_text_acc += "".join(self._thinking_pending_deltas)
            self._thinking_pending_deltas.clear()
        # Lossless final update.
        if self._thinking_widget is not None and self._thinking_text_acc:
            try:
                final = Text(self._thinking_text_acc, style="dim")
                self._thinking_widget.update(final)
                self._thinking_widget._cp_renderable = final
            except Exception:
                pass
        # Widget stays in scrollback; clear refs only.
        self._thinking_widget = None
        self._thinking_text_acc = ""

    def _set_busy(self, busy: bool) -> None:
        """Toggle the working state: disable input + reflect status."""
        self._busy = busy
        prompt = self.query_one("#prompt", PromptArea)
        prompt.disabled = busy
        self.sub_title = "working..." if busy else "ready"
        if busy:
            self._start_spinner()
        else:
            self._stop_spinner()
            prompt.focus()
            # A turn just finished -> token usage / branch may have changed.
            self._refresh_statusbar()
            # Drain the next queued prompt (added via /queue or Enter-while-
            # busy) exactly like the classic CLI's idle loop does. Must run
            # after _busy is already False so submit_prompt's guard passes.

    def _maybe_run_next_queued(self) -> None:
        """If a queued prompt is waiting, auto-submit it as the next turn."""
        try:
            from code_puppy.messaging.pause_controller import get_pause_controller

            next_prompt = get_pause_controller().pop_next_steer_queued()
        except Exception:
            return
        if next_prompt:
            self.submit_prompt(next_prompt)

    # ------------------------------------------------------------------ #
    # Status bar (model / agent / git branch / context%)
    # ------------------------------------------------------------------ #
    @work(thread=True, group="statusbar", exclusive=True)
    def _refresh_statusbar(self) -> None:
        """Rebuild the status bar off the UI thread (git call may block).

        Reuses the statusline plugin's ``build_payload`` (DRY) so the TUI footer
        shows the same model / agent / branch / context% the classic prompt does.
        """
        try:
            text = self._build_status_text()
        except Exception:
            return
        self.call_from_thread(self._apply_statusbar, text)

    def _apply_statusbar(self, text: Text) -> None:
        try:
            bar = self.query_one("#statusbar", Static)
            bar.update(text)
            bar._cp_renderable = text  # for tests / introspection
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Sub-agent live panel (Gap #1 TUI parity)                            #
    # ------------------------------------------------------------------ #
    def _apply_subagent_panel(self, lines: list) -> None:
        """Update the live sub-agent panel widget (must run on UI thread).

        ``lines`` is the same list that ``subagent_panel._push_panel()``
        sends to the bottom bar in classic mode — a mix of ``rich.text.Text``
        objects and plain strings.  We join them into one ``Text`` block and
        toggle the widget's visibility based on whether the list is non-empty.
        """
        try:
            widget = self.query_one("#subagent-panel", Static)
            if not lines:
                widget.remove_class("visible")
                widget.update("")
                return
            combined = Text()
            for i, line in enumerate(lines):
                if i:
                    combined.append("\n")
                if isinstance(line, Text):
                    combined.append_text(line)
                else:
                    combined.append(str(line))
            widget.update(combined)
            widget.add_class("visible")
        except Exception:
            pass

    def _on_subagent_panel_lines_changed(self, lines: list) -> None:
        """Called by the ``subagent_panel_lines_changed`` hook (any thread).

        Schedules the widget update onto the Textual UI thread.  When called
        from WITHIN the Textual event loop (e.g. the ticker asyncio task) we
        apply the update directly (we're already on the right thread).
        When called from an OS thread we use ``call_from_thread``.
        """
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # Already on the event loop — safe to update directly.
                self._apply_subagent_panel(lines)
            else:
                self.call_from_thread(self._apply_subagent_panel, lines)
        except Exception:
            pass

    def _build_status_text(self) -> Text:
        """Build the status bar text using the *same* logic as classic mode.

        Two paths, same end result:

        1. **Custom command configured** — call ``get_status_text()`` to get
           the raw ANSI string the user's script produced, then hand it to
           ``Text.from_ansi()``.  This is a zero-loss path: no intermediate
           prompt_toolkit style representation, no conversion table that could
           silently drop a color variant.

        2. **No custom command** — call ``get_prompt_with_active_model(base="")``
           (same patched function classic uses, including context_indicator)
           and convert its ``FormattedText`` tuples via ``_pt_style_to_rich``.
           The ``class:arrow`` / ``>>> `` fragment is dropped because the
           status bar is not an interactive prompt.
        """
        try:
            from code_puppy.plugins.statusline.config import get_command, is_enabled
            from code_puppy.plugins.statusline.runner import get_status_text

            if is_enabled() and get_command():
                raw = get_status_text()
                if raw:
                    return Text.from_ansi(raw)
        except Exception:
            pass

        from prompt_toolkit.formatted_text import to_formatted_text

        from code_puppy.command_line.prompt_toolkit_completion import (
            get_prompt_with_active_model,
        )

        try:
            frags = list(to_formatted_text(get_prompt_with_active_model(base="")))
        except Exception:
            return Text("  ")

        t = Text()
        for style_str, text in frags:
            if not text:
                continue
            rich_style = _pt_style_to_rich(style_str)
            if rich_style is None:  # arrow -> skip
                continue
            t.append(text, style=rich_style)
        return t

    # ------------------------------------------------------------------ #
    # Thinking spinner (mirrors the classic ConsoleSpinner)               #
    # ------------------------------------------------------------------ #
    def _start_spinner(self) -> None:
        self._spinner_frame = 0
        spinner = self.query_one("#spinner", Static)
        spinner.add_class("visible")
        self._render_spinner()
        if self._spinner_timer is None:
            # 0.05s per frame matches the classic ConsoleSpinner cadence.
            self._spinner_timer = self.set_interval(0.05, self._tick_spinner)
        else:
            self._spinner_timer.resume()

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.pause()
        try:
            self.query_one("#spinner", Static).remove_class("visible")
        except Exception:
            pass

    def _tick_spinner(self) -> None:
        try:
            from code_puppy.plugins.puppy_spinner.register_callbacks import (
                _current_frames_and_interval,
            )

            frames, _interval = _current_frames_and_interval()
        except Exception:
            from code_puppy.messaging.spinner import FRAMES

            frames = FRAMES
        self._spinner_frame = (self._spinner_frame + 1) % len(frames)
        self._render_spinner()

    def _render_spinner(self) -> None:
        from code_puppy.messaging.spinner import (
            THINKING_MESSAGE,
            get_context_info,
        )

        try:
            from code_puppy.plugins.puppy_spinner.register_callbacks import (
                _current_frames_and_interval,
            )

            frames, _interval = _current_frames_and_interval()
        except Exception:
            from code_puppy.messaging.spinner import FRAMES

            frames = FRAMES
        frame = frames[self._spinner_frame % len(frames)]
        ctx = get_context_info()
        line = Text()
        line.append(THINKING_MESSAGE, style="bold cyan")
        line.append(frame, style="cyan")
        if ctx:
            line.append("  ")
            line.append(ctx, style="dim")
        try:
            self.query_one("#spinner", Static).update(line)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Completion (Phase 2e): /command and @path                            #
    # ------------------------------------------------------------------ #
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "prompt":
            self._transform_prompt_attachments(event.text_area)
            self._refresh_completions()

    # ------------------------------------------------------------------ #
    # Drag-and-drop / paste capture                                        #
    # ------------------------------------------------------------------ #
    def on_paste(self, event: events.Paste) -> None:
        """Catch pastes (incl. file drops) even when the prompt isn't focused.

        A paste is delivered to the focused widget first; if that's the prompt,
        its TextArea already inserted the text (and `on_text_area_changed`
        transformed it), so we bail. Otherwise we route the text into the
        prompt ourselves so a file dropped anywhere still lands in the box.
        """
        try:
            prompt = self.query_one("#prompt", PromptArea)
        except Exception:
            return
        if self.focused is prompt:
            return  # already handled by the focused TextArea
        if not event.text:
            return
        prompt.focus()
        prompt.replace(event.text, *prompt.selection, maintain_selection_offset=False)
        prompt.move_cursor(prompt.document.end)
        event.stop()

    def _transform_prompt_attachments(self, prompt: TextArea) -> None:
        """Swap recognised image/doc paths in the buffer for friendly chips.

        Reacts to *buffer content* (like the classic prompt_toolkit Processor)
        rather than the paste event, so it works no matter how the path landed
        in the box -- drag-drop, paste, or typing. Idempotent: placeholders
        aren't re-detected, so repeated changes are no-ops.
        """
        if self._transforming_attachments:
            return
        from .attachments import transform_dragged_paths

        text = prompt.text
        # Skip the filesystem probing on very large inputs (pasted content).
        if not text or len(text) > 4096:
            return
        display_text, mapping = transform_dragged_paths(text)
        if not mapping or display_text == text:
            return

        self._transforming_attachments = True
        try:
            self.register_attachment_placeholders(mapping)
            prompt.text = display_text
            prompt.move_cursor(prompt.document.end)
        finally:
            self._transforming_attachments = False

    def completion_visible(self) -> bool:
        return self._completion is not None

    def _refresh_completions(self) -> None:
        prompt = self.query_one("#prompt", PromptArea)
        completions = self.query_one("#completions", CompletionList)
        row, col = prompt.cursor_location
        line = str(prompt.document.get_line(row))
        result = compute_completions(line, col)

        completions.clear_options()
        if result is None:
            self._completion = None
            completions.remove_class("visible")
            return

        self._completion = result
        for item in result.items:
            label = item.display
            if item.meta:
                label = f"{item.display}   {item.meta}"
            # Plain Text avoids Rich-markup injection from descriptions/paths.
            completions.add_option(Option(Text(label, overflow="ellipsis")))
        completions.add_class("visible")
        completions.highlighted = 0

    def completion_move(self, delta: int) -> None:
        completions = self.query_one("#completions", CompletionList)
        count = completions.option_count
        if not count:
            return
        current = completions.highlighted or 0
        completions.highlighted = max(0, min(count - 1, current + delta))

    def completion_is_exact(self) -> bool:
        """True if the highlighted completion already equals the text it would
        replace (e.g. a fully-typed ``/command``). Enter should then submit
        rather than re-accept (and re-trigger argument completion).
        """
        completions = self.query_one("#completions", CompletionList)
        if self._completion is None or completions.highlighted is None:
            return False
        item = self._completion.items[completions.highlighted]
        prompt = self.query_one("#prompt", PromptArea)
        row, col = prompt.cursor_location
        line = str(prompt.document.get_line(row))
        replaced = line[self._completion.start_col : col]
        return item.display == replaced

    def accept_completion(self, submit_if_terminal: bool = False) -> bool:
        """Insert the highlighted completion into the prompt.

        When ``submit_if_terminal`` is set and the accepted item completes a
        *command name* that has nothing left to complete (no argument
        completions follow), the prompt is submitted immediately -- so menu
        commands like ``/help`` or ``/diff`` open on a single Enter instead of
        requiring a second one (Enter-completes-then-Enter-runs). Commands
        that take argument completions (``/model``, ``/agent``, ``/mcp``)
        leave the dropdown open so the user can pick an argument.

        Returns True if the prompt was submitted, False otherwise.
        """
        completions = self.query_one("#completions", CompletionList)
        if self._completion is None or completions.highlighted is None:
            return False
        item = self._completion.items[completions.highlighted]
        # A command-name completion inserts "/<name> "; argument/path
        # completions don't start with a slash.
        is_command = item.insert.startswith("/")
        prompt = self.query_one("#prompt", PromptArea)
        row, _ = prompt.cursor_location
        prompt.replace(
            item.insert,
            (row, self._completion.start_col),
            (row, self._completion.end_col),
        )
        prompt.move_cursor((row, self._completion.start_col + len(item.insert)))
        self.hide_completions()
        prompt.focus()

        if submit_if_terminal and is_command:
            # Did completing the command surface argument completions? If so,
            # keep the dropdown open and let the user pick one. Otherwise it's
            # a terminal command -> run it now (single-Enter menu open).
            self._refresh_completions()
            if not self.completion_visible():
                text = prompt.text
                prompt.text = ""
                self.submit_prompt(text)
                return True
        return False

    def hide_completions(self) -> None:
        self._completion = None
        completions = self.query_one("#completions", CompletionList)
        completions.remove_class("visible")
        completions.clear_options()

    def _on_legacy_message(self, message) -> None:
        """Legacy-queue listener (runs on the queue's daemon thread).

        Enqueues into the single render pipeline so legacy output stays ordered
        with bus output and streamed deltas.
        """
        try:
            self.call_from_thread(self.enqueue_render, ("legacy", message))
        except Exception:
            pass

    def handle_legacy_message(self, message) -> None:
        """Render a legacy UIMessage into the scrollback (UI thread)."""
        from code_puppy.messaging.message_queue import MessageType

        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            self._show_legacy_prompt(message)
            return
        width = self._log_width()
        renderable = self._legacy_formatter.format(message, width=width)
        if renderable is not None:
            # Keep legacy tool output above an actively streaming response.
            self._append_output(renderable)

    def _show_legacy_prompt(self, message) -> None:
        """Answer a legacy HUMAN_INPUT_REQUEST via a modal so tools don't hang."""
        from code_puppy.messaging.message_queue import get_global_queue

        prompt_id = (message.metadata or {}).get("prompt_id")
        request = UserInputRequest(
            prompt_id=str(prompt_id or "legacy"),
            prompt_text=str(message.content),
        )

        def _reply(value) -> None:
            if prompt_id is not None:
                get_global_queue().provide_prompt_response(prompt_id, value or "")

        self.push_screen(TextInputModal(request), _reply)

    def on_unmount(self) -> None:
        from code_puppy.callbacks import unregister_callback
        from code_puppy.messaging.message_queue import get_global_queue

        try:
            get_global_queue().remove_listener(self._on_legacy_message)
        except Exception:
            pass
        unregister_callback("stream_event", self._on_stream_event)
        unregister_callback(
            "subagent_panel_lines_changed", self._on_subagent_panel_lines_changed
        )
        try:
            get_message_bus().set_event_loop(None)
        except Exception:
            pass
        self._renderer.stop()


def build_app(initial_command: str | None = None) -> CooperApp:
    """Factory used by the launcher and by tests."""
    return CooperApp(initial_command=initial_command)
