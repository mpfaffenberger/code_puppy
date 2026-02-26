"""Tests for code_puppy.messaging.spinner.spinner_base."""

from code_puppy.messaging.spinner.spinner_base import SpinnerBase


class ConcreteSpinner(SpinnerBase):
    """Minimal concrete implementation for testing."""

    def start(self):
        super().start()

    def stop(self):
        super().stop()

    def update_frame(self):
        super().update_frame()


def test_start_stop():
    s = ConcreteSpinner()
    assert not s.is_spinning
    s.start()
    assert s.is_spinning
    assert s._frame_index == 0
    s.stop()
    assert not s.is_spinning


def test_update_frame():
    s = ConcreteSpinner()
    s.start()
    s.update_frame()
    assert s._frame_index == 1
    s.update_frame()
    assert s._frame_index == 2


def test_update_frame_not_spinning():
    s = ConcreteSpinner()
    s.update_frame()
    assert s._frame_index == 0


def test_current_frame():
    s = ConcreteSpinner()
    assert s.current_frame == SpinnerBase.FRAMES[0]


def test_context_info():
    SpinnerBase.set_context_info("test info")
    assert SpinnerBase.get_context_info() == "test info"
    SpinnerBase.clear_context_info()
    assert SpinnerBase.get_context_info() == ""


def test_format_context_info():
    result = SpinnerBase.format_context_info(5000, 10000, 0.5)
    assert "5,000" in result
    assert "10,000" in result
    assert "50.0%" in result


def test_format_context_info_zero_capacity():
    result = SpinnerBase.format_context_info(0, 0, 0)
    assert result == ""


def test_frame_wraps_around():
    s = ConcreteSpinner()
    s.start()
    for _ in range(len(SpinnerBase.FRAMES) + 1):
        s.update_frame()
    assert s._frame_index == 1  # Wrapped
