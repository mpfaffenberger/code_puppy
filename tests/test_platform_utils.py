"""Tests for shared platform detection and UI labels."""

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
    assert platform_utils.startup_banner_text() == "PUP"


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
    assert platform_utils.startup_banner_text() == "CODE PUPPY"
