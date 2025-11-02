"""Robust CLI harness for end-to-end pexpect tests.

Handles a clean temporary HOME, config bootstrapping, and sending/receiving
with the quirks we learned (\r line endings, tiny delays, optional stdout
capture). Includes fixtures for pytest.
"""

import json
import os
import pathlib
import random
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Final

import pexpect
import pytest

CONFIG_TEMPLATE: Final[str] = """[puppy]
puppy_name = IntegrationPup
owner_name = CodePuppyTester
auto_save_session = true
max_saved_sessions = 5
model = synthetic-GLM-4.6
enable_dbos = true
"""

MOTD_TEMPLATE: Final[str] = """2025-08-24
"""


def _random_name(length: int = 8) -> str:
    """Return a short random string for safe temp directory names."""
    return "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=length))


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    backoff_factor: float = 2.0


def _with_retry(fn, policy: RetryPolicy, timeout: float):
    delay = policy.base_delay_seconds
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn()
        except pexpect.exceptions.TIMEOUT:
            if attempt == policy.max_attempts:
                raise
            time.sleep(delay)
            delay = min(delay * policy.backoff_factor, policy.max_delay_seconds)
        except Exception:
            raise


@dataclass(slots=True)
class SpawnResult:
    child: pexpect.spawn
    temp_home: pathlib.Path
    log_path: pathlib.Path
    timeout: float = field(default=10.0)
    _log_file: object = field(init=False, repr=False)
    _initial_files: set[pathlib.Path] = field(
        init=False, repr=False, default_factory=set
    )

    def send(self, txt: str) -> None:
        """Send with the cooked line ending learned from smoke tests."""
        self.child.send(txt)
        time.sleep(0.3)

    def sendline(self, txt: str) -> None:
        """Caller must include any desired line endings explicitly."""
        self.child.send(txt)
        time.sleep(0.3)

    def read_log(self) -> str:
        return (
            self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""
        )

    def close_log(self) -> None:
        if hasattr(self, "_log_file") and self._log_file:
            self._log_file.close()


# ---------------------------------------------------------------------------
# DBOS report collection
# ---------------------------------------------------------------------------
_dbos_reports: list[str] = []


def _safe_json(val):
    try:
        json.dumps(val)
        return val
    except Exception:
        return str(val)


def _capture_initial_files(temp_home: pathlib.Path) -> set[pathlib.Path]:
    """Capture all files that exist before the test starts.

    Returns a set of absolute file paths that were present at test start.
    """
    initial_files = set()
    try:
        for root, dirs, files in os.walk(temp_home):
            for file in files:
                initial_files.add(pathlib.Path(root) / file)
    except (OSError, PermissionError):
        # If we can't walk the directory, just return empty set
        pass
    return initial_files


def _cleanup_test_only_files(
    temp_home: pathlib.Path, initial_files: set[pathlib.Path]
) -> None:
    """Delete only files that were created during the test run.

    This is more selective than removing the entire temp directory.
    """
    try:
        # Walk current files and delete those not in initial set
        current_files = set()
        for root, dirs, files in os.walk(temp_home):
            for file in files:
                current_files.add(pathlib.Path(root) / file)

        # Files to delete are those that exist now but didn't initially
        files_to_delete = current_files - initial_files

        # Delete files in reverse order (deepest first) to avoid path issues
        for file_path in sorted(
            files_to_delete, key=lambda p: len(p.parts), reverse=True
        ):
            try:
                file_path.unlink()
            except (OSError, PermissionError):
                # Best effort cleanup
                pass

        # Try to remove empty directories
        _cleanup_empty_directories(temp_home, initial_files)

    except (OSError, PermissionError):
        # Fallback to full cleanup if selective cleanup fails
        shutil.rmtree(temp_home, ignore_errors=True)


