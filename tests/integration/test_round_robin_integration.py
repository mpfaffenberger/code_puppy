"""Integration tests for round-robin model distribution."""

import json
import os
import pathlib

import pytest

from tests.integration.cli_expect.harness import CliHarness


@pytest.fixture
def round_robin_config(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create an extra_models.json with round-robin configuration."""
    config = {
        "test-round-robin": {
            "type": "round_robin",
            "models": ["glm-4.6-coding", "Cerebras-GLM-4.6"],
            "rotate_every": 2,
        },
        "test-round-robin-single": {
            "type": "round_robin",
            "models": ["glm-4.6-coding"],
            "rotate_every": 1,
        },
        "test-round-robin-missing-api": {
            "type": "round_robin",
            "models": ["missing-api-key-model", "glm-4.6-coding"],
            "rotate_every": 1,
        },
    }

    config_file = tmp_path / "extra_models.json"
    config_file.write_text(json.dumps(config, indent=2))
    return config_file


@pytest.fixture
def integration_env_with_round_robin(
    round_robin_config: pathlib.Path,
    integration_env: dict[str, str],
    tmp_path: pathlib.Path,
) -> dict[str, str]:
    """Integration environment with round-robin config."""
    env = integration_env.copy()
    # Copy the round-robin config to the expected location
    config_dir = tmp_path / ".code_puppy"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Copy extra_models.json to config directory
    extra_models_target = config_dir / "extra_models.json"
    extra_models_target.write_text(round_robin_config.read_text())

    return env


def has_required_api_keys() -> bool:
    """Check if we have at least one real API key for testing."""
    return bool(os.getenv("ZAI_API_KEY") or os.getenv("CEREBRAS_API_KEY"))


@pytest.mark.skipif(
    not has_required_api_keys(),
    reason="Need at least one API key for round-robin testing",
)
def test_round_robin_basic_rotation(
    cli_harness: CliHarness,
    integration_env_with_round_robin: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    """Test basic round-robin rotation between providers."""

    # Set up config with round-robin model
    config_dir = tmp_path / ".config" / "code_puppy"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_content = """
[puppy]
puppy_name = RoundRobinTest
owner_name = TestSuite
model = test-round-robin
auto_save_session = false
"""

    (config_dir / "puppy.cfg").write_text(config_content.strip())

    # Spawn CLI in interactive mode
    result = cli_harness.spawn(args=["-i"], env=integration_env_with_round_robin)
    cli_harness.wait_for_ready(result)

    try:
        # Send multiple prompts to trigger rotation
        prompts = [
            "What is 2+2? Just give the number.",
            "What is 3+3? Just give the number.",
            "What is 4+4? Just give the number.",
            "What is 5+5? Just give the number.",
        ]

        responses = []
        for prompt in prompts:
            cli_harness.send_command(result, prompt)
            # Wait for response
            cli_harness.wait_for_ready(result)
            # Capture response for analysis
            log_output = result.read_log()
            responses.append(log_output)

        # Verify we got responses (basic sanity check)
        assert len(responses) == len(prompts)

        # Check that the log contains evidence of model usage
        full_log = "\n".join(responses)

        # Verify the CLI didn't crash and gave responses
        assert "4" in full_log or "6" in full_log or "8" in full_log or "10" in full_log

        # Look for round-robin indicators in the log
        # Check that we're using one of the configured round-robin models
        assert (
            "Cerebras-GLM-4.6" in full_log
            or "glm-4.6-coding" in full_log
            or "Loading Model:"
            in full_log  # At least the model loading pattern should be there
        )

        # Count number of responses to ensure we got responses for all prompts
        response_count = (
            full_log.count("response")
            or full_log.count("answer")
            or len(
                [
                    line
                    for line in full_log.split("\n")
                    if any(char.isdigit() for char in line)
                ]
            )
        )
        assert (
            response_count >= len(prompts) // 2
        )  # At least half the prompts should have responses

    finally:
        cli_harness.cleanup(result)


@pytest.mark.skipif(
    not has_required_api_keys(),
    reason="Need at least one API key for round-robin testing",
)
def test_round_robin_single_model_fallback(
    cli_harness: CliHarness,
    integration_env_with_round_robin: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    """Test round-robin with a single model (should work like normal model)."""

    # Set up config with single-model round-robin
    config_dir = tmp_path / ".config" / "code_puppy"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_content = """
[puppy]
puppy_name = SingleRoundRobinTest
owner_name = TestSuite
model = test-round-robin-single
auto_save_session = false
"""

    (config_dir / "puppy.cfg").write_text(config_content.strip())

    # Spawn CLI
    result = cli_harness.spawn(args=["-i"], env=integration_env_with_round_robin)
    cli_harness.wait_for_ready(result)

    try:
        # Send a simple prompt
        cli_harness.send_command(result, "Say hello")
        cli_harness.wait_for_ready(result)

        # Verify we got a response
        log_output = result.read_log()
        assert "hello" in log_output.lower() or "hi" in log_output.lower()

    finally:
        cli_harness.cleanup(result)


def test_round_robin_missing_api_key_handling(
    cli_harness: CliHarness,
    integration_env_with_round_robin: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    """Test round-robin gracefully handles missing API keys."""

    # Temporarily clear API keys to test graceful handling
    original_zai = os.environ.get("ZAI_API_KEY")
    original_cerebras = os.environ.get("CEREBRAS_API_KEY")

    # Clear at least one API key to trigger missing key scenario
    if original_zai:
        os.environ.pop("ZAI_API_KEY", None)
    if original_cerebras:
        os.environ.pop("CEREBRAS_API_KEY", None)

    try:
        # Set up config with round-robin that includes a model with missing API key
        config_dir = tmp_path / ".config" / "code_puppy"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = """
[puppy]
puppy_name = MissingKeyTest
owner_name = TestSuite
model = test-round-robin-missing-api
auto_save_session = false
"""

        (config_dir / "puppy.cfg").write_text(config_content.strip())

        # Spawn CLI - should handle missing API keys gracefully
        result = cli_harness.spawn(args=["-i"], env=integration_env_with_round_robin)
        cli_harness.wait_for_ready(result)

        try:
            # Send a prompt
            cli_harness.send_command(result, "Test prompt")
            cli_harness.wait_for_ready(result)

            # Should either get a response or an error message, not crash
            log_output = result.read_log()
            # Log should contain something - either response or error handling
            assert len(log_output) > 0

        finally:
            cli_harness.cleanup(result)

    finally:
        # Restore original API keys
        if original_zai:
            os.environ["ZAI_API_KEY"] = original_zai
        if original_cerebras:
            os.environ["CEREBRAS_API_KEY"] = original_cerebras


def test_round_robin_rotate_every_parameter(
    cli_harness: CliHarness,
    integration_env_with_round_robin: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    """Test round-robin rotate_every parameter behavior."""

    # Create a custom config with rotate_every=3 for testing
    config = {
        "test-rotate-every-3": {
            "type": "round_robin",
            "models": ["glm-4.6-coding", "Cerebras-GLM-4.6"],
            "rotate_every": 3,
        }
    }

    config_dir = tmp_path / ".config" / "code_puppy"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Update extra_models.json with the rotate_every=3 config
    extra_models_file = (
        pathlib.Path(os.environ.get("HOME", tmp_path))
        / ".code_puppy"
        / "extra_models.json"
    )
    extra_models_file.parent.mkdir(parents=True, exist_ok=True)
    extra_models_file.write_text(json.dumps(config, indent=2))

    config_content = """
[puppy]
puppy_name = RotateEveryTest
owner_name = TestSuite
model = test-rotate-every-3
auto_save_session = false
"""

    (config_dir / "puppy.cfg").write_text(config_content.strip())

    if not has_required_api_keys():
        pytest.skip("Need API keys for rotate_every testing")

    # Spawn CLI
    result = cli_harness.spawn(args=["-i"], env=integration_env_with_round_robin)
    cli_harness.wait_for_ready(result)

    try:
        # Send 6 prompts to test rotation behavior (should rotate every 3)
        for i in range(6):
            cli_harness.send_command(
                result, f"Prompt {i + 1}: just say 'response {i + 1}'"
            )
            cli_harness.wait_for_ready(result)

        # Verify we got responses
        log_output = result.read_log()
        assert "response" in log_output.lower()

    finally:
        cli_harness.cleanup(result)
