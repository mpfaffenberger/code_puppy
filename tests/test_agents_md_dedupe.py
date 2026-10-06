"""Global AGENTS.md must not load twice when the project path aliases it.

Run from the home directory, ``.code_puppy/AGENTS.md`` *is* the global
``~/.code_puppy/AGENTS.md``. Before the fix ``load_puppy_rules`` read it once
as global rules and again as project rules, so the same text reached the
system prompt twice.
"""

from unittest.mock import patch

import pytest

from code_puppy.agents import _builder
from code_puppy.agents._builder import load_puppy_rules


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home whose ``.code_puppy`` is also the global config dir."""
    config_dir = tmp_path / ".code_puppy"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    with patch.object(_builder, "CONFIG_DIR", str(config_dir)):
        yield tmp_path


def test_global_rules_load_once_when_cwd_is_home(home):
    (home / ".code_puppy" / "AGENTS.md").write_text("global rules")

    rules = load_puppy_rules()

    assert rules == "global rules"


def test_global_rules_load_once_through_a_symlinked_home(tmp_path, monkeypatch):
    real_home = tmp_path / "real"
    config_dir = real_home / ".code_puppy"
    config_dir.mkdir(parents=True)
    (config_dir / "AGENTS.md").write_text("global rules")
    alias = tmp_path / "alias"
    alias.symlink_to(real_home, target_is_directory=True)
    monkeypatch.chdir(alias)

    with patch.object(_builder, "CONFIG_DIR", str(config_dir)):
        rules = load_puppy_rules()

    assert rules == "global rules"


def test_project_symlink_to_global_file_loads_once(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "AGENTS.md").write_text("global rules")
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").symlink_to(config_dir / "AGENTS.md")
    monkeypatch.chdir(project)

    with patch.object(_builder, "CONFIG_DIR", str(config_dir)):
        rules = load_puppy_rules()

    assert rules == "global rules"


def test_root_agents_md_still_loads_after_alias_is_skipped(home):
    (home / ".code_puppy" / "AGENTS.md").write_text("global rules")
    (home / "AGENTS.md").write_text("home project rules")

    rules = load_puppy_rules()

    assert rules == "global rules\n\nhome project rules"


def test_distinct_files_with_identical_text_both_load(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "AGENTS.md").write_text("same rules")
    project = tmp_path / "project"
    (project / ".code_puppy").mkdir(parents=True)
    (project / ".code_puppy" / "AGENTS.md").write_text("same rules")
    monkeypatch.chdir(project)

    with patch.object(_builder, "CONFIG_DIR", str(config_dir)):
        rules = load_puppy_rules()

    assert rules == "same rules\n\nsame rules"
