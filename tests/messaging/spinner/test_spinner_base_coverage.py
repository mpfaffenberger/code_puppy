"""Tests for code_puppy.messaging.spinner.spinner_base."""

from unittest.mock import patch

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
    # Pin the emoji to the default so this assertion is hermetic regardless
    # of the developer's actual puppy.cfg.
    with patch(
        "code_puppy.messaging.spinner.spinner_base.get_puppy_emoji",
        return_value="🐶",
    ):
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


def test_current_frame_uses_live_puppy_emoji():
    """current_frame must reflect the user's configured puppy_emoji at
    access time, not the import-time default. This is what makes
    /set puppy_emoji 🦊 flip the spinner without a restart."""
    s = ConcreteSpinner()
    with patch(
        "code_puppy.messaging.spinner.spinner_base.get_puppy_emoji",
        return_value="🦴",
    ):
        frame = s.current_frame
    assert "🦴" in frame
    assert "🐶" not in frame


def test_frames_class_attr_remains_default_for_backward_compat():
    """FRAMES class attribute is the frozen default; live frames render
    via current_frame. Tests / external code that reference FRAMES
    keep working with the canonical 🐶 puppy."""
    assert all("🐶" in f for f in SpinnerBase.FRAMES)
    assert len(SpinnerBase.FRAMES) == 9
