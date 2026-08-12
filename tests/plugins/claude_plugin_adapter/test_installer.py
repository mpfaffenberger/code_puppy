from unittest.mock import patch

from code_puppy.plugins.claude_plugin_adapter.installer import (
    install_plugin,
    uninstall_plugin,
)
from code_puppy.plugins.claude_plugin_adapter import register_callbacks


def test_install_plugin(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    mock_plugin_dir.mkdir(parents=True)

    mock_source_dir = tmp_path / "source_plugin"
    mock_source_dir.mkdir()
    (mock_source_dir / "somefile").write_text("hello")

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.get_claude_plugins_dir",
        lambda: mock_plugin_dir,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer._sync_plugin",
        lambda x: None,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer._trigger_agent_reload",
        lambda: None,
    )

    assert install_plugin(str(mock_source_dir)) is True

    dest = mock_plugin_dir / "source_plugin"
    assert dest.exists()
    assert (dest / "somefile").exists()


def test_uninstall_plugin(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    plugin_name = "test_plugin"
    dest = mock_plugin_dir / plugin_name
    dest.mkdir(parents=True)

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.get_installed_plugins",
        lambda: [plugin_name],
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.get_claude_plugins_dir",
        lambda: mock_plugin_dir,
    )

    def mock_sync(name, uninstall=False):
        assert uninstall is True
        assert name == plugin_name

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.sync_agents_adapter",
        mock_sync,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.sync_mcp_adapter", mock_sync
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer.sync_skills_adapter",
        mock_sync,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.installer._trigger_agent_reload",
        lambda: None,
    )

    assert uninstall_plugin(plugin_name) is True
    assert not dest.exists()


def test_custom_command():
    assert register_callbacks._custom_command("other", "") is None
    assert (
        register_callbacks._custom_command("plugin", "")
        == "Usage: /plugin install <path> | /plugin uninstall <name>"
    )

    with patch(
        "code_puppy.plugins.claude_plugin_adapter.register_callbacks.install_plugin"
    ) as mock_install:
        assert register_callbacks._custom_command("plugin", "install mypath") is True
        mock_install.assert_called_with("mypath")

    with patch(
        "code_puppy.plugins.claude_plugin_adapter.register_callbacks.uninstall_plugin"
    ) as mock_uninstall:
        assert register_callbacks._custom_command("plugin", "uninstall myname") is True
        mock_uninstall.assert_called_with("myname")
