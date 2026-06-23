"""Tests for the cwd_context plugin.

Covers:
- ``build_file_index`` produces a bounded, deterministic listing.
- Skipped noise (VCS, caches, generated media) is actually skipped.
- Truncation respects the budget and reports the overflow count.
- The plugin's ``load_prompt`` callback emits a fragment with cwd + tree.
- Cache hits are O(1) and re-emit identical output across turns.
- Unreadable cwd degrades gracefully (no exception, just cwd-only fragment).
- Plugin respects BaseAgent prompt-cache invalidation contract (cwd change).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_puppy.plugins.cwd_context import file_index
from code_puppy.plugins.cwd_context.file_index import (
    FileIndex,
    build_file_index,
    get_tree_signature,
)
from code_puppy.plugins.cwd_context.register_callbacks import (
    _build_fragment,
    _on_load_prompt,
    invalidate_cwd_cache,
)


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """Create a small fake project tree under ``tmp_path``.

    Layout::

        tmp_path/
          AGENTS.md
          README.md
          pyproject.toml
          docs/
            PLAN.md
            IDEAS.md
          src/
            app.py
            lib/
              util.py
          .git/                       (skipped)
            HEAD
          __pycache__/                (skipped)
            app.cpython-313.pyc
          .venv/                      (skipped)
            bin/
              python
          code_puppy.png              (skipped, media)
          uv.lock                     (skipped, lockfile)
    """
    (tmp_path / "AGENTS.md").write_text("agents\n")
    (tmp_path / "README.md").write_text("readme\n")
    (tmp_path / "pyproject.toml").write_text("toml\n")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PLAN.md").write_text("plan\n")
    (docs / "IDEAS.md").write_text("ideas\n")

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')\n")
    lib = src / "lib"
    lib.mkdir()
    (lib / "util.py").write_text("# util\n")

    # Stuff that should be skipped.
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.cpython-313.pyc").write_text("binary")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin" / "python").write_text("#!/usr/bin/env python\n")
    (tmp_path / "code_puppy.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "uv.lock").write_text("lock\n")

    return tmp_path


# ---- build_file_index ------------------------------------------------------


def test_build_file_index_lists_top_level(fake_project: Path):
    idx = build_file_index(str(fake_project))
    assert isinstance(idx, FileIndex)
    assert idx.cwd == str(fake_project)
    # Top level: AGENTS.md, README.md, docs/, pyproject.toml, src/
    # Skipped: .git, __pycache__, .venv, code_puppy.png, uv.lock
    top_names = {line.rstrip("/") for line in idx.lines}
    assert "AGENTS.md" in top_names
    assert "README.md" in top_names
    assert "pyproject.toml" in top_names
    assert "docs" in top_names
    assert "src" in top_names
    assert ".git" not in top_names
    assert "__pycache__" not in top_names
    assert ".venv" not in top_names
    assert "code_puppy.png" not in top_names
    assert "uv.lock" not in top_names


def test_build_file_index_recurses_with_depth(fake_project: Path):
    idx = build_file_index(str(fake_project), max_depth=2)
    # Recursive entries should appear (indented).
    joined = "\n".join(idx.lines)
    # docs/PLAN.md and docs/IDEAS.md should be visible at depth 1.
    assert "PLAN.md" in joined
    assert "IDEAS.md" in joined
    # src/lib/util.py is at depth 2 — should be visible.
    assert "util.py" in joined
    # Indentation signals depth.
    indented_lines = [line for line in idx.lines if line.startswith("  ")]
    assert any("PLAN.md" in line for line in indented_lines)
    assert any("util.py" in line for line in indented_lines)


def test_build_file_index_respects_budget():
    """A tiny budget should truncate aggressively."""
    root = Path("/tmp")  # always huge
    idx = build_file_index(str(root), max_depth=1, budget_chars=200, max_entries=5)
    assert idx.truncated is True
    assert len(idx.lines) <= 5
    assert idx.total_entries > len(idx.lines)


def test_build_file_index_returns_none_for_missing_dir(tmp_path: Path):
    assert build_file_index(str(tmp_path / "does_not_exist")) is None


def test_build_file_index_returns_none_for_file(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    assert build_file_index(str(f)) is None


def test_build_file_index_handles_permission_denied(tmp_path: Path, monkeypatch):
    """If scandir raises, the indexer should not crash."""

    def boom(_path):
        raise PermissionError("nope")

    monkeypatch.setattr(file_index.os, "scandir", boom)
    # Should still return a (possibly empty) FileIndex, not raise.
    idx = build_file_index(str(tmp_path))
    assert idx is not None
    assert idx.total_entries == 0


def test_build_file_index_deterministic_order(fake_project: Path):
    """Two calls with the same inputs should produce identical output."""
    a = build_file_index(str(fake_project))
    b = build_file_index(str(fake_project))
    assert a.lines == b.lines


def test_build_file_index_directories_trailing_slash(fake_project: Path):
    idx = build_file_index(str(fake_project), max_depth=0)
    assert any(line.endswith("/") for line in idx.lines)


# ---- get_tree_signature ----------------------------------------------------


def test_tree_signature_changes_on_edit(fake_project: Path):
    s1 = get_tree_signature(str(fake_project))
    # Touch a file deep in the tree.
    (fake_project / "src" / "app.py").write_text("print('changed')\n")
    s2 = get_tree_signature(str(fake_project))
    assert s2 >= s1
    # And actually > s1 because mtime strictly increased.
    assert s2 > s1


def test_tree_signature_handles_missing_cwd(tmp_path: Path):
    # Should not raise.
    sig = get_tree_signature(str(tmp_path / "missing"))
    assert isinstance(sig, float)


# ---- _build_fragment --------------------------------------------------------


def test_build_fragment_contains_cwd_and_tree(fake_project: Path, monkeypatch):
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()
    fragment = _build_fragment(str(fake_project))
    assert fragment is not None
    assert "## Working directory" in fragment
    assert str(fake_project) in fragment
    assert "## File tree" in fragment
    assert "IN_PLACE" not in fragment  # not in this fake
    # Capped size.
    assert len(fragment) <= 5000 + 200  # rough overhead tolerance


def test_build_fragment_truncation_notice(fake_project: Path, monkeypatch):
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()
    # Force truncation with a tiny budget.
    idx = build_file_index(str(fake_project), budget_chars=50, max_entries=2)
    assert idx.truncated
    body = idx.render()
    assert "+" in body and "more" in body


def test_build_fragment_caches_unchanged_tree(fake_project: Path, monkeypatch):
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()
    f1 = _build_fragment(str(fake_project))
    f2 = _build_fragment(str(fake_project))
    assert f1 == f2


def test_build_fragment_invalidates_on_tree_change(fake_project: Path, monkeypatch):
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()
    f1 = _build_fragment(str(fake_project))
    # Edit a tracked file — signature changes, fragment refreshes.
    (fake_project / "AGENTS.md").write_text("agents v2\n")
    sig_after = get_tree_signature(str(fake_project))
    assert isinstance(sig_after, float)
    # Introduce a brand new file so the tree definitively changes.
    (fake_project / "docs" / "NEW.md").write_text("new\n")
    f3 = _build_fragment(str(fake_project))
    assert f3 != f1
    assert isinstance(f1, str)
    assert isinstance(f3, str)


def test_build_fragment_falls_back_to_cwd_only_on_index_failure(
    fake_project: Path, monkeypatch
):
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()

    def _boom(*_a, **_k):
        return None

    monkeypatch.setattr(
        "code_puppy.plugins.cwd_context.register_callbacks.build_file_index",
        _boom,
    )
    frag = _build_fragment(str(fake_project))
    assert frag is not None
    assert "## Working directory" in frag
    # No tree section when index fails.
    assert "## File tree" not in frag


# ---- _on_load_prompt callback ----------------------------------------------


def test_on_load_prompt_uses_real_cwd(monkeypatch):
    invalidate_cwd_cache()
    # _on_load_prompt calls os.getcwd() internally. Stub it.
    monkeypatch.setattr(
        "code_puppy.plugins.cwd_context.register_callbacks.os.getcwd",
        lambda: "/nonexistent_dir_xyz",
    )
    # /nonexistent_dir_xyz doesn't exist → returns None for index → cwd-only.
    frag = _on_load_prompt()
    assert frag is not None
    assert "## Working directory" in frag
    assert "/nonexistent_dir_xyz" in frag
    # No tree block since dir doesn't exist.
    assert "## File tree" not in frag


def test_on_load_prompt_silent_on_oserror(monkeypatch):
    def _boom():
        raise OSError("no cwd")

    monkeypatch.setattr(
        "code_puppy.plugins.cwd_context.register_callbacks.os.getcwd", _boom
    )
    assert _on_load_prompt() is None


def test_on_load_prompt_silent_on_unexpected_failure(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "code_puppy.plugins.cwd_context.register_callbacks._build_fragment", _boom
    )
    assert _on_load_prompt() is None


# ---- integration with BaseAgent dynamic prompt -----------------------------


def test_fragment_lands_in_base_agent_dynamic_prompt(fake_project: Path, monkeypatch):
    """The fragment must show up in the assembled dynamic prompt."""
    from code_puppy.agents.base_agent import BaseAgent

    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache()

    class _Stub(BaseAgent):
        @property
        def name(self):
            return "stub"

        @property
        def display_name(self):
            return "stub"

        @property
        def description(self):
            return "stub"

        def get_system_prompt(self) -> str:
            return "STATIC PROMPT"

        def get_available_tools(self):
            return []

    agent = _Stub()
    # First call → cache miss → populates dynamic.
    sections = agent.get_prompt_sections()
    dynamic = sections.dynamic
    assert "## Working directory" in dynamic
    assert str(fake_project) in dynamic
    assert "## File tree" in dynamic


def test_cwd_change_invalidates_dynamic_cache(fake_project: Path, monkeypatch):
    """BaseAgent should re-emit the dynamic prompt when cwd changes."""
    from code_puppy.agents.base_agent import BaseAgent

    class _Stub(BaseAgent):
        @property
        def name(self):
            return "stub"

        @property
        def display_name(self):
            return "stub"

        @property
        def description(self):
            return "stub"

        def get_system_prompt(self) -> str:
            return "STATIC"

        def get_available_tools(self):
            return []

    agent = _Stub()

    # First cwd.
    monkeypatch.chdir(fake_project)
    invalidate_cwd_cache(str(fake_project))
    agent._dynamic_prompt_cache = None
    agent._dynamic_prompt_cwd = None
    section_a = agent.get_prompt_sections()
    assert str(fake_project) in section_a.dynamic

    # Switch cwd — BaseAgent.get_prompt_sections reads os.getcwd() at call
    # time, so chdir + invalidate dynamic cache should yield a fresh fragment.
    other = fake_project.parent
    monkeypatch.chdir(other)
    invalidate_cwd_cache(str(other))
    agent._dynamic_prompt_cache = None
    agent._dynamic_prompt_cwd = None
    section_b = agent.get_prompt_sections()
    assert str(other) in section_b.dynamic
    assert section_a.dynamic != section_b.dynamic
