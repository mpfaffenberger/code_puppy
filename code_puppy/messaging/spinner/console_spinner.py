"""
Console spinner implementation for CLI mode using Rich's Live Display.
"""

import threading
import time
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich import box
from rich.panel import Panel

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
            transient=True
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
        
    def update_frame(self):
        """Update to the next frame."""
        super().update_frame()
        
    def _generate_spinner_panel(self):
        """Generate a Rich panel containing the spinner text."""
        if self._paused:
            return Text("")
        
        text = Text()
        text.append("🐶 Puppy is thinking... ", style="bold cyan")
        text.append(self.current_frame, style="bold cyan")
        
        # Return a simple Text object instead of a Panel for a cleaner look
        return text
        
    def _update_spinner(self):
        """Update the spinner in a background thread."""
        try:
            while not self._stop_event.is_set():
                # Update the frame
                self.update_frame()
                
                # Update the live display
                if self._live and not self._paused:
                    self._live.update(self._generate_spinner_panel())
                
                # Short sleep to control animation speed
                time.sleep(0.1)
        except Exception as e:
            print(f"\nSpinner error: {e}")
            self._is_spinning = False
    
    def pause(self):
        """Pause the spinner animation."""
        if self._is_spinning:
            self._paused = True
            # Update the live display to hide the spinner
            if self._live:
                self._live.update(Text(""))
    
    def resume(self):
        """Resume the spinner animation."""
        if self._is_spinning and self._paused:
            self._paused = False
            # Force an immediate update to show the spinner again
            if self._live:
                self._live.update(self._generate_spinner_panel())
    
    def __enter__(self):
        """Support for context manager."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up when exiting context manager."""
        self.stop()