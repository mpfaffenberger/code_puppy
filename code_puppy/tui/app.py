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

from io import StringIO

from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, RichLog, TextArea

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

from .capture import RichCaptureFormatter
from .renderer import TextualRenderer, message_to_renderable
from .screens.interactive import ConfirmModal, SelectionModal, TextInputModal


class PromptArea(TextArea):
    """Multiline prompt. Enter submits; Shift+Enter inserts a newline."""

    def _on_key(self, event: events.Key) -> None:
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
        # Hidden console so the agent's live token streaming never writes to
        # the real terminal (which would corrupt the Textual screen). The
        # final response is rendered from AgentResponseMessage instead.
        self._quiet_console = Console(file=StringIO(), force_terminal=False)
        self._busy = False
        self._agent_worker = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            # Captured output is already fully styled by the classic renderer;
            # render it verbatim (no re-highlighting / markup re-parsing) so we
            # don't double-process span boundaries.
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)
            yield PromptArea(id="prompt", soft_wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        bus = get_message_bus()
        bus.emit(
            TextMessage(
                level=MessageLevel.SUCCESS,
                text="cooper is ready. Type a task and press Enter. Ctrl+Q to quit.",
            )
        )
        self._renderer.start()
        self.query_one("#prompt", PromptArea).focus()
        if self._initial_command:
            self.submit_prompt(self._initial_command)

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
            body = (
                Markdown(message.content)
                if message.is_markdown
                else Text(message.content)
            )
            log.write(body)
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
            # Shell passthrough writes to stdout; routing it cleanly into the
            # TUI comes in a later Phase 2 sub-step.
            get_message_bus().emit(
                TextMessage(
                    level=MessageLevel.WARNING,
                    text="Shell passthrough (!cmd) isn't wired into the TUI yet.",
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

        try:
            result = handle_command(command)
        except Exception as e:  # never let a command crash the UI
            emit_error(f"Command error: {e}")
            return True
        if result == "__AUTOSAVE_LOAD__":
            emit_error("Interactive autosave load isn't available in the TUI yet.")
            return True
        return result

    @work(exclusive=True, group="agent")
    async def _run_agent_turn(self, task: str) -> None:
        """Run one agent turn on a Textual worker, keeping the UI responsive."""
        from code_puppy.agents import get_current_agent
        from code_puppy.cli_runner import run_prompt_with_attachments
        from code_puppy.config import auto_save_session_if_enabled
        from code_puppy.messaging import emit_error

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

    def _set_busy(self, busy: bool) -> None:
        """Toggle the working state: disable input + reflect status."""
        self._busy = busy
        prompt = self.query_one("#prompt", PromptArea)
        prompt.disabled = busy
        self.sub_title = "working..." if busy else "ready"
        if not busy:
            prompt.focus()

    def on_unmount(self) -> None:
        self._renderer.stop()


def build_app(initial_command: str | None = None) -> CooperApp:
    """Factory used by the launcher and by tests."""
    return CooperApp(initial_command=initial_command)
