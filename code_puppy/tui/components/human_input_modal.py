"""
Modal component for human input requests.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

try:
    from .custom_widgets import CustomTextArea
except ImportError:
    # Fallback to regular TextArea if CustomTextArea isn't available
    CustomTextArea = TextArea


class HumanInputModal(ModalScreen):
    """Modal for requesting human input."""

    def __init__(self, prompt_text: str, prompt_id: str, **kwargs):
        """Initialize the modal with prompt information.

        Args:
            prompt_text: The prompt to display to the user
            prompt_id: Unique identifier for this prompt request
            **kwargs: Additional arguments to pass to the parent class
        """
        super().__init__(**kwargs)
        self.prompt_text = prompt_text
        self.prompt_id = prompt_id
        self.response = ""
        print(f"[DEBUG] Created HumanInputModal for prompt_id: {prompt_id}")

    DEFAULT_CSS = """
    HumanInputModal {
        align: center middle;
    }

    #modal-container {
        width: 80%;
        max-width: 80;
        height: 16;
        min-height: 12;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        layout: vertical;
    }

    #prompt-display {
        width: 100%;
        margin-bottom: 1;
        color: $text;
        text-align: left;
        height: auto;
        max-height: 6;
        overflow: auto;
    }

    #input-container {
        width: 100%;
        height: 4;
        margin-bottom: 1;
    }

    #response-input {
        width: 100%;
        height: 4;
        border: solid $primary;
        background: $surface-darken-1;
    }

    #button-container {
        width: 100%;
        height: 3;
        align: center bottom;
        layout: horizontal;
    }

    #submit-button, #cancel-button {
        width: auto;
        height: 3;
        margin: 0 1;
        min-width: 10;
    }

    #hint-text {
        width: 100%;
        color: $text-muted;
        text-align: center;
        height: 1;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the modal layout."""
        with Container(id="modal-container"):
            yield Static(self.prompt_text, id="prompt-display")
            with Container(id="input-container"):
                yield CustomTextArea("", id="response-input")
            with Horizontal(id="button-container"):
                yield Button("Submit", id="submit-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="default")
            yield Static("Enter to submit • Escape to cancel", id="hint-text")

    def on_mount(self) -> None:
        """Focus the input field when modal opens."""
        try:
            print("[DEBUG] Modal on_mount called")
            input_field = self.query_one("#response-input", CustomTextArea)
            input_field.focus()
            print("[DEBUG] Modal input field focused")
        except Exception as e:
            print(f"[DEBUG] Modal on_mount exception: {e}")
            import traceback

            traceback.print_exc()

    @on(Button.Pressed, "#submit-button")
    def on_submit_clicked(self) -> None:
        """Handle submit button click."""
        self._submit_response()

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self._cancel_response()

    def on_key(self, event: Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            self._cancel_response()
            event.prevent_default()
        elif event.key == "enter":
            # Check if we're in the text area and it's not multi-line
            try:
                input_field = self.query_one("#response-input", CustomTextArea)
                if input_field.has_focus and "\n" not in input_field.text:
                    self._submit_response()
                    event.prevent_default()
            except Exception:
                pass

    def _submit_response(self) -> None:
        """Submit the user's response."""
        try:
            input_field = self.query_one("#response-input", CustomTextArea)
            self.response = input_field.text.strip()
            print(f"[DEBUG] Modal submitting response: {self.response[:20]}...")

            # Provide the response back to the message queue
            from code_puppy.messaging import provide_prompt_response

            provide_prompt_response(self.prompt_id, self.response)

            # Close the modal using the same method as other modals
            self.app.pop_screen()
        except Exception as e:
            print(f"[DEBUG] Modal error during submit: {e}")
            # If something goes wrong, provide empty response
            from code_puppy.messaging import provide_prompt_response

            provide_prompt_response(self.prompt_id, "")
            self.app.pop_screen()

    def _cancel_response(self) -> None:
        """Cancel the input request."""
        print("[DEBUG] Modal cancelling response")
        from code_puppy.messaging import provide_prompt_response

        provide_prompt_response(self.prompt_id, "")
        self.app.pop_screen()
