from unittest.mock import patch

from code_puppy.messaging.spinner.spinner_base import SpinnerBase


def test_all_presets_are_nonempty_string_frames():
    for name, frames in SpinnerBase.SPINNER_PRESETS.items():
        assert frames, name
        assert all(isinstance(f, str) and f for f in frames), name
        # Width is consistent within a preset (no horizontal jitter).
        assert len({len(f) for f in frames}) == 1, name


def test_get_frames_uses_configured_style():
    with patch("code_puppy.config.get_value", return_value="wave"):
        assert SpinnerBase.get_frames() is SpinnerBase.SPINNER_PRESETS["wave"]


def test_get_frames_falls_back_on_unknown_or_blank():
    default = SpinnerBase.SPINNER_PRESETS[SpinnerBase._DEFAULT_SPINNER]
    for value in (None, "", "does-not-exist"):
        with patch("code_puppy.config.get_value", return_value=value):
            assert SpinnerBase.get_frames() is default


def test_current_frame_cycles_within_resolved_preset():
    with patch("code_puppy.config.get_value", return_value="pulse"):
        # A concrete subclass is needed; ConsoleSpinner registers globally, so
        # build a minimal stand-in instead.
        class _S(SpinnerBase):
            def start(self):
                pass

            def stop(self):
                pass

            def update_frame(self):
                super().update_frame()

        s = _S()
        s._is_spinning = True
        frames = SpinnerBase.SPINNER_PRESETS["pulse"]
        seen = []
        for _ in range(len(frames) + 2):
            seen.append(s.current_frame)
            s.update_frame()
        assert set(seen) <= set(frames)
        assert seen[0] == frames[0]
