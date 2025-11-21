"""
Copy button component for copying agent responses to clipboard.
"""

import subprocess
import sys
from typing import Optional

from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widgets import Button


class CopyButton(Button):
    """A button that copies associated text to the clipboard."""

    DEFAULT_CSS = """
    CopyButton {
        width: auto;
        height: 3;
        min-width: 8;
        margin: 0 1 1 1;
        padding: 0 1;
        background: $primary;
        color: $text;
        border: none;
        text-align: center;
    }

    CopyButton:hover {
        background: $accent;
        color: $text;
    }

    CopyButton:focus {
        background: $accent;
        color: $text;
        text-style: bold;
    }

    CopyButton.-pressed {
        background: $success;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("enter", "press", "Copy", show=False),
        Binding("space", "press", "Copy", show=False),
    ]

    def __init__(self, text_to_copy: str, **kwargs):
        super().__init__("📋 Copy", **kwargs)
        self.text_to_copy = text_to_copy
        self._original_label = "📋 Copy"
        self._copied_label = "✅ Copied!"

    class CopyCompleted(Message):
        """Message sent when text is successfully copied."""

        def __init__(self, success: bool, error: Optional[str] = None):
            super().__init__()
            self.success = success
            self.error = error

    def copy_to_clipboard(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Copy text to clipboard using platform-appropriate method.

        Returns:
            tuple: (success: bool, error_message: Optional[str])
        """
        try:
            if sys.platform == "darwin":  # macOS
                subprocess.run(
                    ["pbcopy"], input=text, text=True, check=True, capture_output=True
                )
            elif sys.platform == "win32":  # Windows
                subprocess.run(
                    ["clip"], input=text, text=True, check=True, capture_output=True
                )
            else:  # Linux and other Unix-like systems
                # Try xclip first, then xsel as fallback
                try:
                    subprocess.run(
                        ["xclip", "-selection", "clipboard"],
                        input=text,
                        text=True,
                        check=True,
                        capture_output=True,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # Fallback to xsel
                    subprocess.run(
                        ["xsel", "--clipboard", "--input"],
                        input=text,
                        text=True,
                        check=True,
                        capture_output=True,
                    )

            return True, None

        except subprocess.CalledProcessError as e:
            return False, f"Clipboard command failed: {e}"
        except FileNotFoundError:
            if sys.platform not in ["darwin", "win32"]:
                return (
                    False,
                    "Clipboard utilities not found. Please install xclip or xsel.",
                )
            else:
                return False, "System clipboard command not found."
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def on_click(self, event: Click) -> None:
        """Handle button click to copy text."""
        self.action_press()

    def action_press(self) -> None:
        """Copy the text to clipboard and provide visual feedback."""
        success, error = self.copy_to_clipboard(self.text_to_copy)

        if success:
            # Visual feedback - change button text temporarily
            self.label = self._copied_label
            self.add_class("-pressed")

            # Reset button appearance after a short delay
            # self.set_timer(1.5, self._reset_button_appearance)

        # Send message about copy operation
        self.post_message(self.CopyCompleted(success, error))

    def update_text_to_copy(self, new_text: str) -> None:
        """Update the text that will be copied when button is pressed."""
        self.text_to_copy = new_text