def _cleanup_empty_directories(
    temp_home: pathlib.Path, initial_files: set[pathlib.Path]
) -> None:
    """Remove empty directories that weren't present initially."""
    try:
        # Get all current directories
        current_dirs = set()
        for root, dirs, files in os.walk(temp_home):
            for dir_name in dirs:
                current_dirs.add(pathlib.Path(root) / dir_name)

        # Get initial directories (just the parent dirs of initial files)
        initial_dirs = set()
        for file_path in initial_files:
            initial_dirs.add(file_path.parent)

        # Remove empty directories that weren't there initially
        dirs_to_remove = current_dirs - initial_dirs
        for dir_path in sorted(
            dirs_to_remove, key=lambda p: len(p.parts), reverse=True
        ):
            try:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass


def dump_dbos_report(temp_home: pathlib.Path) -> None:
    """Collect a summary of DBOS SQLite contents for this temp HOME.

    - Lists tables and row counts
    - Samples up to 2 rows per table
    Appends human-readable text to a global report buffer.
    """
    try:
        db_path = temp_home / ".code_puppy" / "dbos_store.sqlite"
        if not db_path.exists():
            return
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = [r[0] for r in cur.fetchall()]
            lines: list[str] = []
            lines.append(f"DBOS Report for: {db_path}")
            if not tables:
                lines.append("- No user tables found")
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    count = cur.fetchone()[0]
                    lines.append(f"- {t}: {count} rows")
                    # Sample up to 2 rows for context
                    cur.execute(f"SELECT * FROM {t} LIMIT 2")
                    rows = cur.fetchall()
                    colnames = (
                        [d[0] for d in cur.description] if cur.description else []
                    )
                    for row in rows:
                        obj = {colnames[i]: _safe_json(row[i]) for i in range(len(row))}
                        lines.append(f"  • sample: {obj}")
                except Exception as te:
                    lines.append(f"- {t}: error reading table: {te}")
            lines.append("")
            _dbos_reports.append("\n".join(lines))
        finally:
            conn.close()
    except Exception:
        # Silent: reporting should never fail tests
        pass


def get_dbos_reports() -> str:
    return "\n".join(_dbos_reports)


