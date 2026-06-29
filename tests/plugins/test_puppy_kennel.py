"""Tests for the puppy_kennel plugin.

Covers:
* schema initialization is idempotent
* recorder writes a single drawer to the repo wing only (no dual-write)
* FTS5 search finds drawers, optionally scoped to a wing
* passive recall block builds a sensible system-prompt fragment
* empty/garbage inputs are no-ops, not crashes
* multi-process concurrent writes don't corrupt or lose data

The multi-process test is the headline guarantee — it's the whole reason
we picked SQLite + WAL over ChromaDB.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

import pytest


@pytest.fixture
def kennel_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Throwaway kennel directory per test, isolated from the user's real one."""
    root = tmp_path / "kennel"
    monkeypatch.setenv("PUPPY_KENNEL_ROOT", str(root))
    # Force the kennel ON for the duration of the test, independent of the
    # developer's real puppy.cfg. This env override is also inherited across
    # the multiprocessing *spawn* boundary, so child workers in
    # ``test_concurrent_multiprocess_writes_do_not_corrupt`` don't silently
    # no-op when the dev happens to have ``kennel_enabled = false`` locally.
    monkeypatch.setenv("PUPPY_KENNEL_ENABLED", "true")

    # Every submodule binds paths/flags from ``config`` (and ``state``) AT
    # IMPORT TIME. If the plugin was already imported earlier in the test
    # session (e.g. via another plugin test) those bindings point at the
    # user's REAL kennel — which may even be disabled — and the recorder
    # silently no-ops. Reload the whole graph in dependency order so the temp
    # root + a fresh (enabled) state win regardless of import history.
    import importlib

    from code_puppy.plugins.puppy_kennel import config as kennel_config
    from code_puppy.plugins.puppy_kennel import kennel as kennel_mod
    from code_puppy.plugins.puppy_kennel import packer as packer_mod
    from code_puppy.plugins.puppy_kennel import recorder as recorder_mod
    from code_puppy.plugins.puppy_kennel import retriever as retriever_mod
    from code_puppy.plugins.puppy_kennel import schema as schema_mod
    from code_puppy.plugins.puppy_kennel import state as state_mod
    from code_puppy.plugins.puppy_kennel import wings as wings_mod

    for mod in (
        kennel_config,  # base: paths + budgets
        schema_mod,  # SQL constants
        state_mod,  # is_enabled() reads kennel_enabled from puppy.cfg
        wings_mod,  # cwd/repo helpers
        kennel_mod,  # DB_PATH <- config
        packer_mod,  # <- kennel, config, wings
        recorder_mod,  # <- kennel, state, wings
        retriever_mod,  # <- packer, state
    ):
        importlib.reload(mod)

    kennel_mod.initialize()
    return root


def test_initialize_creates_db(kennel_root: Path) -> None:
    assert (kennel_root / "kennel.db").exists()


def test_initialize_is_idempotent(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel

    kennel.initialize()
    kennel.initialize()  # second call must not raise


def test_recorder_writes_only_to_repo_wing(kennel_root: Path) -> None:
    """Phase 5: autosave goes to the repo wing only, not the agent diary."""
    from code_puppy.plugins.puppy_kennel import kennel, recorder

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="test-model",
        session_id="sess-abc",
        success=True,
        response_text="Hello from the kennel.",
    )
    # Single write — no more dual-write.
    assert kennel.count_drawers() == 1
    wings = kennel.list_wings()
    assert any(w.startswith("repo:") for w in wings)
    assert "agent:code-puppy" not in wings


