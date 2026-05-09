"""Security regression tests for secret redaction and private file storage."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import patch


from code_puppy.secret_storage import (
    atomic_write_private_json,
    ensure_private_dir,
    warn_or_fix_private_file_mode,
)
from code_puppy.security.redaction import redact_secrets


class TestRedactSecrets:
    """Test that redact_secrets scrubs known secret patterns."""

    def test_redacts_url_query_token(self):
        url = "https://example.com/api?access_token=sekrit&foo=bar"
        result = redact_secrets(url)
        assert "sekrit" not in result
        assert "<redacted>" in result
        assert "foo=bar" in result

    def test_redacts_json_sensitive_keys(self):
        payload = {
            "access_token": "super-secret",
            "refresh_token": "another-secret",
            "user": "alice",
        }
        result = redact_secrets(payload)
        assert result["access_token"] == "<redacted>"
        assert result["refresh_token"] == "<redacted>"
        assert result["user"] == "alice"

    def test_redacts_bearer_header(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result
        assert "Bearer <redacted>" in result

    def test_redacts_bearer_standalone(self):
        text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result
        assert "Bearer <redacted>" in result

    def test_redacts_nested_dict_and_list(self):
        data = [
            {"api_key": "key123"},
            "Bearer token456",
        ]
        result = redact_secrets(data)
        assert result[0]["api_key"] == "<redacted>"
        assert "token456" not in result[1]
        assert "Bearer <redacted>" in result[1]

    def test_redacts_env_assignment(self):
        text = "MY_API_KEY=secret123 OTHER=value"
        result = redact_secrets(text)
        assert "secret123" not in result
        assert "MY_API_KEY=<redacted>" in result
        assert "OTHER=value" in result

    def test_redacts_env_assignment_with_spaces_in_value(self):
        """Values containing whitespace (e.g. Bearer tokens) must be fully redacted."""
        text = "Authorization=Bearer sk-abc123"
        result = redact_secrets(text)
        assert "sk-abc123" not in result
        assert "<redacted>" in result

    def test_redacts_env_assignment_basic_auth_with_spaces(self):
        """Basic auth with a space-separated secret must not leak the token."""
        text = "AUTHORIZATION=Basic sk-abc123"
        result = redact_secrets(text)
        assert "sk-abc123" not in result
        assert "<redacted>" in result

    def test_env_assignment_preserves_ampersand_separated_pairs(self):
        """URL query strings with & separators must not over-consume."""
        text = "access_token=sekrit&foo=bar"
        result = redact_secrets(text)
        assert "sekrit" not in result
        assert "foo=bar" in result

    def test_env_assignment_multi_value_with_spaces(self):
        """Multi-assignment strings must preserve later pairs."""
        text = "MY_TOKEN=Bearer sk-abc123 OTHER=val"
        result = redact_secrets(text)
        assert "sk-abc123" not in result
        assert "OTHER=val" in result

    def test_redacts_bytes(self):
        raw = b'{"access_token":"tok"}'
        result = redact_secrets(raw)
        assert result == '{"access_token":"<redacted>"}'

    def test_no_token_length_metadata(self):
        """Ensure redaction does not embed token length hints."""
        payload = {"access_token": "a" * 100}
        result = redact_secrets(payload)
        assert result["access_token"] == "<redacted>"


class TestAtomicWritePrivateJson:
    """Test atomic private file writes."""

    def test_creates_file_with_mode_0o600(self, tmp_path: Path):
        target = tmp_path / "secrets.json"
        atomic_write_private_json(target, {"key": "value"})
        assert target.exists()
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    def test_no_tmp_file_left_behind(self, tmp_path: Path):
        target = tmp_path / "secrets.json"
        atomic_write_private_json(target, {"key": "value"})
        tmp_candidates = list(tmp_path.glob("*.tmp"))
        assert not tmp_candidates

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "secrets.json"
        target.write_text("old")
        atomic_write_private_json(target, {"key": "new"})
        data = json.loads(target.read_text())
        assert data == {"key": "new"}


class TestEnsurePrivateDir:
    """Test directory permission helpers."""

    def test_creates_dir_with_mode_0o700(self, tmp_path: Path):
        d = tmp_path / "deep" / "private"
        ensure_private_dir(d)
        assert d.exists()
        mode = stat.S_IMODE(d.stat().st_mode)
        assert mode == 0o700

    def test_fixes_broad_mode(self, tmp_path: Path):
        d = tmp_path / "loose"
        d.mkdir()
        d.chmod(0o755)
        ensure_private_dir(d)
        mode = stat.S_IMODE(d.stat().st_mode)
        assert mode == 0o700


class TestWarnOrFixPrivateFileMode:
    """Test permission repair on existing files."""

    def test_fixes_broad_mode_and_warns(self, tmp_path: Path):
        f = tmp_path / "tokens.json"
        f.write_text("{}")
        f.chmod(0o644)
        with patch("code_puppy.secret_storage.logger") as mock_logger:
            warn_or_fix_private_file_mode(f)
        mode = stat.S_IMODE(f.stat().st_mode)
        assert mode == 0o600
        mock_logger.warning.assert_called_once()

    def test_no_op_for_correct_mode(self, tmp_path: Path):
        f = tmp_path / "tokens.json"
        f.write_text("{}")
        f.chmod(0o600)
        with patch("code_puppy.secret_storage.logger") as mock_logger:
            warn_or_fix_private_file_mode(f)
        mock_logger.warning.assert_not_called()
