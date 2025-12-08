import asyncio
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from code_puppy.messaging import emit_info

# Global variable to track current token per second rate
CURRENT_TOKEN_RATE = 0.0


class StatusDisplay:
    """
    Displays real-time status information during model execution,
    including token per second rate and rotating loading messages.
    """

    def __init__(self, console: Console):
        self.console = console
        self.token_count = 0
        self.start_time = None
        self.last_update_time = None
        self.last_token_count = 0
        self.current_rate = 0
        self.is_active = False
        self.task = None
        self.live = None
        self.loading_messages = [
            "Fetching...",
            "Sniffing around...",
            "Wagging tail...",
            "Pawsing for a moment...",
            "Chasing tail...",
            "Digging up results...",
            "Barking at the data...",
            "Rolling over...",
            "Panting with excitement...",
            "Chewing on it...",
            "Prancing along...",
            "Howling at the code...",
            "Snuggling up to the task...",
            "Bounding through data...",
            "Puppy pondering...",
        ]
        self.current_message_index = 0
        self.spinner = Spinner("dots", text="")

    def _calculate_rate(self) -> float:
        """Calculate the current token rate"""
        current_time = time.time()
        if self.last_update_time:
            time_diff = current_time - self.last_update_time
            token_diff = self.token_count - self.last_token_count
            if time_diff > 0:
                rate = token_diff / time_diff
                # Smooth the rate calculation with the current rate
                if self.current_rate > 0:
                    self.current_rate = (self.current_rate * 0.7) + (rate * 0.3)
                else:
                    self.current_rate = rate

                # Only ensure rate is not negative
                self.current_rate = max(0, self.current_rate)

                # Update the global rate for other components to access
                global CURRENT_TOKEN_RATE
                CURRENT_TOKEN_RATE = self.current_rate

        self.last_update_time = current_time
        self.last_token_count = self.token_count
        return self.current_rate

    def update_rate_from_sse(
        self, completion_tokens: int, completion_time: float
    ) -> None:
        """Update the token rate directly using SSE time_info data

        Args:
            completion_tokens: Number of tokens in the completion (from SSE stream)
            completion_time: Time taken for completion in seconds (from SSE stream)
        """
        if completion_time > 0:
            # Using the direct t/s formula: tokens / time
            rate = completion_tokens / completion_time

            # Use a lighter smoothing for this more accurate data
            if self.current_rate > 0:
                self.current_rate = (self.current_rate * 0.3) + (
                    rate * 0.7
                )  # Weight SSE data more heavily
            else:
                self.current_rate = rate

            # Update the global rate
            global CURRENT_TOKEN_RATE
            CURRENT_TOKEN_RATE = self.current_rate

    @staticmethod
    def get_current_rate() -> float:
        """Get the current token rate for use in other components"""
        global CURRENT_TOKEN_RATE
        return CURRENT_TOKEN_RATE

    def update_token_count(self, tokens: int) -> None:
        """Update the token count and recalculate the rate"""
        # Reset timing if this is the first update of a new task
        if self.start_time is None:
            self.start_time = time.time()
            self.last_update_time = self.start_time
            # Reset token counters for new task
            self.last_token_count = 0
            self.current_rate = 0.0
            # Set initial token count
            self.token_count = tokens if tokens >= 0 else 0
            return  # Don't calculate rate on first initialization

        # Allow for incremental updates (common for streaming) or absolute updates
        if tokens > self.token_count or tokens < 0:
            # Incremental update or reset
            self.token_count = tokens if tokens >= 0 else 0
        else:
            # If tokens <= current count but > 0, treat as incremental
            # This handles simulated token streaming
            self.token_count += tokens

        self._calculate_rate()

    def _get_status_panel(self) -> Panel:
        """Generate a status panel with current rate and animated message"""
        rate_text = (
            f"{self.current_rate:.1f} t/s" if self.current_rate > 0 else "Warming up..."
        )

        # Update spinner
        self.spinner.update()

        # Rotate through loading messages every few updates
        if int(time.time() * 2) % 4 == 0:
            self.current_message_index = (self.current_message_index + 1) % len(
                self.loading_messages
            )

        # Create a highly visible status message
        status_text = Text.assemble(
            Text(f"⏳ {rate_text} ", style="bold cyan"),
            str(self.spinner),
            Text(
                f" {self.loading_messages[self.current_message_index]} ⏳",
                style="bold yellow",
            ),
        )

        # Use expanded panel with more visible formatting
        return Panel(
            status_text,
            title="[bold blue]Code Puppy Status[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 2),
        )

    def _get_status_text(self) -> Text:
        """Generate a status text with current rate and animated message"""
        rate_text = (
            f"{self.current_rate:.1f} t/s" if self.current_rate > 0 else "Warming up..."
        )

        # Update spinner
        self.spinner.update()

        # Rotate through loading messages
        self.current_message_index = (self.current_message_index + 1) % len(
            self.loading_messages
        )
        message = self.loading_messages[self.current_message_index]

        # Create a highly visible status text
        return Text.assemble(
            Text(f"⏳ {rate_text} 🐾", style="bold cyan"),
            Text(f" {message}", style="yellow"),
        )

    async def _update_display(self) -> None:
        """Update the display continuously while active using Rich Live display"""
        # Add a newline to ensure we're below the blue bar
        emit_info("")

        # Create a Live display that will update in-place
        with Live(
            self._get_status_text(),
            console=self.console,
            refresh_per_second=2,  # Update twice per second
            transient=False,  # Keep the final state visible
        ) as live:
            # Keep updating the live display while active
            while self.is_active:
                live.update(self._get_status_text())
                await asyncio.sleep(0.5)

    def start(self) -> None:
        """Start the status display"""
        if not self.is_active:
            self.is_active = True
            self.start_time = time.time()
            self.last_update_time = self.start_time
            self.token_count = 0
            self.last_token_count = 0
            self.current_rate = 0
            self.task = asyncio.create_task(self._update_display())

    def stop(self) -> None:
        """Stop the status display"""
        if self.is_active:
            self.is_active = False
            if self.task:
                self.task.cancel()
            self.task = None

            # Print final stats
            elapsed = time.time() - self.start_time if self.start_time else 0
            avg_rate = self.token_count / elapsed if elapsed > 0 else 0
            emit_info(
                f"Completed: {self.token_count} tokens in {elapsed:.1f}s ({avg_rate:.1f} t/s avg)"
            )

            # Reset state
            self.start_time = None
            self.token_count = 0
            self.last_update_time = None
            self.last_token_count = 0
            self.current_rate = 0

            # Reset global rate to 0 to avoid affecting subsequent tasks
            global CURRENT_TOKEN_RATE
            CURRENT_TOKEN_RATE = 0.0
        else:
            # Even if not active, ensure we print stats when stop is called
            # This is for testing purposes
            elapsed = time.time() - self.start_time if self.start_time else 0
            avg_rate = self.token_count / elapsed if elapsed > 0 else 0
            emit_info(
                f"Completed: {self.token_count} tokens in {elapsed:.1f}s ({avg_rate:.1f} t/s avg)"
            )
