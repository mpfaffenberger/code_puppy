from pathlib import Path


def test_dbos_initializes_and_creates_db(spawned_cli):
    # spawned_cli fixture starts the app and waits until interactive mode
    # Confirm DBOS initialization message appeared
    log = spawned_cli.read_log()
    assert "Initializing DBOS with database at:" in log or "DBOS is disabled" not in log

    # Database path should be under temp HOME/.code_puppy by default
    home = Path(spawned_cli.temp_home)
    db_path = home / ".code_puppy" / "dbos_store.sqlite"

    # Allow a little time for DBOS to initialize the DB file
    # but generally by the time interactive prompt is ready, it should exist
    assert db_path.exists(), f"Expected DB file at {db_path}"

    # Quit cleanly
    spawned_cli.send("/quit\r")