def test_recorder_skips_blank_or_failed_runs(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, recorder

    recorder.record_run_end(
        agent_name="x", model_name="m", success=True, response_text=""
    )
    recorder.record_run_end(
        agent_name="x", model_name="m", success=True, response_text="   "
    )
    recorder.record_run_end(
        agent_name="x", model_name="m", success=False, response_text="boom"
    )
    assert kennel.count_drawers() == 0


def test_fts5_search_finds_drawers(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, recorder

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="We picked SQLite FTS5 because Chroma corrupts on concurrent writes.",
    )
    hits = kennel.search_drawers("chroma corrupts", limit=5)
    assert len(hits) >= 1
    assert "chroma" in hits[0].content.lower()


def test_fts5_search_scoped_to_wing(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, recorder, wings

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="The fox jumps over the lazy puppy.",
    )
    repo_w = wings.repo_wing()
    agent_w = wings.agent_wing("code-puppy")
    # Autosave only lands in the repo wing now.
    assert len(kennel.search_drawers("fox", wing_name=repo_w)) == 1
    assert len(kennel.search_drawers("fox", wing_name=agent_w)) == 0
    assert len(kennel.search_drawers("fox", wing_name="agent:nobody")) == 0


def test_search_handles_garbage_input(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel

    assert kennel.search_drawers("") == []
    assert kennel.search_drawers("   ") == []
    # FTS5 would normally choke on bare operator chars; sanitizer should rescue us.
    assert kennel.search_drawers('"":*()') == []


def test_passive_recall_block_returns_none_when_empty(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import retriever

    assert retriever.build_recall_block() is None


def test_passive_recall_block_renders_when_drawers_exist(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import recorder, retriever

    # Has to exceed MIN_DRAWER_CHARS (80) or the packer correctly drops it.
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text=(
            "A small but mighty drawer that nonetheless contains enough "
            "verbatim content to clear the noise threshold and earn its "
            "place in the recall block."
        ),
    )
    block = retriever.build_recall_block()
    assert block is not None
    assert "Puppy Kennel" in block
    assert "code-puppy" in block


def test_wing_naming_conventions() -> None:
    from code_puppy.plugins.puppy_kennel import wings

    assert wings.agent_wing("code-puppy") == "agent:code-puppy"
    assert wings.agent_wing("") == "agent:unknown"
    assert wings.agent_wing(None) == "agent:unknown"  # type: ignore[arg-type]
    assert wings.repo_wing("/tmp").startswith("repo:")
    assert wings.USER_WING == "user:default"


def test_repo_wing_resolves_worktree_to_main_repo(tmp_path: Path) -> None:
    """Worktrees use a .git *file* pointing to the main repo — wing must resolve to main."""
    from code_puppy.plugins.puppy_kennel import wings

    # Set up a fake main repo
    main_repo = tmp_path / "main-repo"
    main_git = main_repo / ".git"
    main_git.mkdir(parents=True)
    worktrees_dir = main_git / "worktrees" / "feature-branch"
    worktrees_dir.mkdir(parents=True)

    # Set up a fake worktree with a .git file
    worktree = tmp_path / "main-repo-feature-branch"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text(f"gitdir: {worktrees_dir}\n")

    assert wings.repo_wing(worktree) == f"repo:{main_repo.resolve()}"
    # Main repo should still resolve to itself
    assert wings.repo_wing(main_repo) == f"repo:{main_repo.resolve()}"


def test_repo_wing_worktree_relative_gitdir(tmp_path: Path) -> None:
    """Worktree .git files can have relative gitdir paths."""
    from code_puppy.plugins.puppy_kennel import wings

    main_repo = tmp_path / "repos" / "my-project"
    main_git = main_repo / ".git"
    main_git.mkdir(parents=True)
    worktrees_dir = main_git / "worktrees" / "hotfix"
    worktrees_dir.mkdir(parents=True)

    worktree = tmp_path / "repos" / "my-project-hotfix"
    worktree.mkdir(parents=True)
    git_file = worktree / ".git"
    # Relative path from worktree to main repo's .git/worktrees/hotfix
    git_file.write_text("gitdir: ../my-project/.git/worktrees/hotfix\n")

    assert wings.repo_wing(worktree) == f"repo:{main_repo.resolve()}"


def test_repo_wing_malformed_git_file_falls_back(tmp_path: Path) -> None:
    """If .git file is malformed, fall back to worktree dir itself."""
    from code_puppy.plugins.puppy_kennel import wings

    worktree = tmp_path / "broken-worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("garbage content\n")

    # Should fall back to the directory containing .git
    assert wings.repo_wing(worktree) == f"repo:{worktree.resolve()}"


def test_repo_wing_subdirectory_in_worktree(tmp_path: Path) -> None:
    """Querying from a subdirectory inside a worktree resolves to main repo."""
    from code_puppy.plugins.puppy_kennel import wings

    main_repo = tmp_path / "main"
    main_git = main_repo / ".git"
    main_git.mkdir(parents=True)
    worktrees_dir = main_git / "worktrees" / "dev"
    worktrees_dir.mkdir(parents=True)

    worktree = tmp_path / "main-dev"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {worktrees_dir}\n")
    subdir = worktree / "src" / "com" / "deep"
    subdir.mkdir(parents=True)

    assert wings.repo_wing(subdir) == f"repo:{main_repo.resolve()}"


def test_repo_wing_binary_git_file_falls_back(tmp_path: Path) -> None:
    """A .git file with non-UTF-8 bytes must not crash — falls back gracefully."""
    from code_puppy.plugins.puppy_kennel import wings

    worktree = tmp_path / "corrupt-worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_bytes(b"\xff\xfe\x00garbage\x80\x81")

    # Should not raise, falls back to the directory itself
    assert wings.repo_wing(worktree) == f"repo:{worktree.resolve()}"


def test_repo_wing_submodule_stays_siloed(tmp_path: Path) -> None:
    """Submodules should NOT merge into the superproject's wing."""
    from code_puppy.plugins.puppy_kennel import wings

    # Set up a fake superproject
    superproject = tmp_path / "superproject"
    super_git = superproject / ".git"
    super_git.mkdir(parents=True)
    modules_dir = super_git / "modules" / "my-submodule"
    modules_dir.mkdir(parents=True)

    # Set up a fake submodule with a .git file pointing to modules/
    submodule = superproject / "vendor" / "my-submodule"
    submodule.mkdir(parents=True)
    git_file = submodule / ".git"
    git_file.write_text(f"gitdir: {modules_dir}\n")

    # Submodule should keep its OWN wing, not merge into superproject
    result = wings.repo_wing(submodule)
    # It should resolve to the submodule dir (since .git file resolution
    # returns None for submodules, it falls back to the candidate dir)
    assert result == f"repo:{submodule.resolve()}"
    assert result != f"repo:{superproject.resolve()}"


def test_default_recall_scope_combines_three_wings() -> None:
    from code_puppy.plugins.puppy_kennel import wings

    scope = wings.default_recall_scope("code-puppy")
    assert len(scope) == 3
    assert any(w.startswith("repo:") for w in scope)
    assert "agent:code-puppy" in scope
    assert "user:default" in scope


# --------------------------------------------------------------------------- #
# The headline test: multi-process writes do not corrupt or lose data.
# --------------------------------------------------------------------------- #


def _concurrent_worker(worker_id: int, kennel_root: str, n: int = 25) -> int:
    """Run inside a child process — imports must happen here, not at import time."""
    os.environ["PUPPY_KENNEL_ROOT"] = kennel_root
    # Spawned children re-read the developer's REAL puppy.cfg (config
    # isolation only patches the parent process), so pin the toggle ON via
    # the env override or every write silently no-ops.
    os.environ["PUPPY_KENNEL_ENABLED"] = "true"
    import importlib

    from code_puppy.plugins.puppy_kennel import config as kennel_config
    from code_puppy.plugins.puppy_kennel import kennel as kennel_mod
    from code_puppy.plugins.puppy_kennel import recorder as recorder_mod
    from code_puppy.plugins.puppy_kennel import state as state_mod

    importlib.reload(kennel_config)
    importlib.reload(state_mod)
    importlib.reload(kennel_mod)
    importlib.reload(recorder_mod)
    kennel_mod.initialize()
    for i in range(n):
        recorder_mod.record_run_end(
            agent_name=f"worker-{worker_id}",
            model_name="m",
            session_id=f"sess-{worker_id:02d}-{i:03d}",
            success=True,
            response_text=f"Worker {worker_id} drawer {i}: lorem ipsum dolor sit amet.",
        )
    return worker_id


def test_concurrent_multiprocess_writes_do_not_corrupt(kennel_root: Path) -> None:
    """The thesis: 20 processes, 500 drawers, no corruption, no data loss.

    Cranked from 10x10 to 20x25 after a previous run revealed a flaky
    SELECT-then-INSERT race in ``ensure_wing``/``ensure_room``. Higher
    contention makes that class of bug surface more reliably in CI.
    """
    num_workers = 20
    drawers_per_worker = 25
    # Phase 5: single-write per response (no more dual-write).
    expected_total = num_workers * drawers_per_worker

    ctx = mp.get_context("spawn")
    with ctx.Pool(num_workers) as pool:
        results = pool.starmap(
            _concurrent_worker,
            [(wid, str(kennel_root), drawers_per_worker) for wid in range(num_workers)],
        )
    assert sorted(results) == list(range(num_workers))

    from code_puppy.plugins.puppy_kennel import kennel

    assert kennel.count_drawers() == expected_total
    # All workers land in the single shared repo wing (cwd is the same).
    assert len(kennel.list_wings()) == 1

    hits = kennel.search_drawers("lorem ipsum", limit=50)
    assert len(hits) == 50  # FTS5 still works after the storm
