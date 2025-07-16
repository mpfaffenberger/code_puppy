"""
Textual spinner implementation for TUI mode.
"""

from textual.widgets import Static

from .spinner_base import SpinnerBase


class TextualSpinner(Static):
    """A textual spinner widget based on the SimpleSpinnerWidget."""
    
    # Use the frames from SpinnerBase
    FRAMES = SpinnerBase.FRAMES
    MESSAGE = SpinnerBase.MESSAGE
    
    def __init__(self, **kwargs):
        """Initialize the textual spinner."""
        super().__init__("", **kwargs)
        self._frame_index = 0
        self._is_spinning = False
        self._timer = None
        
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
        
    def update_frame(self):
        """Update to the next frame."""
        if self._is_spinning:
            self._frame_index = (self._frame_index + 1) % len(self.FRAMES)
        
    def update_frame_display(self):
        """Update the display with the current frame."""
        if self._is_spinning:
            self.update_frame()
            current_frame = self.FRAMES[self._frame_index]
            self.update(
                f"[bold cyan]{self.MESSAGE}[/bold cyan][bold cyan]{current_frame}[/bold cyan]"
            )