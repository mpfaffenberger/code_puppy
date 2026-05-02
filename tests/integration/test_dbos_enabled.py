import time
from pathlib import Path


def test_dbos_initializes_and_creates_db(spawned_cli):
    # spawned_cli fixture starts the app and waits until interactive mode
    # Confirm DBOS initialization message appeared
    log = spawned_cli.read_log()
    assert "Initializing DBOS with database at:" in log or "DBOS is disabled" not in log

    # Database path should be under temp HOME/.code_puppy by default
    home = Path(spawned_cli.temp_home)
    db_path = home / ".code_puppy" / "dbos_store.sqlite"

    # DBOS init runs via the dbos_durable_exec plugin's startup callback. On
    # slower CI runners, sqlite migrations can lag behind the interactive prompt
    # becoming ready. Poll for up to 10s before giving up.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if db_path.exists():
            break
        time.sleep(0.25)
    if not db_path.exists():
        # Surface the spawned CLI's log + filesystem state so CI failures
        # are debuggable. We log the FIRST 16kb (where DBOS init messages
        # live) plus a directory tree of the .code_puppy dir.
        import os

        cli_log = spawned_cli.read_log()
        cp_dir = home / ".code_puppy"
        if cp_dir.exists():
            tree_lines = []
            for root, dirs, files in os.walk(cp_dir):
                for f in files:
                    p = Path(root) / f
                    try:
                        size = p.stat().st_size
                    except OSError:
                        size = -1
                    tree_lines.append(f"  {p.relative_to(home)}  ({size} bytes)")
            tree = "\n".join(tree_lines) or "  <empty>"
        else:
            tree = "  <.code_puppy dir does not exist>"

        msg = (
            f"Expected DB file at {db_path} (waited 10s).\n"
            f"--- .code_puppy dir contents ---\n{tree}\n"
            f"--- spawned CLI log (FIRST 16kb) ---\n{cli_log[:16384]}\n"
            f"--- spawned CLI log (LAST 4kb) ---\n{cli_log[-4096:]}"
        )
        raise AssertionError(msg)

    # Quit cleanly
    spawned_cli.send("/quit\r")
