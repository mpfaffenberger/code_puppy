"""Unit tests for ConsoleSpinner elapsed time and bell alert behavior."""

from unittest.mock import patch

from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner


def test_get_elapsed_str_empty_when_not_started():
    spinner = ConsoleSpinner()
    spinner._start_time = None
    assert spinner._get_elapsed_str() == ""


def test_get_elapsed_str_formats_seconds_under_minute():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=45):
        assert spinner._get_elapsed_str() == "[0:45]"


def test_get_elapsed_str_formats_minutes_and_seconds():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=125):
        assert spinner._get_elapsed_str() == "[2:05]"


def test_get_elapsed_str_formats_hours_minutes_seconds():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=3725):
        assert spinner._get_elapsed_str() == "[1:02:05]"


def test_check_bell_alert_does_nothing_when_disabled():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    spinner._bell_triggered = False

    with patch("code_puppy.config.get_alert_bell_enabled", return_value=False):
        with patch("sys.stdout") as mock_stdout:
            spinner._check_bell_alert()
            mock_stdout.write.assert_not_called()
            assert spinner._bell_triggered is False


def test_check_bell_alert_does_nothing_before_threshold():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    spinner._bell_triggered = False

    with patch("code_puppy.config.get_alert_bell_enabled", return_value=True):
        with patch("code_puppy.config.get_alert_bell_threshold", return_value=30):
            with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=29):
                with patch("sys.stdout") as mock_stdout:
                    spinner._check_bell_alert()
                    mock_stdout.write.assert_not_called()
                    assert spinner._bell_triggered is False


def test_check_bell_alert_rings_once_after_threshold():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    spinner._bell_triggered = False

    with patch("code_puppy.config.get_alert_bell_enabled", return_value=True):
        with patch("code_puppy.config.get_alert_bell_threshold", return_value=30):
            with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=30):
                with patch("sys.stdout") as mock_stdout:
                    spinner._check_bell_alert()
                    mock_stdout.write.assert_called_once_with("\a")
                    mock_stdout.flush.assert_called_once()
                    assert spinner._bell_triggered is True


def test_check_bell_alert_only_triggers_once_per_session():
    spinner = ConsoleSpinner()
    spinner._start_time = 0
    spinner._bell_triggered = False

    with patch("code_puppy.config.get_alert_bell_enabled", return_value=True):
        with patch("code_puppy.config.get_alert_bell_threshold", return_value=30):
            with patch("code_puppy.messaging.spinner.console_spinner.time.time", return_value=35):
                with patch("sys.stdout") as mock_stdout:
                    spinner._check_bell_alert()
                    spinner._check_bell_alert()

                    mock_stdout.write.assert_called_once_with("\a")
                    assert spinner._bell_triggered is True
