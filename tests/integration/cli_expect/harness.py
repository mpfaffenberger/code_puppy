"""Robust CLI harness for end-to-end pexpect tests.

Handles a clean temporary HOME, config bootstrapping, and sending/receiving
with the quirks we learned (\r line endings, tiny delays, optional stdout
capture). Includes fixtures for pytest.
"""

import os
import pathlib
import random
import shutil
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
model = Cerebras-Qwen3-Coder-480b
enable_dbos = false
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
            (config_dir / "puppy.cfg").write_text(CONFIG_TEMPLATE, encoding="utf-8")
            (config_dir / "motd.txt").write_text(MOTD_TEMPLATE, encoding="utf-8")

        log_path = temp_home / f"cli_output_{uuid.uuid4().hex}.log"
        cmd_args = ["code-puppy"] + (args or [])

        spawn_env = os.environ.copy()
        spawn_env.update(env or {})
        spawn_env["HOME"] = str(temp_home)
        spawn_env.pop("PYTHONPATH", None)  # avoid accidental venv confusion

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
        """Terminate the child and remove the temporary HOME unless instructed otherwise."""
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
            if not keep_home:
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
        "CEREBRAS_API_KEY": os.getenv("CEREBRAS_API_KEY", "fake-key-for-ci"),
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
    """Spawn a CLI in interactive mode with a clean environment."""
    result = cli_harness.spawn(args=["-i"], env=integration_env)
    result.child.expect("What should we name the puppy?", timeout=15)
    result.sendline("\r")
    result.child.expect("What's your name", timeout=10)
    result.sendline("\r")
    result.child.expect("Interactive Mode", timeout=15)
    try:
        result.child.expect("1-5 to load, 6 for next", timeout=5)
        result.send("\r")
        time.sleep(0.3)
        result.send("\r")
    except pexpect.exceptions.TIMEOUT:
        pass
    result.child.expect("Enter your coding task", timeout=15)
    yield result
    cli_harness.cleanup(result)
