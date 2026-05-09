"""Security regression tests for MCP key redaction and hardcoded-secret validation (P2-07).

Covers:
- get_status() redacts sensitive header values
- get_status() redacts sensitive env values
- _validate_no_hardcoded_secrets warns on hardcoded API key prefixes
- _validate_no_hardcoded_secrets passes on env-var references
- Redaction uses the same redact_secrets logic as the rest of the codebase
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from code_puppy.mcp_.secrets import (
    _contains_hardcoded_secret,
    _validate_env_list_secrets,
    _validate_no_hardcoded_secrets,
    redact_mcp_config,
)
from code_puppy.mcp_.managed_server import (
    ManagedMCPServer,
    ServerConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server(
    name: str = "test-server",
    server_type: str = "sse",
    config: dict | None = None,
) -> ManagedMCPServer:
    """Create a ManagedMCPServer with defaults, suppressing actual server creation."""
    cfg = ServerConfig(
        id="test-id",
        name=name,
        type=server_type,
        config=config or {"url": "http://localhost:8080"},
    )
    # Suppress actual pydantic-ai server creation to avoid network side-effects
    with patch.object(ManagedMCPServer, "_create_server"):
        srv = ManagedMCPServer.__new__(ManagedMCPServer)
        srv.config = cfg
        srv._pydantic_server = None
        srv._state = ManagedMCPServer.__dict__.get("ServerState", None)
        # Manually init the bits get_status needs
        from code_puppy.mcp_.managed_server import ServerState

        srv._state = ServerState.STOPPED
        srv._enabled = False
        srv._quarantine_until = None
        srv._start_time = None
        srv._stop_time = None
        srv._error_message = None
        return srv


# ---------------------------------------------------------------------------
# get_status redaction
# ---------------------------------------------------------------------------


class TestGetStatusRedaction:
    """get_status must never expose raw API keys in headers or env."""

    def test_headers_with_auth_key_redacted(self):
        config = {
            "url": "http://localhost:8080",
            "headers": {
                "Authorization": "Bearer sk-12345secret67890",
                "X-Custom": "safe-value",
            },
        }
        srv = _make_server(config=config)
        status = srv.get_status()

        cfg_out = status["config"]
        assert cfg_out["headers"]["Authorization"] == "<redacted>"
        assert cfg_out["headers"]["X-Custom"] == "safe-value"

    def test_env_with_api_key_redacted(self):
        config = {
            "url": "http://localhost:8080",
            "env": {
                "OPENAI_API_KEY": "sk-abc123",
                "NORMAL_VAR": "fine",
            },
        }
        srv = _make_server(config=config)
        status = srv.get_status()

        cfg_out = status["config"]
        assert cfg_out["env"]["OPENAI_API_KEY"] == "<redacted>"
        assert cfg_out["env"]["NORMAL_VAR"] == "fine"

    def test_config_without_headers_or_env_untouched(self):
        config = {
            "url": "http://localhost:8080",
            "command": "node",
            "args": ["server.js"],
        }
        srv = _make_server(config=config)
        status = srv.get_status()

        cfg_out = status["config"]
        assert cfg_out == config  # no redaction needed

    def test_env_list_strings_redacted(self):
        config = {
            "url": "http://localhost:8080",
            "env": [
                "OPENAI_API_KEY=sk-abc123",
                "NORMAL_VAR=hello",
            ],
        }
        srv = _make_server(config=config)
        status = srv.get_status()

        cfg_out = status["config"]
        assert "sk-abc123" not in str(cfg_out["env"])
        assert "NORMAL_VAR=hello" in str(cfg_out["env"]) or "NORMAL_VAR" in str(
            cfg_out["env"]
        )

    def test_nested_env_secret_redacted(self):
        """Even deeply nested secrets inside env dicts must be caught."""
        config = {
            "url": "http://localhost:8080",
            "env": {
                "access_token": "tok_xxx",
            },
        }
        srv = _make_server(config=config)
        status = srv.get_status()

        cfg_out = status["config"]
        assert cfg_out["env"]["access_token"] == "<redacted>"


# ---------------------------------------------------------------------------
# Hardcoded secret validation
# ---------------------------------------------------------------------------


class TestHardcodedSecretValidation:
    """_validate_no_hardcoded_secrets must warn on known key prefixes."""

    def test_warns_on_sk_prefix(self, caplog):
        headers = {"Authorization": "sk-12345abcde"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "my-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_warns_on_ghp_prefix(self, caplog):
        headers = {"X-GitHub-Token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "gh-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_warns_on_xoxb_prefix(self, caplog):
        headers = {"X-Slack-Token": "xoxb-1234567890-abcdef"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "slack-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_no_warning_on_env_var_reference(self, caplog):
        headers = {"Authorization": "Bearer $MY_API_KEY"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "safe-server")
        assert "hardcoded secret" not in caplog.text.lower()

    def test_no_warning_on_non_secret_header(self, caplog):
        headers = {"X-Request-Id": "req-12345"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "safe-server")
        assert "hardcoded secret" not in caplog.text.lower()

    def test_warns_on_aws_key_prefix(self, caplog):
        headers = {"X-AWS-Key": "AKIAIOSFODNN7EXAMPLE"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "aws-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_empty_headers_no_warning(self, caplog):
        headers: dict[str, str] = {}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "empty-server")
        assert "hardcoded secret" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# _redact_config static method
# ---------------------------------------------------------------------------


class TestRedactConfigStatic:
    """redact_mcp_config covers headers and env fields."""

    def test_redacts_header_dict(self):
        config = {
            "headers": {"Authorization": "Bearer secret123"},
            "url": "http://x",
        }
        result = redact_mcp_config(config)
        assert result["headers"]["Authorization"] == "<redacted>"
        assert result["url"] == "http://x"

    def test_redacts_env_dict(self):
        config = {"env": {"api_key": "super-secret"}}
        result = redact_mcp_config(config)
        assert result["env"]["api_key"] == "<redacted>"

    def test_non_headers_env_passthrough(self):
        config = {"command": "node", "args": ["--verbose"]}
        result = redact_mcp_config(config)
        assert result == config


class TestRedactConfigUrlQueryParams:
    """_redact_config must redact secrets in URL query parameters."""

    def test_url_api_key_query_param_redacted(self):
        config = {"url": "https://api.example.com/v1?api_key=sk-secret123&format=json"}
        result = redact_mcp_config(config)
        assert "sk-secret123" not in str(result["url"])
        assert "<redacted>" in str(result["url"])
        assert "format=json" in str(result["url"])

    def test_url_access_token_query_param_redacted(self):
        config = {"url": "https://api.example.com/oauth?access_token=tok_abc&other=yes"}
        result = redact_mcp_config(config)
        assert "tok_abc" not in str(result["url"])
        assert "other=yes" in str(result["url"])

    def test_url_without_secrets_untouched(self):
        config = {"url": "https://api.example.com/v1?format=json"}
        result = redact_mcp_config(config)
        assert result["url"] == "https://api.example.com/v1?format=json"


class TestRedactConfigBearerInValues:
    """_redact_config must redact bearer tokens embedded in non-header/env values."""

    def test_bearer_in_arbitrary_string_field(self):
        config = {"description": "Auth: Bearer sk-abc123"}
        result = redact_mcp_config(config)
        assert "sk-abc123" not in str(result["description"])
        assert "Bearer <redacted>" in str(result["description"])

    def test_nested_json_with_secret(self):
        """A JSON string value containing secrets must be redacted."""
        config = {"payload": '{"access_token":"tok_abc"}'}
        result = redact_mcp_config(config)
        assert "tok_abc" not in str(result["payload"])
        assert "<redacted>" in str(result["payload"])


class TestRedactConfigEnvAssignmentBearer:
    """Env list entries with Bearer tokens must fully redact the token."""

    def test_env_list_bearer_not_leaked(self):
        config = {
            "url": "http://localhost:8080",
            "env": ["Authorization=Bearer sk-abc123"],
        }
        result = redact_mcp_config(config)
        env_str = str(result["env"])
        assert "sk-abc123" not in env_str
        assert "<redacted>" in env_str

    def test_env_list_basic_auth_not_leaked(self):
        config = {
            "url": "http://localhost:8080",
            "env": ["MY_TOKEN=Basic sk-abc123"],
        }
        result = redact_mcp_config(config)
        env_str = str(result["env"])
        assert "sk-abc123" not in env_str


class TestHardcodedSecretBearerPrefix:
    """_validate_no_hardcoded_secrets must catch Bearer sk-... values."""

    def test_warns_on_bearer_sk_prefix(self, caplog):
        headers = {"Authorization": "Bearer sk-12345abcde"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "my-server")
        assert "hardcoded secret" in caplog.text.lower()
        assert "sk-" in caplog.text

    def test_warns_on_bearer_ghp_prefix(self, caplog):
        headers = {"X-Token": "Bearer ghp_ABCDEFGHIJKLMNOPQR"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "gh-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_warns_on_basic_sk_prefix(self, caplog):
        headers = {"Authorization": "Basic sk-12345abcde"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "basic-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_no_warning_on_bearer_env_ref(self, caplog):
        headers = {"Authorization": "Bearer $MY_API_KEY"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "safe-server")
        assert "hardcoded secret" not in caplog.text.lower()


class TestContainsHardcodedSecret:
    """Unit tests for _contains_hardcoded_secret helper."""

    def test_returns_prefix_on_match(self):
        assert _contains_hardcoded_secret("sk-abc123") == "sk-"

    def test_returns_none_on_clean(self):
        assert _contains_hardcoded_secret("hello world") is None

    def test_returns_none_on_env_ref(self):
        assert _contains_hardcoded_secret("$MY_KEY") is None

    def test_finds_secret_after_bearer(self):
        assert _contains_hardcoded_secret("Bearer sk-abc") == "sk-"

    def test_finds_secret_after_basic(self):
        result = _contains_hardcoded_secret("Basic AKIA1234")
        assert result is not None
        assert result.lower() == "akia"


class TestValidateEnvListSecrets:
    """_validate_env_list_secrets must warn on KEY=VALUE entries with secrets."""

    def test_warns_on_sk_in_value(self, caplog):
        entries = ["API_KEY=sk-abc123", "NORMAL=hello"]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "list-server")
        assert "hardcoded secret" in caplog.text.lower()
        assert "api_key" in caplog.text.lower()

    def test_warns_on_bearer_in_value(self, caplog):
        entries = ["AUTH=Bearer sk-12345"]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "bearer-server")
        assert "hardcoded secret" in caplog.text.lower()

    def test_no_warning_on_env_ref_value(self, caplog):
        entries = ["API_KEY=$MY_SECRET"]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "safe-server")
        assert "hardcoded secret" not in caplog.text.lower()

    def test_no_warning_on_non_secret_value(self, caplog):
        entries = ["APP_NAME=myapp", "PORT=8080"]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "clean-server")
        assert "hardcoded secret" not in caplog.text.lower()

    def test_skips_entries_without_equals(self, caplog):
        entries = ["not-a-key-value-pair"]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "skip-server")
        assert "hardcoded secret" not in caplog.text.lower()

    def test_skips_non_string_entries(self, caplog):
        entries = [123]
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_env_list_secrets(entries, "skip-server")
        assert "hardcoded secret" not in caplog.text.lower()


class TestValidateDictSourceContext:
    """_validate_no_hardcoded_secrets includes source context in warnings."""

    def test_header_source_in_warning(self, caplog):
        headers = {"X-Key": "sk-abc"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(headers, "ctx-server", source="header")
        assert "header" in caplog.text.lower()

    def test_env_source_in_warning(self, caplog):
        env = {"MY_KEY": "sk-abc"}
        with caplog.at_level(logging.WARNING, logger="code_puppy.mcp_.secrets"):
            _validate_no_hardcoded_secrets(env, "ctx-server", source="env")
        assert "env" in caplog.text.lower()


class TestRedactHyphenatedKeys:
    """Hyphenated header/env keys like X-API-Key must match sensitive patterns."""

    def test_x_api_key_redacted(self):
        config = {"headers": {"X-API-Key": "abc123"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-API-Key"] == "<redacted>"

    def test_auth_token_redacted(self):
        config = {"headers": {"auth-token": "tok"}}
        result = redact_mcp_config(config)
        assert result["headers"]["auth-token"] == "<redacted>"

    def test_authorization_case_insensitive(self):
        """'Authorization' must redact regardless of case."""
        config = {"headers": {"authorization": "Bearer xyz"}}
        result = redact_mcp_config(config)
        assert result["headers"]["authorization"] == "<redacted>"

    def test_x_api_key_env_dict(self):
        """Env keys with hyphens also match after normalisation."""
        config = {"env": {"X-API-KEY": "secret"}}
        result = redact_mcp_config(config)
        assert result["env"]["X-API-KEY"] == "<redacted>"


class TestRedactValueScanning:
    """Values containing secrets must be redacted even when the key is not sensitive."""

    def test_value_with_sk_prefix_redacted(self):
        """Non-sensitive key but value starts with sk-: must redact."""
        config = {"headers": {"X-Custom": "sk-abc123"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-Custom"] == "<redacted>"

    def test_value_with_bearer_redacted(self):
        """Non-sensitive key but value is 'Bearer ...': must redact."""
        config = {"headers": {"X-Custom": "Bearer sk-abc123"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-Custom"] == "<redacted>"

    def test_value_with_basic_redacted(self):
        """Non-sensitive key but value is 'Basic ...': must redact."""
        config = {"headers": {"X-My-Auth": "Basic dXNlcjpwYXNz"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-My-Auth"] == "<redacted>"

    def test_value_with_ghp_prefix_redacted(self):
        config = {"headers": {"X-Extra": "ghp_ABCDEFGHIJKLMNOPQR"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-Extra"] == "<redacted>"

    def test_non_secret_value_preserved(self):
        """Values that are clearly not secrets must pass through."""
        config = {"headers": {"X-Request-Id": "req-12345"}}
        result = redact_mcp_config(config)
        assert result["headers"]["X-Request-Id"] == "req-12345"

    def test_env_value_with_sk_prefix_redacted(self):
        """Env dict with non-sensitive key but secret value: must redact."""
        config = {"env": {"MY_VAR": "sk-abc123"}}
        result = redact_mcp_config(config)
        assert result["env"]["MY_VAR"] == "<redacted>"

    def test_env_value_with_bearer_redacted(self):
        config = {"env": {"MY_VAR": "Bearer sk-abc123"}}
        result = redact_mcp_config(config)
        assert result["env"]["MY_VAR"] == "<redacted>"

    def test_env_non_secret_value_preserved(self):
        config = {"env": {"APP_NAME": "myapp"}}
        result = redact_mcp_config(config)
        assert result["env"]["APP_NAME"] == "myapp"


class TestRedactStaticMethodDelegates:
    """ManagedMCPServer._redact_config delegates to redact_mcp_config."""

    def test_delegates_correctly(self):
        config = {
            "headers": {"X-API-Key": "secret", "X-Custom": "sk-abc"},
            "url": "http://x",
        }
        assert ManagedMCPServer._redact_config(config) == redact_mcp_config(config)


class TestRedactEnvListValueScanning:
    """Env list entries with non-sensitive keys but secret values must be redacted."""

    def test_non_sensitive_key_with_sk_value_redacted(self):
        """MY_VAR=sk-abc123 must redact the value despite MY_VAR not being sensitive."""
        config = {"url": "http://x", "env": ["MY_VAR=sk-abc123"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["MY_VAR=<redacted>"]

    def test_non_sensitive_key_with_bearer_value_redacted(self):
        config = {"url": "http://x", "env": ["MY_VAR=Bearer sk-abc"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["MY_VAR=<redacted>"]

    def test_non_sensitive_key_with_ghp_value_redacted(self):
        config = {"url": "http://x", "env": ["MY_VAR=ghp_ABCDEFGH"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["MY_VAR=<redacted>"]

    def test_normal_value_preserved(self):
        """NORMAL=hello is not touched."""
        config = {"url": "http://x", "env": ["NORMAL=hello"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["NORMAL=hello"]

    def test_sensitive_key_redacted_even_with_plain_value(self):
        """OPENAI_API_KEY=whatever still redacts by key name."""
        config = {"url": "http://x", "env": ["OPENAI_API_KEY=whatever"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["OPENAI_API_KEY=<redacted>"]

    def test_non_string_entry_preserved(self):
        """Non-string entries in the list are passed through unchanged."""
        config = {"url": "http://x", "env": [42, None, "NORMAL=hello"]}
        result = redact_mcp_config(config)
        assert result["env"] == [42, None, "NORMAL=hello"]

    def test_entry_without_equals_preserved(self):
        """Entries without = are passed through redact_secrets unchanged."""
        config = {"url": "http://x", "env": ["JUST_A_STRING"]}
        result = redact_mcp_config(config)
        assert result["env"] == ["JUST_A_STRING"]
