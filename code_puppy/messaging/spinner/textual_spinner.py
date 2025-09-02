"""
Textual spinner implementation for TUI mode.
"""

from textual.widgets import Static

from .spinner_base import SpinnerBase


class TextualSpinner(Static):
    """A textual spinner widget based on the SimpleSpinnerWidget."""

    # Use the frames from SpinnerBase
    FRAMES = SpinnerBase.FRAMES

    def __init__(self, **kwargs):
        """Initialize the textual spinner."""
        super().__init__("", **kwargs)
        self._frame_index = 0
        self._is_spinning = False
        self._timer = None
        self._paused = False
        self._previous_state = ""

        # Register this spinner for global management
        from . import register_spinner

        register_spinner(self)

    def start_spinning(self):
        """Start the spinner animation using Textual's timer system."""
        if not self._is_spinning:
            self._is_spinning = True
            self._frame_index = 0
            self.update_frame_display()
            # Start the animation timer using Textual's timer system
            self._timer = self.set_interval(0.10, self.update_frame_display)

    def stop_spinning(self):
        """Stop the spinner animation."""
        self._is_spinning = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.update("")

        # Unregister this spinner from global management
        from . import unregister_spinner

        unregister_spinner(self)

    def update_frame(self):
        """Update to the next frame."""
        if self._is_spinning:
            self._frame_index = (self._frame_index + 1) % len(self.FRAMES)

    def update_frame_display(self):
        """Update the display with the current frame."""
        if self._is_spinning:
            self.update_frame()
            current_frame = self.FRAMES[self._frame_index]

            # Check if we're awaiting user input to determine which message to show
            from code_puppy.tools.command_runner import is_awaiting_user_input

            if is_awaiting_user_input():
                # Show waiting message when waiting for user input
                message = SpinnerBase.WAITING_MESSAGE
            else:
                # Show thinking message during normal processing
                message = SpinnerBase.THINKING_MESSAGE

            self.update(
                f"[bold cyan]{message}[/bold cyan][bold cyan]{current_frame}[/bold cyan]"
            )

    def pause(self):
        """Pause the spinner animation temporarily."""
        if self._is_spinning and self._timer and not self._paused:
            self._paused = True
            self._timer.pause()
            # Store current state but don't clear it completely
            self._previous_state = self.renderable
            self.update("")

    def resume(self):
        """Resume a paused spinner animation."""
        # Check if we should show a spinner - don't resume if waiting for user input
        from code_puppy.tools.command_runner import is_awaiting_user_input

        if is_awaiting_user_input():
            return  # Don't resume if waiting for user input

        if self._is_spinning and self._timer and self._paused:
            self._paused = False
            self._timer.resume()
            # Restore previous state instead of immediately updating display
            if self._previous_state:
                self.update(self._previous_state)
            else:
                self.update_frame_display()
