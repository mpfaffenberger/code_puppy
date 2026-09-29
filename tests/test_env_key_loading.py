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


def test_dotenv_does_not_import_endpoints(tmp_path, monkeypatch):
    """An endpoint in the project .env must not import: it can redirect requests.

    ``AZURE_OPENAI_ENDPOINT`` still hydrates from the user's own puppy.cfg
    (see ``cfg_only_names``), but a repo-local .env supplying it would let the
    project point Azure traffic at an arbitrary host.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("AZURE_OPENAI_ENDPOINT=https://attacker.invalid\n")

    monkeypatch.chdir(tmp_path)

    snapshot = _snapshot_env()
    try:
        os.environ.pop("AZURE_OPENAI_ENDPOINT", None)

        cp_config.load_api_keys_to_environment()

        assert os.environ.get("AZURE_OPENAI_ENDPOINT") != "https://attacker.invalid"
    finally:
        _restore_env(snapshot)


def test_dotenv_does_not_import_custom_endpoint_headers(tmp_path, monkeypatch):
    """A header var in the project .env must not import: it can reroute requests.

    A ``custom_endpoint.headers`` value is spliced into outgoing request headers,
    so hydrating it from a repo-local .env would let an untrusted project set
    request headers/routing — the same redirect concern as an endpoint. Only
    api_key vars hydrate from a project .env, never header vars.
    """
    monkeypatch.setattr(
        "code_puppy.provider_credentials._load_merged_model_config",
        lambda: {
            "custom-model": {
                "provider": "custom",
                "custom_endpoint": {"headers": {"X-Route": "$MY_ROUTE"}},
            }
        },
    )

    env_file = tmp_path / ".env"
    env_file.write_text("MY_ROUTE=https://attacker.invalid\n")

    monkeypatch.chdir(tmp_path)

    snapshot = _snapshot_env()
    try:
        os.environ.pop("MY_ROUTE", None)

        cp_config.load_api_keys_to_environment()

        assert os.environ.get("MY_ROUTE") != "https://attacker.invalid"
    finally:
        _restore_env(snapshot)


def test_endpoint_hydrates_from_config(monkeypatch):
    """The Azure endpoint still loads from the user's trusted config."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")

    def fake_get_key(key_name):
        return "https://example.valid" if key_name == "AZURE_OPENAI_ENDPOINT" else None

    monkeypatch.setattr(cp_config, "get_api_key", fake_get_key)

    snapshot = _snapshot_env()
    try:
        cp_config.load_api_keys_to_environment()
        assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://example.valid"
    finally:
        _restore_env(snapshot)
