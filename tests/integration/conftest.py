"""Pytest configuration for integration tests.

Integration tests require specific environment variables to be set to prevent
hanging issues with Rich's Live() display in pexpect PTY environments.
"""

import os

import pytest

# Required environment variables for integration tests
REQUIRED_ENV_VARS = {
    "CI": "Disables Rich Live() display in streaming handler",
    "CODE_PUPPY_TEST_FAST": "Puts CLI in fast/lean mode for testing",
}


def _check_integration_env_vars() -> tuple[bool, list[tuple[str, str]]]:
    """Check if required environment variables are set.

    Returns:
        Tuple of (all_set, missing_vars) where missing_vars is a list of
        (var_name, description) tuples.
    """
    missing_vars = []
    for var, description in REQUIRED_ENV_VARS.items():
        value = os.environ.get(var, "").lower()
        if value not in ("1", "true", "yes"):
            missing_vars.append((var, description))
    return len(missing_vars) == 0, missing_vars


def _format_skip_reason(missing_vars: list[tuple[str, str]]) -> str:
    """Format a skip reason message for missing env vars."""
    var_list = ", ".join(var for var, _ in missing_vars)
    return (
        f"Integration tests require env vars: {var_list}. "
        f"Run with: CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/"
    )


# Check once at module load time
_ENV_VARS_OK, _MISSING_VARS = _check_integration_env_vars()
_SKIP_REASON = _format_skip_reason(_MISSING_VARS) if _MISSING_VARS else ""


@pytest.fixture(autouse=True, scope="function")
def _require_integration_env_vars():
    """Skip integration tests if required environment variables are not set.

    This fixture runs automatically for every test in the integration directory.
    It gracefully skips tests instead of bombing the entire test suite.
    """
    if not _ENV_VARS_OK:
        pytest.skip(_SKIP_REASON)


# ---------------------------------------------------------------------------
# Lilac live-test model seeding
# ---------------------------------------------------------------------------
# tests/conftest.py redirects XDG_* to a session temp sandbox so tests never
# read the developer's real config — which also hides any provisioned lilac
# model from the live compaction suites' module-level model gate. When a real
# LILAC_API_KEY is present in the environment (the same signal those suites
# key on), seed the sandboxed extra_models.json with the live-test model so
# the gate can actually pass. Without a key this is a no-op and the suites
# skip exactly as before.

_LILAC_LIVE_MODEL = "lilac-moonshotai-kimi-k2.6"
_FAKE_CI_KEYS = {"fake-key-for-ci-testing", ""}


def _seed_lilac_model_for_live_tests() -> None:
    key = os.environ.get("LILAC_API_KEY", "").strip()
    if key in _FAKE_CI_KEYS:
        return
    if os.environ.get("CI", "").lower() in ("1", "true", "yes"):
        # Live lilac suites skip in CI regardless; don't seed.
        return

    import json

    from code_puppy import config as cp_config

    path = cp_config.EXTRA_MODELS_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        models = {}
        if os.path.exists(path):
            with open(path) as f:
                models = json.load(f)
        models.setdefault(
            _LILAC_LIVE_MODEL,
            {
                "type": "custom_openai",
                "provider": "lilac",
                "name": "moonshotai/kimi-k2.6",
                "custom_endpoint": {
                    "url": "https://api.getlilac.com/v1",
                    "api_key": "$LILAC_API_KEY",
                },
                "context_length": 262144,
                "supported_settings": ["temperature", "seed", "top_p"],
            },
        )
        with open(path, "w") as f:
            json.dump(models, f, indent=2)
    except Exception:
        # Seeding is best-effort; the live suites will skip with their own
        # explicit reason if the model still isn't visible.
        pass


_seed_lilac_model_for_live_tests()
