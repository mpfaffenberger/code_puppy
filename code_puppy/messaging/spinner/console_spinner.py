"""
Console spinner implementation for CLI mode using Rich's Live Display.
"""

import platform
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

        # Print blank line before spinner for visual separation from content
        self.console.print()

        # Create a Live display for the spinner
        self._live = Live(
            self._generate_spinner_panel(),
            console=self.console,
            refresh_per_second=20,
            transient=True,  # Clear the spinner line when stopped (no puppy litter!)
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

        # Windows-specific cleanup: Rich's Live display can leave terminal in corrupted state
        if platform.system() == "Windows":
            import sys

            try:
                # Reset ANSI formatting for both stdout and stderr
                sys.stdout.write("\x1b[0m")  # Reset all attributes
                sys.stdout.flush()
                sys.stderr.write("\x1b[0m")
                sys.stderr.flush()

                # Clear the line and reposition cursor
                sys.stdout.write("\r")  # Return to start of line
                sys.stdout.write("\x1b[K")  # Clear to end of line
                sys.stdout.flush()

                # Flush keyboard input buffer to clear any stuck keys
                try:
                    import msvcrt

                    while msvcrt.kbhit():
                        msvcrt.getch()
                except ImportError:
                    pass  # msvcrt not available (not Windows or different Python impl)
            except Exception:
                pass  # Fail silently if cleanup doesn't work

        # Unregister this spinner from global management
        from . import unregister_spinner

        unregister_spinner(self)

    def update_frame(self):
        """Update to the next frame."""
        super().update_frame()

    def _generate_spinner_panel(self):
        """Generate a Rich panel containing the spinner text."""
        # Check if we're awaiting user input - show nothing during input prompts
        from code_puppy.tools.command_runner import is_awaiting_user_input

        if self._paused or is_awaiting_user_input():
            return Text("")

        text = Text()

        # Show thinking message during normal processing
        text.append(SpinnerBase.THINKING_MESSAGE, style="bold cyan")
        text.append(self.current_frame, style="bold cyan")

        context_info = SpinnerBase.get_context_info()
        if context_info:
            text.append(" ")
            text.append(context_info, style="bold white")

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
            # Note: Using sys.stderr - can't use messaging during spinner
            import sys

            sys.stderr.write(f"\nSpinner error: {e}\n")
            self._is_spinning = False

    def pause(self):
        """Pause the spinner animation."""
        if self._is_spinning:
            self._paused = True
            # Stop the live display completely to restore terminal echo during input
            if self._live:
                try:
                    self._live.stop()
                    self._live = None
                    # Clear the line to remove any artifacts
                    import sys

                    sys.stdout.write("\r")  # Return to start of line
                    sys.stdout.write("\x1b[K")  # Clear to end of line
                    sys.stdout.flush()
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
            # Restart the live display if it was stopped during pause
            if not self._live:
                try:
                    # Clear any leftover artifacts before starting
                    import sys

                    sys.stdout.write("\r")  # Return to start of line
                    sys.stdout.write("\x1b[K")  # Clear to end of line
                    sys.stdout.flush()

                    # Print blank line before spinner for visual separation
                    self.console.print()

                    self._live = Live(
                        self._generate_spinner_panel(),
                        console=self.console,
                        refresh_per_second=20,
                        transient=True,  # Clear spinner line when stopped
                        auto_refresh=False,
                    )
                    self._live.start()
                except Exception:
                    pass
            else:
                # If live display still exists, clear console state first
                try:
                    # Force Rich to reset any cached console state
                    if hasattr(self.console, "_buffer"):
                        # Clear Rich's internal buffer to prevent artifacts
                        self.console.file.write("\r")  # Return to start
                        self.console.file.write("\x1b[K")  # Clear line
                        self.console.file.flush()

                    self._live.update(self._generate_spinner_panel())
                    self._live.refresh()
                except Exception:
                    pass

    def __enter__(self):
        """Support for context manager."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up when exiting context manager."""
        self.stop()
