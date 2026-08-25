"""Installed plugin entry-point discovery."""

from unittest.mock import patch

from code_puppy import plugins


class FakeEntryPoint:
    def __init__(self, name, callback):
        self.name = name
        self._callback = callback

    def load(self):
        return self._callback()


def test_installed_plugins_load_deterministically_with_context():
    events = []
    points = [
        FakeEntryPoint("zeta", lambda: events.append("zeta")),
        FakeEntryPoint("alpha", lambda: events.append("alpha")),
    ]

    with (
        patch.object(plugins, "entry_points", return_value=points),
        patch("code_puppy.config.get_safety_permission_level", return_value="low"),
        patch.object(
            plugins, "set_loading_context", side_effect=lambda name: events.append(name)
        ),
        patch.object(
            plugins, "clear_loading_context", side_effect=lambda: events.append("clear")
        ),
    ):
        assert plugins._load_installed_plugins() == ["alpha", "zeta"]

    assert events == ["alpha", "alpha", "clear", "zeta", "zeta", "clear"]


def test_installed_plugin_failures_are_isolated(caplog):
    def fail():
        raise RuntimeError("boom")

    points = [FakeEntryPoint("broken", fail), FakeEntryPoint("healthy", lambda: None)]
    with (
        patch.object(plugins, "entry_points", return_value=points),
        patch("code_puppy.config.get_safety_permission_level", return_value="low"),
    ):
        assert plugins._load_installed_plugins() == ["healthy"]

    assert "broken" in caplog.text


def test_legacy_loader_skips_installed_duplicate(tmp_path):
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "register_callbacks.py").write_text(
        "raise AssertionError('must not import')", encoding="utf-8"
    )

    assert plugins._load_builtin_plugins(tmp_path, {"duplicate"}) == []
