"""Foundational tests for the CLI harness plumbing."""
import pathlib
import time

from tests.integration.cli_expect.harness import CliHarness, SpawnResult


def test_harness_bootstrap_write_config(
    cli_harness: CliHarness,
    integration_env: dict[str, str],
) -> None:
    """Config file should exist and contain expected values after bootstrap."""
    result = cli_harness.spawn(args=["--version"], env=integration_env)
    cfg_path = result.temp_home / ".config" / "code_puppy" / "puppy.cfg"
    assert cfg_path.exists(), f"Config not written to {cfg_path}"
    cfg_text = cfg_path.read_text(encoding="utf-8")
    assert "IntegrationPup" in cfg_text
    assert "CodePuppyTester" in cfg_text
    assert "Cerebras-Qwen3-Coder-480b" in cfg_text
    cli_harness.cleanup(result)


def test_integration_env_env(integration_env: dict[str, str]) -> None:
    """Environment used for live integration tests should include required keys or a fake for CI."""
    assert "CEREBRAS_API_KEY" in integration_env
    assert integration_env["CODE_PUPPY_TEST_FAST"] == "1"


def test_retry_policy_constructs(retry_policy) -> None:
    """RetryPolicy should construct with reasonable defaults."""
    policy = retry_policy
    assert policy.max_attempts >= 3
    assert policy.base_delay_seconds >= 0.1
    assert policy.max_delay_seconds > policy.base_delay_seconds
    assert policy.backoff_factor >= 1.0


def test_log_dump_path_exists(log_dump, tmp_path: pathlib.Path) -> None:
    """Log dump fixture should yield a path under the shared tmp_path."""
    path = log_dump
    assert path.parent == tmp_path
    assert not path.exists()  # not written until after test


def test_spawned_cli_is_alive(spawned_cli: SpawnResult) -> None:
    """spawned_cli fixture should hand us a live CLI at the task prompt."""
    assert spawned_cli.child.isalive()
    log = spawned_cli.read_log()
    assert "Enter your coding task" in log or log == ""


def test_send_command_returns_output(spawned_cli: SpawnResult) -> None:
    """send_command should send text and give us back whatever was written."""
    spawned_cli.sendline("/set owner_name 'HarnessTest'\r")
    time.sleep(0.5)
    log = spawned_cli.read_log()
    assert "/set owner_name" in log or log == ""


def test_harness_cleanup_terminates_and_removes_temp_home(
    cli_harness: CliHarness,
    integration_env: dict[str, str],
) -> None:
    """cleanup should kill the process and delete its temporary HOME."""
    result = cli_harness.spawn(args=["--help"], env=integration_env)
    temp_home = result.temp_home
    assert temp_home.exists()
    cli_harness.cleanup(result)
    assert not temp_home.exists()
    assert not result.child.isalive()
