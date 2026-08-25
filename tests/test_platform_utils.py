"""Tests for shared platform detection and UI labels."""

import os

import pytest

from code_puppy import platform_utils

_ANDROID_ENV_VARS = ("TERMUX_VERSION", "ANDROID_ROOT", "ANDROID_DATA")


def _clear_android_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ANDROID_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("platform_name", ["android", "android-30"])
def test_android_platform_names_are_detected(monkeypatch, platform_name):
    _clear_android_environment(monkeypatch)
    monkeypatch.setattr(platform_utils.sys, "platform", platform_name)

    assert platform_utils.is_android() is True


def test_termux_marker_is_detected_on_linux(monkeypatch):
    _clear_android_environment(monkeypatch)
    monkeypatch.setattr(platform_utils.sys, "platform", "linux")
    monkeypatch.setenv("TERMUX_VERSION", "0.118")

    assert platform_utils.is_android() is True


def test_android_environment_pair_is_detected(monkeypatch):
    _clear_android_environment(monkeypatch)
    monkeypatch.setattr(platform_utils.sys, "platform", "linux")
    monkeypatch.setenv("ANDROID_ROOT", "/system")
    monkeypatch.setenv("ANDROID_DATA", "/data")

    assert platform_utils.is_android() is True


def test_partial_android_environment_is_not_detected(monkeypatch):
    _clear_android_environment(monkeypatch)
    monkeypatch.setattr(platform_utils.sys, "platform", "linux")
    monkeypatch.setenv("ANDROID_ROOT", "/system")

    assert platform_utils.is_android() is False


class TestStartupBannerText:
    """Banner selection is width-based, not platform-based."""

    def test_wide_terminal_gets_full_banner(self):
        assert platform_utils.startup_banner_text(120) == "CODE PUPPY"

    def test_narrow_terminal_gets_compact_banner(self):
        assert platform_utils.startup_banner_text(78) == "PUP"

    def test_threshold_matches_baked_figlet_width(self):
        import pyfiglet

        rendered = pyfiglet.figlet_format("CODE PUPPY", font="ansi_shadow", width=300)
        width = max(len(line.rstrip()) for line in rendered.splitlines())
        assert width == platform_utils._FULL_BANNER_WIDTH
        assert platform_utils.startup_banner_text(width) == "CODE PUPPY"
        assert platform_utils.startup_banner_text(width - 1) == "PUP"

    def test_defaults_to_detected_terminal_width(self, monkeypatch):
        monkeypatch.setattr(
            platform_utils.shutil,
            "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((50, 24)),
        )
        assert platform_utils.startup_banner_text() == "PUP"
