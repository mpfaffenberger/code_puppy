"""Tests for the DBOS plugin's startup_lock helpers.

These guard the simultaneous-launch fix: multiple Code Puppy instances
(e.g. several Zellij panes) must serialize DBOS initialization instead of
racing the shared SQLite system database and failing all-but-one.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap

from code_puppy.plugins.dbos_durable_exec.startup_lock import (
    enable_sqlite_wal,
    interprocess_lock,
)

_STARTUP_LOCK_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "code_puppy",
    "plugins",
    "dbos_durable_exec",
    "startup_lock.py",
)


def test_enable_sqlite_wal_sets_wal_mode():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "dbos_store.sqlite")
        enable_sqlite_wal(db)
        mode = sqlite3.connect(db).execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"


def test_enable_sqlite_wal_fails_soft_on_bad_path():
    # A path whose parent cannot be created must not raise.
    enable_sqlite_wal("/proc/cannot/create/here/dbos.sqlite")


def test_interprocess_lock_yields_acquired():
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "x.launch.lock")
        with interprocess_lock(lock, timeout=5) as acquired:
            assert acquired is True


def test_interprocess_lock_serializes_across_processes():
    """Two processes racing for the lock must NOT hold it simultaneously."""
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, "race.launch.lock")
        startup_lock_path = os.path.abspath(_STARTUP_LOCK_PATH)
        script = textwrap.dedent(
            f"""
            import importlib.util, sys, time
            spec = importlib.util.spec_from_file_location(
                "startup_lock", {startup_lock_path!r}
            )
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            with m.interprocess_lock({lock!r}, timeout=10):
                sys.stdout.write(f"ACQ {{time.time():.4f}}\\n")
                sys.stdout.flush()
                time.sleep(0.5)
            """
        )
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outs = [p.communicate(timeout=30)[0] for p in procs]

        acquires = [
            float(line.split()[1])
            for out in outs
            for line in out.splitlines()
            if line.startswith("ACQ")
        ]
        assert len(acquires) == 2, f"expected 2 acquisitions, got {outs}"
        # The second acquisition must wait for the first holder (>=0.4s gap,
        # allowing slack under the 0.5s hold).
        assert abs(acquires[0] - acquires[1]) >= 0.4, (
            f"locks were not serialized: {acquires}"
        )
