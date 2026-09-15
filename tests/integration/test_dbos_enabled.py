import importlib.util
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("dbos") is None,
    reason="DBOS optional dependency is not installed",
)


def test_dbos_initializes_and_creates_db(spawned_cli):
    # spawned_cli fixture starts the app and waits until interactive mode
    # Confirm DBOS initialization message appeared
    log = spawned_cli.read_log()
    assert "Initializing DBOS with database at:" in log

    # Database path should be under temp HOME/.code_puppy by default
    home = Path(spawned_cli.temp_home)
    db_path = home / ".code_puppy" / "dbos_store.sqlite"

    # DBOS init runs via the plugin's startup callback; on slow CI the sqlite
    # migrations can lag behind the prompt — poll up to 10s before giving up.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if db_path.exists():
            break
        time.sleep(0.25)
    assert db_path.exists(), f"Expected DB file at {db_path} (waited 10s)"

    # Quit cleanly
    spawned_cli.send("/quit\r")
