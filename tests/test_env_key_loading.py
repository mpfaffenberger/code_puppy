"""Tests for how ``load_api_keys_to_environment`` treats a project-local .env."""

import os

from code_puppy import config as cp_config


def _snapshot_env():
    return dict(os.environ)


def _restore_env(snapshot):
    os.environ.clear()
    os.environ.update(snapshot)


def test_dotenv_only_loads_known_api_keys(tmp_path, monkeypatch):
    """A .env in the working directory hydrates known API keys but nothing else.

    Only allowlisted API-key names are imported; unrelated names such as base
    URLs or CODE_PUPPY_* toggles in the .env must not reach the environment.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=key-from-dotenv\n"
        "ANTHROPIC_BASE_URL=http://example.invalid\n"
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT=1\n"
    )

    monkeypatch.chdir(tmp_path)

    snapshot = _snapshot_env()
    try:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_BASE_URL", None)
        os.environ.pop("CODE_PUPPY_DISABLE_RETRY_TRANSPORT", None)

        cp_config.load_api_keys_to_environment()

        # The allowlisted API key still loads from the .env.
        assert os.environ.get("ANTHROPIC_API_KEY") == "key-from-dotenv"

        # Non-allowlisted names never enter the environment via the .env.
        assert os.environ.get("ANTHROPIC_BASE_URL") != "http://example.invalid"
        assert "CODE_PUPPY_DISABLE_RETRY_TRANSPORT" not in os.environ
    finally:
        _restore_env(snapshot)