class CliHarness:
    """Manages a temporary CLI environment and pexpect child."""

    def __init__(
        self,
        timeout: float = 10.0,
        capture_output: bool = True,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._timeout = timeout
        self._capture_output = capture_output
        self._retry_policy = retry_policy or RetryPolicy()

    def spawn(
        self,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        existing_home: pathlib.Path | None = None,
    ) -> SpawnResult:
        """Spawn the CLI, optionally reusing an existing HOME for autosave tests."""
        if existing_home is not None:
            temp_home = pathlib.Path(existing_home)
            config_dir = temp_home / ".config" / "code_puppy"
            code_puppy_dir = temp_home / ".code_puppy"
            config_dir.mkdir(parents=True, exist_ok=True)
            code_puppy_dir.mkdir(parents=True, exist_ok=True)
            write_config = not (config_dir / "puppy.cfg").exists()
        else:
            temp_home = pathlib.Path(
                tempfile.mkdtemp(prefix=f"code_puppy_home_{_random_name()}_")
            )
            config_dir = temp_home / ".config" / "code_puppy"
            code_puppy_dir = temp_home / ".code_puppy"
            config_dir.mkdir(parents=True, exist_ok=True)
            code_puppy_dir.mkdir(parents=True, exist_ok=True)
            write_config = True

        if write_config:
            # Write config to both legacy (~/.code_puppy) and XDG (~/.config/code_puppy)
            (config_dir / "puppy.cfg").write_text(CONFIG_TEMPLATE, encoding="utf-8")
            (config_dir / "motd.txt").write_text(MOTD_TEMPLATE, encoding="utf-8")
            (code_puppy_dir / "puppy.cfg").write_text(CONFIG_TEMPLATE, encoding="utf-8")

        log_path = temp_home / f"cli_output_{uuid.uuid4().hex}.log"
        cmd_args = ["code-puppy"] + (args or [])

        spawn_env = os.environ.copy()
        spawn_env.update(env or {})
        spawn_env["HOME"] = str(temp_home)
        spawn_env.pop("PYTHONPATH", None)  # avoid accidental venv confusion
        # Ensure DBOS uses a temp sqlite under this HOME
        dbos_sqlite = code_puppy_dir / "dbos_store.sqlite"
        spawn_env["DBOS_SYSTEM_DATABASE_URL"] = f"sqlite:///{dbos_sqlite}"
        spawn_env.setdefault("DBOS_LOG_LEVEL", "ERROR")

        child = pexpect.spawn(
            cmd_args[0],
            args=cmd_args[1:],
            encoding="utf-8",
            timeout=self._timeout,
            env=spawn_env,
        )

        log_file = None
        if self._capture_output:
            log_file = log_path.open("w", encoding="utf-8")
            child.logfile = log_file
        child.logfile_read = sys.stdout

        result = SpawnResult(
            child=child,
            temp_home=temp_home,
            log_path=log_path,
            timeout=self._timeout,
        )
        if log_file:
            result._log_file = log_file

        # Capture initial file state for selective cleanup
        result._initial_files = _capture_initial_files(temp_home)

        return result

    def send_command(self, result: SpawnResult, txt: str) -> str:
        """Convenience: send a command and return all new output until next prompt."""
        result.sendline(txt + "\r")
        # Let the child breathe before we slurp output
        time.sleep(0.2)
        return result.read_log()

    def wait_for_ready(self, result: SpawnResult) -> None:
        """Wait for CLI to be ready for user input."""
        self._expect_with_retry(
            result.child,
            ["Enter your coding task", ">>> ", "Interactive Mode"],
            timeout=result.timeout,
        )

    def cleanup(self, result: SpawnResult) -> None:
        """Terminate the child, dump DBOS report, then remove test-created files unless kept."""
        keep_home = os.getenv("CODE_PUPPY_KEEP_TEMP_HOME") in {
            "1",
            "true",
            "TRUE",
            "True",
        }
        try:
            result.close_log()
        except Exception:
            pass
        try:
            if result.child.isalive():
                result.child.terminate(force=True)
        finally:
            # Dump DBOS report before cleanup
            dump_dbos_report(result.temp_home)
            if not keep_home:
                # Use selective cleanup - only delete files created during test
                use_selective_cleanup = os.getenv(
                    "CODE_PUPPY_SELECTIVE_CLEANUP", "true"
                ).lower() in {"1", "true", "yes", "on"}
                if use_selective_cleanup:
                    _cleanup_test_only_files(result.temp_home, result._initial_files)
                else:
                    # Fallback to original behavior
                    shutil.rmtree(result.temp_home, ignore_errors=True)

    def _expect_with_retry(
        self, child: pexpect.spawn, patterns, timeout: float
    ) -> None:
        def _inner():
            return child.expect(patterns, timeout=timeout)

        _with_retry(_inner, policy=self._retry_policy, timeout=timeout)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def integration_env() -> dict[str, str]:
    """Return a basic environment for integration tests."""
    return {
        "CEREBRAS_API_KEY": os.environ["CEREBRAS_API_KEY"],
        "CODE_PUPPY_TEST_FAST": "1",
    }


@pytest.fixture
def retry_policy() -> RetryPolicy:
    return RetryPolicy()


@pytest.fixture
def log_dump(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "test_cli.log"


@pytest.fixture
def cli_harness() -> CliHarness:
    """Harness with default settings and output capture on."""
    return CliHarness(capture_output=True)


@pytest.fixture
def spawned_cli(
    cli_harness: CliHarness,
    integration_env: dict[str, str],
) -> SpawnResult:
    """Spawn a CLI in interactive mode with a clean environment.

    Robust to first-run prompts; gracefully proceeds if config exists.
    """
    result = cli_harness.spawn(args=["-i"], env=integration_env)

    # Try to satisfy first-run prompts if they appear; otherwise continue
    try:
        result.child.expect("What should we name the puppy?", timeout=5)
        result.sendline("\r")
        result.child.expect("What's your name", timeout=5)
        result.sendline("\r")
    except pexpect.exceptions.TIMEOUT:
        pass

    # Skip autosave picker if it appears
    try:
        result.child.expect("1-5 to load, 6 for next", timeout=3)
        result.send("\r")
        time.sleep(0.2)
        result.send("\r")
    except pexpect.exceptions.TIMEOUT:
        pass

    # Wait until interactive prompt is ready
    cli_harness.wait_for_ready(result)

    yield result
    cli_harness.cleanup(result)
