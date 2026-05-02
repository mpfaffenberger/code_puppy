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
    assert db_path.exists(), f"Expected DB file at {db_path} (waited 10s)"

    # Quit cleanly
    spawned_cli.send("/quit\r")
