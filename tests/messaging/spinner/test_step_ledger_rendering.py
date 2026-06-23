"""Tests for the in-place steps ledger rendering inside the Live panel."""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
from code_puppy.messaging.spinner.spinner_base import SpinnerBase
from code_puppy.messaging.step_ledger import configure_ledger, get_ledger


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


@pytest.fixture(autouse=True)
def _reset_user_input():
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=False,
    ):
        yield


@pytest.fixture(autouse=True)
def _clean_ledger():
    ledger = configure_ledger(max_visible=5)
    ledger.reset()
    SpinnerBase.set_ledger_active(False)
    SpinnerBase.clear_activity()
    yield
    ledger.reset()
    SpinnerBase.set_ledger_active(False)
    SpinnerBase.clear_activity()


def test_ledger_mode_renders_active_and_recent(console):
    """When ledger mode is on, the spinner panel shows the active row
    and the last completed rows together."""
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    ledger = get_ledger()
    ledger.push_completed("✓ first step")
    ledger.begin_active("Running: pytest")
    SpinnerBase.set_ledger_active(True)

    text = spinner._generate_spinner_panel()
    plain = text.plain
    assert "Running: pytest" in plain
    assert "✓ first step" in plain

    spinner.stop()


def test_ledger_mode_with_empty_ledger_falls_back(console):
    """Empty ledger + ledger mode on falls back to the thinking line so
    the user still sees a spinner."""
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    SpinnerBase.set_ledger_active(True)
    # ledger has no rows and no active step
    text = spinner._generate_spinner_panel()
    plain = text.plain
    # Falls through to the standard thinking line.
    assert "thinking" in plain.lower()
    spinner.stop()


def test_ledger_off_uses_activity_label(console):
    """With ledger off, the standard activity label is rendered."""
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    SpinnerBase.set_activity("Running: tests")
    text = spinner._generate_spinner_panel()
    plain = text.plain
    assert "Running: tests" in plain
    spinner.stop()
    SpinnerBase.clear_activity()


def test_ledger_renders_completed_rows_dim(console):
    """Completed rows are styled dim so the active row stands out."""
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    ledger = get_ledger()
    ledger.push_completed("✓ file read")
    SpinnerBase.set_ledger_active(True)
    text = spinner._generate_spinner_panel()
    # At least one styled "dim" span should be present for the completed row.
    styles = {span.style for span in text.spans}
    assert "dim" in styles
    spinner.stop()