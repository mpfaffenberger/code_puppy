"""Tests for the one-shot ``contexts/`` -> ``autosaves/`` sweep.

Under the unified-store model, the legacy CONTEXTS_DIR is no longer the
canonical named-session store; everything lives under AUTOSAVE_DIR. Any
sessions a user had ``/dump_context``'d into the legacy location are moved
on first launch via
:func:`code_puppy.session_migration.sweep_contexts_to_autosaves`,
which is what we exercise here.

Why a separate test module vs. tucking it into ``test_session_storage``:
the sweep cuts across two directories, several failure modes, and a
sentinel file -- giving it its own file keeps each test small and the
shared fixtures readable.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def sweep_dirs(tmp_path: Path, monkeypatch):
    """Wire AUTOSAVE_DIR + CONTEXTS_DIR to a clean tmp_path layout."""
    contexts = tmp_path / "contexts"
    autosaves = tmp_path / "autosaves"
    monkeypatch.setattr("code_puppy.config.CONTEXTS_DIR", str(contexts))
    monkeypatch.setattr("code_puppy.config.AUTOSAVE_DIR", str(autosaves))
    return contexts, autosaves


def _write_pair(
    directory: Path, stem: str, *, contents: str = "x"
) -> tuple[Path, Path]:
    """Write a fake (pickle, sidecar) pair under ``directory`` and return them."""
    directory.mkdir(parents=True, exist_ok=True)
    pkl = directory / f"{stem}.pkl"
    meta = directory / f"{stem}_meta.json"
    pkl.write_text(contents)
    meta.write_text(json.dumps({"session_name": stem}))
    return pkl, meta


class TestSweepContextsToAutosaves:
    def test_noop_when_contexts_missing(self, sweep_dirs):
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        # contexts/ never created
        sweep_contexts_to_autosaves()
        # Sentinel touched even with nothing to do, so subsequent runs
        # skip the recheck.
        assert (autosaves / ".contexts_sweep_done").exists()
        # No spurious files in either dir.
        assert list(autosaves.iterdir()) == [autosaves / ".contexts_sweep_done"]

    def test_clean_run_moves_pickle_and_sidecar(self, sweep_dirs):
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        pkl_src, meta_src = _write_pair(contexts, "mywork", contents="payload")

        sweep_contexts_to_autosaves()

        # Pickle + sidecar moved.
        assert not pkl_src.exists()
        assert not meta_src.exists()
        moved_pkl = autosaves / "mywork.pkl"
        moved_meta = autosaves / "mywork_meta.json"
        assert moved_pkl.read_text() == "payload"
        assert json.loads(moved_meta.read_text())["session_name"] == "mywork"
        # Sentinel present.
        assert (autosaves / ".contexts_sweep_done").exists()

    def test_idempotent_via_sentinel(self, sweep_dirs):
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        _write_pair(contexts, "mywork")

        sweep_contexts_to_autosaves()
        # Drop a sentinel-only fixture: a new file in contexts/ after the
        # first sweep must NOT be moved on the second run.
        _write_pair(contexts, "second_run_file")

        sweep_contexts_to_autosaves()

        assert (contexts / "second_run_file.pkl").exists()
        assert not (autosaves / "second_run_file.pkl").exists()

    def test_name_conflict_skips_and_warns(self, sweep_dirs):
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        _write_pair(contexts, "mywork", contents="from-contexts")
        _write_pair(autosaves, "mywork", contents="from-autosaves")

        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            sweep_contexts_to_autosaves()

        # Conflicting source stays put.
        assert (contexts / "mywork.pkl").read_text() == "from-contexts"
        # Dest unchanged.
        assert (autosaves / "mywork.pkl").read_text() == "from-autosaves"
        # Warning emitted, mentions the path.
        assert mock_warn.called
        warning_text = mock_warn.call_args[0][0]
        assert "mywork" in warning_text
        assert "already exists" in warning_text

    def test_per_file_error_does_not_abort(self, sweep_dirs):
        """A single move failure must not stop the sweep for siblings."""
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        _write_pair(contexts, "good_one", contents="ok")
        _write_pair(contexts, "bad_one", contents="will-fail")

        real_replace = __import__("os").replace

        def selective_failure(src, dst):
            if "bad_one.pkl" in str(src):
                raise OSError("simulated disk full")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=selective_failure):
            sweep_contexts_to_autosaves()

        # Good one made it.
        assert (autosaves / "good_one.pkl").read_text() == "ok"
        # Bad one stayed put. (Sidecar too -- pickle never moved.)
        assert (contexts / "bad_one.pkl").exists()
        # Sentinel still touched.
        assert (autosaves / ".contexts_sweep_done").exists()

    def test_sidecar_failure_leaves_pickle_loadable(self, sweep_dirs):
        """Pickle-first + log-on-sidecar-orphan: load-bearing data survives.

        Regression guard for B3 of the LEAN-plan review. Without this, a
        sidecar-move failure between pickle-move and sidecar-move would
        either roll back the pickle (losing data) or silently strand the
        orphan with no audit trail.
        """
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        _write_pair(contexts, "session_a", contents="payload")

        real_replace = __import__("os").replace

        def fail_only_sidecar(src, dst):
            if str(src).endswith("_meta.json"):
                raise OSError("simulated sidecar failure")
            return real_replace(src, dst)

        with (
            patch("os.replace", side_effect=fail_only_sidecar),
            patch("code_puppy.error_logging.log_error_message") as mock_log,
        ):
            sweep_contexts_to_autosaves()

        # Pickle moved successfully -- the load-bearing data is at its
        # new home and reads fine.
        assert (autosaves / "session_a.pkl").read_text() == "payload"
        # Orphan sidecar stuck at source.
        assert (contexts / "session_a_meta.json").exists()
        # Orphan path logged for SRE follow-up.
        assert mock_log.called
        log_text = mock_log.call_args[0][0]
        assert "session_a_meta.json" in log_text

    def test_sweep_never_raises(self, sweep_dirs):
        """Even an internal explosion must not crash the caller."""
        from code_puppy.session_migration import sweep_contexts_to_autosaves

        contexts, autosaves = sweep_dirs
        _write_pair(contexts, "victim")

        # Force a failure somewhere in the iteration by mocking list_dir
        # in a way that explodes after entering the try-block.
        with patch("pathlib.Path.glob", side_effect=RuntimeError("unexpected")):
            # Must not raise.
            sweep_contexts_to_autosaves()
