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
from rich.markdown import Markdown
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, OptionList, RichLog, TextArea
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


class CompletionList(OptionList):
    """Completion dropdown that never steals focus from the prompt."""

    can_focus = False


class PromptArea(TextArea):
    """Multiline prompt. Enter submits; Shift+Enter inserts a newline.

    When the completion dropdown is open, Up/Down navigate it, Tab/Enter
    accept the highlighted item, and Escape dismisses it.
    """

    def _on_key(self, event: events.Key) -> None:
        if self.app.completion_visible():
            if event.key in ("down", "up", "tab", "enter", "escape"):
                event.prevent_default()
                event.stop()
                if event.key == "down":
                    self.app.completion_move(1)
                elif event.key == "up":
                    self.app.completion_move(-1)
                elif event.key in ("tab", "enter"):
                    self.app.accept_completion()
                else:
                    self.app.hide_completions()
                return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.app.submit_prompt(self.text)
            self.text = ""
        # Shift+Enter / ctrl+j fall through to default newline insertion.


class CooperApp(App):
    """Code Puppy's Textual UI (Phase 0 scaffold)."""

    CSS = """
    Screen { background: $surface; }
    #log {
        border: round $primary;
        padding: 0 1;
        background: $panel;
    }
    #prompt {
        height: 5;
        border: round $accent;
        margin-top: 1;
    }
    #completions {
        display: none;
        height: auto;
        max-height: 8;
        border: round $primary;
        background: $panel;
        margin-top: 1;
    }
    #completions.visible { display: block; }
    #stream-scroll {
        display: none;
        height: auto;
        max-height: 16;
        background: $panel;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }
    #stream-scroll.visible { display: block; }
    #stream {
        background: transparent;
        padding: 0;
        margin: 0;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("escape", "cancel_turn", "Cancel"),
        ("ctrl+t", "steer", "Steer"),
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
        # Live markdown streaming for the in-progress response (None when idle).
        self._md_stream: MarkdownStream | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            # Captured output is already fully styled by the classic renderer;
            # render it verbatim (no re-highlighting / markup re-parsing) so we
            # don't double-process span boundaries.
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)
            # Live response streaming: formatted markdown rendered in place as
            # tokens arrive (Textual MarkdownStream coalesces updates). The
            # scroll container anchors to the bottom so the typewriter effect
            # follows the latest text. On completion the response is promoted
            # into #log and this is cleared/hidden.
            with VerticalScroll(id="stream-scroll"):
                yield MarkdownWidget(id="stream")
            yield CompletionList(id="completions")
            yield PromptArea(id="prompt", soft_wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        # Importing command_handler registers all built-in slash commands so
        # completion is populated from the first keystroke (not just after the
        # first /command is dispatched).
        import code_puppy.command_line.command_handler  # noqa: F401

        # The classic logo print (cli_runner.run) is skipped in Textual mode
        # because stdout is wiped when the app grabs the screen. Render it here
        # instead, using the shared builder so both UIs stay in sync.
        from code_puppy.startup_banner import build_logo_renderable

        logo = build_logo_renderable()
        if logo is not None:
            self.query_one("#log", RichLog).write(logo)

        self._renderer.start()

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

    def write_renderable(self, renderable: RenderableType) -> None:
        """Mount a renderable into the scrollback."""
        self.query_one("#log", RichLog).write(renderable)

    def handle_bus_message(self, message: AnyMessage) -> None:
        """Render a bus message into the scrollback (runs on the UI thread).

        Uses the Phase 1 capture bridge for full parity with the classic UI.
        Falls back to a minimal renderable only if capture yields nothing for
        a plain TextMessage (defensive; shouldn't normally happen).
        """
        log = self.query_one("#log", RichLog)
        width = log.size.width or None

        # The agent's final response: the classic UI streams it to the
        # terminal (so its _do_render skips it). We stream to a hidden
        # console, so we render the response here instead.
        if isinstance(message, AgentResponseMessage):
            # Promote the streamed response into the permanent scrollback and
            # clear the live streaming widget (same handler -> one repaint, no
            # flicker / no duplicate).
            body = (
                Markdown(message.content)
                if message.is_markdown
                else Text(message.content)
            )
            log.write(body)
            self._reset_stream()
            return

        # Interactive requests: the agent is awaiting a response. Show a modal
        # and ALWAYS reply (even on cancel) so the agent never hangs.
        if isinstance(
            message, (UserInputRequest, ConfirmationRequest, SelectionRequest)
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
        log.write(renderable)

    def submit_prompt(self, text: str) -> None:
        """Dispatch a submitted prompt: exit, slash command, or agent turn."""
        text = text.strip()
        if not text or self._busy:
            return

        lowered = text.lower()
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
        """Run one agent turn on a Textual worker, keeping the UI responsive."""
        from code_puppy.agents import get_current_agent
        from code_puppy.cli_runner import run_prompt_with_attachments
        from code_puppy.config import auto_save_session_if_enabled
        from code_puppy.messaging import emit_error

        self._reset_stream()
        self._set_busy(True)
        try:
            agent = get_current_agent()
            result, _agent_task = await run_prompt_with_attachments(
                agent,
                task,
                spinner_console=self._quiet_console,
                use_spinner=False,
            )
            if result is None:
                return  # cancelled or empty
            if hasattr(result, "all_messages"):
                agent.set_message_history(list(result.all_messages()))
            get_message_bus().emit(
                AgentResponseMessage(content=result.output, is_markdown=True)
            )
            auto_save_session_if_enabled()
        except Exception as e:
            emit_error(f"Agent error: {e}")
        finally:
            self._set_busy(False)

    def action_cancel_turn(self) -> None:
        """Hard-cancel the running agent turn (Escape)."""
        if not self._busy or self._agent_worker is None:
            return
        try:
            self._agent_worker.cancel()
        except Exception:
            pass
        self._reset_stream()
        get_message_bus().emit(
            TextMessage(level=MessageLevel.WARNING, text="Turn cancelled.")
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
        """Stream response text deltas as formatted markdown, live.

        Runs on the app's event loop (the stream callback is fired there), so
        widget updates are safe. Only TEXT parts are streamed; thinking/tool
        deltas are ignored here. The text is rendered as markdown in place via
        a Textual MarkdownStream (it coalesces updates to keep up).
        """
        try:
            if event_type != "part_delta":
                return
            if event_data.get("delta_type") != "TextPartDelta":
                return
            delta = event_data.get("delta")
            content = getattr(delta, "content_delta", None)
            if not content:
                return
            if self._md_stream is None:
                scroll = self.query_one("#stream-scroll", VerticalScroll)
                widget = self.query_one("#stream", MarkdownWidget)
                scroll.add_class("visible")
                # Follow the bottom as new text streams in.
                scroll.anchor()
                self._md_stream = MarkdownWidget.get_stream(widget)
            # write() appends synchronously to the stream's pending buffer
            # before its only await, so create_task preserves delta order.
            asyncio.create_task(self._md_stream.write(content))
        except Exception:
            # Streaming is best-effort polish; never break a turn over it.
            pass

    def _reset_stream(self) -> None:
        """Stop streaming and clear/hide the live markdown widget."""
        stream_obj = self._md_stream
        self._md_stream = None
        if stream_obj is not None or self._stream_visible():
            self.run_worker(
                self._async_reset_stream(stream_obj),
                group="stream-reset",
                exclusive=True,
            )

    def _stream_visible(self) -> bool:
        try:
            return self.query_one("#stream-scroll", VerticalScroll).has_class("visible")
        except Exception:
            return False

    async def _async_reset_stream(self, stream_obj: MarkdownStream | None) -> None:
        if stream_obj is not None:
            try:
                await stream_obj.stop()
            except Exception:
                pass
        try:
            scroll = self.query_one("#stream-scroll", VerticalScroll)
            scroll.remove_class("visible")
            await self.query_one("#stream", MarkdownWidget).update("")
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        """Toggle the working state: disable input + reflect status."""
        self._busy = busy
        prompt = self.query_one("#prompt", PromptArea)
        prompt.disabled = busy
        self.sub_title = "working..." if busy else "ready"
        if not busy:
            prompt.focus()

    # ------------------------------------------------------------------ #
    # Completion (Phase 2e): /command and @path                            #
    # ------------------------------------------------------------------ #
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "prompt":
            self._refresh_completions()

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

    def accept_completion(self) -> None:
        completions = self.query_one("#completions", CompletionList)
        if self._completion is None or completions.highlighted is None:
            return
        item = self._completion.items[completions.highlighted]
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

    def hide_completions(self) -> None:
        self._completion = None
        completions = self.query_one("#completions", CompletionList)
        completions.remove_class("visible")
        completions.clear_options()

    def _on_legacy_message(self, message) -> None:
        """Legacy-queue listener (runs on the queue's daemon thread)."""
        try:
            self.call_from_thread(self.handle_legacy_message, message)
        except Exception:
            pass

    def handle_legacy_message(self, message) -> None:
        """Render a legacy UIMessage into the scrollback (UI thread)."""
        from code_puppy.messaging.message_queue import MessageType

        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            self._show_legacy_prompt(message)
            return
        log = self.query_one("#log", RichLog)
        renderable = self._legacy_formatter.format(
            message, width=log.size.width or None
        )
        if renderable is not None:
            log.write(renderable)

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
        self._renderer.stop()


def build_app(initial_command: str | None = None) -> CooperApp:
    """Factory used by the launcher and by tests."""
    return CooperApp(initial_command=initial_command)
