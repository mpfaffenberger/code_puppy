"""
Console spinner implementation for CLI mode using Rich's Live Display.
"""

import threading
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

from .spinner_base import SpinnerBase


class ConsoleSpinner(SpinnerBase):
    """A console-based spinner implementation using Rich's Live Display."""

    def __init__(self, console=None):
        """Initialize the console spinner.

        Args:
            console: Optional Rich console instance to use for output.
                    If not provided, a new one will be created.
        """
        super().__init__()
        self.console = console or Console()
        self._thread = None
        self._stop_event = threading.Event()
        self._paused = False
        self._live = None

        # Register this spinner for global management
        from . import register_spinner

        register_spinner(self)

    def start(self):
        """Start the spinner animation."""
        super().start()
        self._stop_event.clear()

        # Don't start a new thread if one is already running
        if self._thread and self._thread.is_alive():
            return

        # Create a Live display for the spinner
        self._live = Live(
            self._generate_spinner_panel(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
            auto_refresh=False,  # Don't auto-refresh to avoid wiping out user input
        )
        self._live.start()

        # Start a thread to update the spinner frames
        self._thread = threading.Thread(target=self._update_spinner)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stop the spinner animation."""
        if not self._is_spinning:
            return

        self._stop_event.set()
        self._is_spinning = False

        if self._live:
            self._live.stop()
            self._live = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

        self._thread = None

        # Unregister this spinner from global management
        from . import unregister_spinner

        unregister_spinner(self)

    def update_frame(self):
        """Update to the next frame."""
        super().update_frame()

    def _generate_spinner_panel(self):
        """Generate a Rich panel containing the spinner text."""
        if self._paused:
            return Text("")

        text = Text()

        # Check if we're awaiting user input to determine which message to show
        from code_puppy.tools.command_runner import is_awaiting_user_input

        if is_awaiting_user_input():
            # Show waiting message when waiting for user input
            text.append(SpinnerBase.WAITING_MESSAGE, style="bold cyan")
        else:
            # Show thinking message during normal processing
            text.append(SpinnerBase.THINKING_MESSAGE, style="bold cyan")

        text.append(self.current_frame, style="bold cyan")

        # Return a simple Text object instead of a Panel for a cleaner look
        return text

    def _update_spinner(self):
        """Update the spinner in a background thread."""
        try:
            while not self._stop_event.is_set():
                # Update the frame
                self.update_frame()

                # Check if we're awaiting user input before updating the display
                from code_puppy.tools.command_runner import is_awaiting_user_input

                awaiting_input = is_awaiting_user_input()

                # Update the live display only if not paused and not awaiting input
                if self._live and not self._paused and not awaiting_input:
                    # Manually refresh instead of auto-refresh to avoid wiping input
                    self._live.update(self._generate_spinner_panel())
                    self._live.refresh()

                # Short sleep to control animation speed
                time.sleep(0.05)
        except Exception as e:
            print(f"\nSpinner error: {e}")
            self._is_spinning = False

    def pause(self):
        """Pause the spinner animation."""
        if self._is_spinning:
            self._paused = True
            # Update the live display to hide the spinner immediately
            if self._live:
                try:
                    # When pausing, first update with the waiting message
                    # so it's visible briefly before disappearing
                    from code_puppy.tools.command_runner import is_awaiting_user_input

                    if is_awaiting_user_input():
                        text = Text()
                        text.append(SpinnerBase.WAITING_MESSAGE, style="bold cyan")
                        text.append(self.current_frame, style="bold cyan")
                        self._live.update(text)
                        self._live.refresh()
                        # Allow a moment for the waiting message to be visible
                        import time

                        time.sleep(0.1)

                    # Then clear the display
                    self._live.update(Text(""))
                except Exception:
                    # If update fails, try stopping it completely
                    try:
                        self._live.stop()
                    except Exception:
                        pass

    def resume(self):
        """Resume the spinner animation."""
        # Check if we should show a spinner - don't resume if waiting for user input
        from code_puppy.tools.command_runner import is_awaiting_user_input

        if is_awaiting_user_input():
            return  # Don't resume if waiting for user input

        if self._is_spinning and self._paused:
            self._paused = False
            # Force an immediate update to show the spinner again
            if self._live:
                try:
                    self._live.update(self._generate_spinner_panel())
                except Exception:
                    # If update fails, the live display might have been stopped
                    # Try to restart it
                    try:
                        self._live = Live(
                            self._generate_spinner_panel(),
                            console=self.console,
                            refresh_per_second=10,
                            transient=True,
                            auto_refresh=False,  # Don't auto-refresh to avoid wiping out user input
                        )
                        self._live.start()
                    except Exception:
                        pass

    def __enter__(self):
        """Support for context manager."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up when exiting context manager."""
        self.stop()
