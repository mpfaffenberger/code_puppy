"""Project-scoped readers follow the active working directory, not the process cwd.

An ACP editor session carries its own project folder in a ContextVar. Every
chat in one process must read that folder's rules, agents, and sandbox mount,
so a session never sees another project's files.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents import _builder
from code_puppy.agents._builder import load_puppy_rules
from code_puppy.agents._code_mode import build_speculative_code_mode, sandbox_mount_path
from code_puppy.config import AGENTS_MD_MAX_CHARS_DEFAULT, get_project_agents_directory
from code_puppy.tools.common import reset_working_directory, set_working_directory


@pytest.fixture
def process_cwd(tmp_path, monkeypatch):
    """The process folder ``c``, with the global config dir isolated from it."""
    config_dir = tmp_path / "global-config"
    config_dir.mkdir()
    cwd = tmp_path / "c"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    with patch.object(_builder, "CONFIG_DIR", str(config_dir)):
        yield cwd


def _write_rules(folder: Path, layout: str, text: str) -> Path:
    target = (
        folder / ".code_puppy" / "AGENTS.md"
        if layout == "dot_code_puppy"
        else folder / "AGENTS.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def _rules_in(folder: Path) -> str | None:
    token = set_working_directory(str(folder))
    try:
        return load_puppy_rules()
    finally:
        reset_working_directory(token)


@pytest.mark.parametrize("layout", ["root", "dot_code_puppy"])
def test_rules_follow_override_and_fall_back_to_process_folder(process_cwd, layout):
    base = process_cwd.parent
    folder_a, folder_b = base / "a", base / "b"
    for folder in (folder_a, folder_b, process_cwd):
        _write_rules(folder, layout, f"MARKER-{folder.name}")

    assert _rules_in(folder_a) == "MARKER-a"
    assert _rules_in(folder_b) == "MARKER-b"
    assert load_puppy_rules() == "MARKER-c"


async def _read_rules_as_session(folder: Path) -> str | None:
    token = set_working_directory(str(folder))
    try:
        await asyncio.sleep(0)
        rules = load_puppy_rules()
        await asyncio.sleep(0)
        return rules
    finally:
        reset_working_directory(token)


def test_concurrent_sessions_each_read_their_own_rules(process_cwd):
    base = process_cwd.parent
    folder_a, folder_b = base / "a", base / "b"
    _write_rules(folder_a, "root", "MARKER-a")
    _write_rules(folder_b, "root", "MARKER-b")

    async def run_both():
        return await asyncio.gather(
            _read_rules_as_session(folder_a), _read_rules_as_session(folder_b)
        )

    assert asyncio.run(run_both()) == ["MARKER-a", "MARKER-b"]


@pytest.mark.parametrize(
    ("layout", "label"),
    [
        ("root", "project AGENTS.md"),
        ("dot_code_puppy", "project .code_puppy/AGENTS.md"),
    ],
)
def test_truncation_notice_keeps_relative_label(process_cwd, layout, label):
    folder_a = process_cwd.parent / "a"
    _write_rules(folder_a, layout, "x" * (AGENTS_MD_MAX_CHARS_DEFAULT + 10))

    rules = _rules_in(folder_a)

    assert f"The {label} content was truncated" in rules
    assert str(folder_a) not in rules


def test_project_agents_directory_follows_override(process_cwd):
    base = process_cwd.parent
    folder_a, folder_b = base / "a", base / "b"
    (folder_a / ".code_puppy" / "agents").mkdir(parents=True)
    folder_b.mkdir()
    (process_cwd / ".code_puppy" / "agents").mkdir(parents=True)

    token = set_working_directory(str(folder_a))
    try:
        found = get_project_agents_directory()
    finally:
        reset_working_directory(token)
    token = set_working_directory(str(folder_b))
    try:
        missing = get_project_agents_directory()
    finally:
        reset_working_directory(token)

    assert found == os.path.join(str(folder_a), ".code_puppy", "agents")
    assert missing is None


def test_code_mode_mount_follows_override(process_cwd, monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
        lambda: True,
    )
    folder_a = process_cwd.parent / "a"
    folder_a.mkdir()

    token = set_working_directory(str(folder_a))
    try:
        code_mode, *_ = build_speculative_code_mode(["read_file"])
    finally:
        reset_working_directory(token)

    assert os.path.samefile(code_mode.mount.host_path, folder_a)
    assert code_mode.mount.virtual_path == sandbox_mount_path(str(folder_a))
