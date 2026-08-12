from code_puppy.plugins.claude_plugin_adapter.adapters.skills import sync_skills_adapter


def test_sync_skills_adapter_exists(monkeypatch, tmp_path):
    # Setup mock plugin dir
    mock_plugin_dir = tmp_path / "claude_plugins"
    plugin_name = "test-plugin"
    skills_dir = mock_plugin_dir / plugin_name / "skills"
    skills_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.skills.get_claude_plugins_dir",
        lambda: mock_plugin_dir,
    )

    mock_add_skill = []

    def fake_add_skill_directory(path: str) -> bool:
        mock_add_skill.append(path)
        return True

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.skills.add_skill_directory",
        fake_add_skill_directory,
    )

    sync_skills_adapter(plugin_name)

    assert len(mock_add_skill) == 1
    assert mock_add_skill[0] == str(skills_dir)


def test_sync_skills_adapter_not_exists(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    plugin_name = "test-plugin"
    # Do not create skills dir

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.skills.get_claude_plugins_dir",
        lambda: mock_plugin_dir,
    )

    mock_add_skill = []

    def fake_add_skill_directory(path: str) -> bool:
        mock_add_skill.append(path)
        return True

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.skills.add_skill_directory",
        fake_add_skill_directory,
    )

    sync_skills_adapter(plugin_name)

    assert len(mock_add_skill) == 0
