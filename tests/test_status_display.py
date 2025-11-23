from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

import code_puppy.status_display
from code_puppy.status_display import CURRENT_TOKEN_RATE, StatusDisplay


class TestStatusDisplay:
    """Comprehensive test suite for StatusDisplay class."""

    @pytest.fixture
    def mock_console(self):
        """Mock Rich console for testing."""
        console = MagicMock()
        console.print = MagicMock()
        return console

    @pytest.fixture
    def status_display(self, mock_console):
        """StatusDisplay instance with mocked console."""
        return StatusDisplay(console=mock_console)

    def test_initialization(self, status_display):
        """Test StatusDisplay initialization."""
        assert status_display.console is not None
        assert status_display.token_count == 0
        assert status_display.start_time is None
        assert status_display.last_update_time is None
        assert status_display.last_token_count == 0
        assert status_display.current_rate == 0
        assert status_display.is_active is False
        assert status_display.task is None
        assert status_display.live is None
        assert len(status_display.loading_messages) == 15
        assert status_display.current_message_index == 0

    def test_initialization_with_custom_console(self):
        """Test StatusDisplay initialization with custom console."""
        custom_console = MagicMock()
        display = StatusDisplay(console=custom_console)
        assert display.console is custom_console

    def test_calculate_rate_first_call(self, status_display):
        """Test rate calculation on first call (no previous data)."""
        # Should not raise error and return 0
        rate = status_display._calculate_rate()
        assert rate == 0

    def test_calculate_rate_with_previous_data(self, status_display):
        """Test rate calculation with previous timing data."""
        # First update to establish baseline (10 tokens)
        status_display.update_token_count(10)

        # Wait a tiny bit and simulate manual time passage
        initial_time = time.time()
        status_display.last_update_time = (
            initial_time - 1.0
        )  # Pretend last update was 1 second ago
        status_display.current_rate = 5.0  # Set existing rate for smoothing

        # Second update with more tokens (20 total = 10 new tokens in ~1 second)
        status_display.token_count = 20

        rate = status_display._calculate_rate()

        # Should calculate new rate and apply smoothing
        # Expected: ~10 tokens / 1 sec = 10 t/s raw, smoothed with existing 5.0
        # Smoothing: 5.0 * 0.7 + 10.0 * 0.3 = 3.5 + 3.0 = 6.5 t/s
        assert rate > 0
        assert rate > 5.0  # Should be higher than the previous rate component
        # Global rate should be updated - check from module namespace
        assert code_puppy.status_display.CURRENT_TOKEN_RATE == rate

    def test_calculate_rate_negative_rates_handled(self, status_display):
        """Test that negative rates are clamped to 0."""
        status_display.last_update_time = time.time() - 1.0
        status_display.last_token_count = 20  # Higher than current
        status_display.token_count = 10
        status_display.current_rate = 5.0

        rate = status_display._calculate_rate()
        assert rate >= 0
        assert code_puppy.status_display.CURRENT_TOKEN_RATE >= 0

    def test_update_rate_from_sse(self, status_display):
        """Test updating token rate from SSE stream data."""
        status_display.update_rate_from_sse(completion_tokens=100, completion_time=2.0)

        assert status_display.current_rate == 50  # 100/2 = 50
        assert code_puppy.status_display.CURRENT_TOKEN_RATE == 50

    def test_update_rate_from_sse_with_smoothing(self, status_display):
        """Test SSE rate updates with smoothing."""
        status_display.current_rate = 10.0

        status_display.update_rate_from_sse(completion_tokens=20, completion_time=1.0)

        # Should be smoothed: 10.0 * 0.3 + 20.0 * 0.7 = 17.0
        expected_rate = 10.0 * 0.3 + 20.0 * 0.7
        assert abs(status_display.current_rate - expected_rate) < 0.001

    def test_update_rate_from_sse_zero_time(self, status_display):
        """Test SSE rate update with zero completion time."""
        original_rate = status_display.current_rate

        status_display.update_rate_from_sse(completion_tokens=100, completion_time=0.0)

        # Should not update rate
        assert status_display.current_rate == original_rate

    def test_get_current_rate_static(self):
        """Test static method for getting current rate."""
        # Set global rate
        import code_puppy.status_display

        original_rate = CURRENT_TOKEN_RATE
        try:
            code_puppy.status_display.CURRENT_TOKEN_RATE = 42.0
            assert StatusDisplay.get_current_rate() == 42.0
        finally:
            code_puppy.status_display.CURRENT_TOKEN_RATE = original_rate

    def test_update_token_count_first_update(self, status_display):
        """Test token count update on first call."""
        status_display.update_token_count(10)

        assert status_display.token_count == 10
        assert status_display.start_time is not None
        assert status_display.last_update_time is not None
        assert status_display.last_token_count == 0
        assert status_display.current_rate >= 0

    def test_update_token_count_incremental(self, status_display):
        """Test incremental token count updates (streaming)."""
        # First update
        status_display.update_token_count(5)
        first_time = status_display.start_time

        # Second incremental update
        status_display.update_token_count(3)  # Should add to existing

        assert status_display.token_count == 8
        assert status_display.start_time == first_time

    def test_update_token_count_absolute_higher(self, status_display):
        """Test absolute token count update with higher value."""
        status_display.update_token_count(5)
        status_display.update_token_count(15)  # Higher, should replace

        assert status_display.token_count == 15

    def test_update_token_count_reset_negative(self, status_display):
        """Test token count reset with negative value."""
        status_display.update_token_count(10)
        status_display.update_token_count(-1)  # Should reset to 0

        assert status_display.token_count == 0

    def test_get_status_panel_with_rate(self, status_display):
        """Test status panel generation with non-zero rate."""
        status_display.current_rate = 25.5
        status_display.current_message_index = 0

        panel = status_display._get_status_panel()

        assert panel is not None
        # Extract text from panel renderable
        panel_content = str(panel.renderable)
        assert "25.5 t/s" in panel_content
        # Check that the message contains loading message content
        found_message = False
        for msg in status_display.loading_messages:
            if msg in panel_content:
                found_message = True
                break
        assert found_message, f"No loading message found in: {panel_content}"

    def test_get_status_panel_warming_up(self, status_display):
        """Test status panel generation when warming up (zero rate)."""
        status_display.current_rate = 0.0

        panel = status_display._get_status_panel()

        assert panel is not None
        # Extract text from panel renderable
        panel_content = str(panel.renderable)
        assert "Warming up..." in panel_content

    def test_get_status_text_with_rate(self, status_display):
        """Test status text generation with non-zero rate."""
        status_display.current_rate = 30.0
        status_display.current_message_index = 1

        text = status_display._get_status_text()

        text_str = str(text)
        assert "30.0 t/s" in text_str
        assert "🐾" in text_str  # Paw emoji
        # Check that the message contains loading message content
        found_message = False
        for msg in status_display.loading_messages:
            if msg in text_str:
                found_message = True
                break
        assert found_message, f"No loading message found in: {text_str}"

    def test_get_status_text_warming_up(self, status_display):
        """Test status text generation when warming up."""
        status_display.current_rate = 0.0

        text = status_display._get_status_text()

        text_str = str(text)
        assert "Warming up..." in text_str

    def test_status_message_rotation(self, status_display):
        """Test that status messages rotate properly."""
        messages_count = len(status_display.loading_messages)

        # Simulate message rotation by calling multiple times
        for i in range(messages_count + 2):
            text = status_display._get_status_text()

            # Message should be from the list
            text_str = str(text)
            found_message = None
            for msg in status_display.loading_messages:
                if msg in text_str:
                    found_message = msg
                    break
            assert found_message is not None

    @pytest.mark.asyncio
    async def test_start(self, status_display):
        """Test starting the status display."""
        assert not status_display.is_active

        with patch("code_puppy.status_display.asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            status_display.start()

            assert status_display.is_active
            assert status_display.start_time is not None
            assert status_display.last_update_time is not None
            assert status_display.token_count == 0
            assert status_display.last_token_count == 0
            assert status_display.current_rate == 0
            assert status_display.task is mock_task

    @pytest.mark.asyncio
    async def test_start_already_active(self, status_display):
        """Test starting when already active."""
        with patch("code_puppy.status_display.asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            status_display.start()
            original_task = status_display.task

            status_display.start()  # Should not create new task

            assert status_display.task is original_task

    @pytest.mark.asyncio
    async def test_stop_after_start(self, status_display):
        """Test stopping the status display after starting."""
        with patch("code_puppy.status_display.asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            status_display.start()
            status_display.stop()

            assert not status_display.is_active
            assert status_display.task is None
            # Should print final stats
            status_display.console.print.assert_called()

            # Check that final stats message contains expected info
            call_args = status_display.console.print.call_args[0][0]
            assert "Completed:" in str(call_args)
            assert "tokens" in str(call_args)

            # State should be reset
            assert status_display.start_time is None
            assert status_display.token_count == 0
            assert code_puppy.status_display.CURRENT_TOKEN_RATE == 0.0

    def test_stop_without_start(self, status_display):
        """Test stopping when not active."""
        status_display.stop()  # Should not raise error

        assert not status_display.is_active
        assert status_display.task is None

    @pytest.mark.asyncio
    async def test_stop_with_cancellation(self, status_display):
        """Test stopping handles task cancellation properly."""
        with patch("code_puppy.status_display.asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            status_display.start()

            # Should stop cleanly (task cancellation happens internally)
            status_display.stop()

            # Should be able to stop cleanly
            assert not status_display.is_active
            assert status_display.task is None
            mock_task.cancel.assert_called_once()

    def test_stop_calculates_average_rate(self, status_display):
        """Test that stop calculates and displays average rate."""
        # Set up the stop scenario manually
        status_display.token_count = 50
        status_display.start_time = 1.0

        status_display.stop()

        # Should have called console.print
        status_display.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_update_display_integration(self, status_display):
        """Test the display update loop (integration test)."""
        with (
            patch("code_puppy.status_display.asyncio.create_task"),
            patch("code_puppy.status_display.Live") as mock_live,
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value.__enter__.return_value = mock_live_instance

            status_display.start()
            status_display.stop()

            # Console should have been used
            assert status_display.console.print.called

    def test_spinner_in_status_panel(self, status_display):
        """Test that spinner is included and updated in status panel."""
        status_display.current_rate = 10.0

        panel1 = status_display._get_status_panel()
        panel2 = status_display._get_status_panel()

        # Both should be valid panel objects
        assert panel1 is not None
        assert panel2 is not None

    def test_loading_messages_content(self):
        """Test that loading messages are appropriate and varied."""
        display = StatusDisplay(console=MagicMock())

        messages = display.loading_messages
        assert len(messages) > 0

        # All messages should be non-empty strings
        for msg in messages:
            assert isinstance(msg, str)
            assert len(msg.strip()) > 0

        # Should have variety (not all the same)
        assert len(set(messages)) > 1

        # Should be puppy-themed
        puppy_terms = ["puppy", "paws", "tail", "barking", "panting"]
        combined_text = " ".join(messages).lower()
        has_puppy_theme = any(term in combined_text for term in puppy_terms)
        assert has_puppy_theme

    def test_concurrent_rate_updates(self, status_display):
        """Test handling concurrent rate updates."""
        import threading

        def update_tokens(count):
            for i in range(10):
                status_display.update_token_count(count + i)
                time.sleep(0.001)

        # Start multiple threads updating tokens
        threads = [
            threading.Thread(target=update_tokens, args=(i * 10,)) for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash and have reasonable final state
        assert status_display.token_count >= 0
        assert status_display.current_rate >= 0

    def test_large_token_numbers(self, status_display):
        """Test handling of large token numbers."""
        large_number = 1_000_000
        status_display.update_token_count(large_number)

        # Should handle large numbers without overflow
        assert status_display.token_count == large_number

        # Rate calculation should work
        rate = status_display._calculate_rate()
        assert isinstance(rate, (int, float))
        assert rate >= 0

    def test_zero_time_diff_handling(self, status_display):
        """Test handling of zero time difference in rate calculation."""
        current_time = time.time()
        status_display.last_update_time = current_time
        status_display.last_token_count = 10
        status_display.token_count = 20

        # Should not crash with zero time diff
        rate = status_display._calculate_rate()
        assert isinstance(rate, (int, float))

    def test_global_rate_reset_on_stop(self, status_display):
        """Test that global rate is reset to 0 on stop."""
        # Need to start the display first for stop() to work properly
        with patch("code_puppy.status_display.asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task
            status_display.start()

        # Set global rate to non-zero
        status_display.update_rate_from_sse(10, 1.0)

        status_display.stop()

        # Global rate should be reset
        assert code_puppy.status_display.CURRENT_TOKEN_RATE == 0.0

    def test_panel_styling(self, status_display):
        """Test that status panel has appropriate styling."""
        status_display.current_rate = 15.0

        panel = status_display._get_status_panel()

        # Check panel configuration
        assert panel.border_style == "bright_blue"
        assert panel.expand is False
        assert panel.padding == (1, 2)

        # Check title styling exists
        assert panel.title == "[bold blue]Code Puppy Status[/bold blue]"

    def test_memory_efficiency(self, status_display):
        """Test that status display doesn't accumulate memory unnecessarily."""
        # Update many times
        for i in range(1000):
            status_display.update_token_count(i)
            status_display._calculate_rate()

        # State should remain bounded
        assert status_display.token_count < 2000  # Should not grow indefinitely
        assert status_display.current_rate >= 0

        # Internal state should be minimal
        assert hasattr(status_display, "token_count")
        assert hasattr(status_display, "current_rate")
        assert hasattr(status_display, "start_time")
        assert hasattr(status_display, "last_update_time")
        assert hasattr(status_display, "last_token_count")
