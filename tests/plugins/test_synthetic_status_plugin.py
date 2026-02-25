"""Tests for Synthetic status plugin command handling and API parsing."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from code_puppy.plugins.synthetic_status import status_api
from code_puppy.plugins.synthetic_status.register_callbacks import (
    _custom_help,
    _handle_custom_command,
    _is_synthetic_only_provider_configured,
)
from code_puppy.plugins.synthetic_status.status_api import (
    SyntheticQuota,
    SyntheticQuotaResult,
)


def test_custom_help_has_expected_entries():
    entries = dict(_custom_help())
    assert "synthetic-status" in entries
    assert "provider" in entries
    assert "status" in entries


def test_fetch_synthetic_quota_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "subscription": {
            "limit": 135,
            "requests": 28.55,
            "renewsAt": "2025-10-27T02:01:31.030Z",
        }
    }

    with patch(
        "code_puppy.plugins.synthetic_status.status_api.requests.get"
    ) as mock_get:
        mock_get.return_value = mock_response
        result = status_api.fetch_synthetic_quota("test-key")

    assert result.ok is True
    assert result.quota is not None
    assert result.quota.limit == 135
    assert result.quota.requests_used == 28.55
    assert result.quota.renews_at_utc.tzinfo is not None
    assert result.quota.renews_at_utc.tzinfo == timezone.utc


def test_fetch_synthetic_quota_auth_error():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch(
        "code_puppy.plugins.synthetic_status.status_api.requests.get"
    ) as mock_get:
        mock_get.return_value = mock_response
        result = status_api.fetch_synthetic_quota("bad-key")

    assert result.ok is False
    assert "authentication failed" in (result.error or "").lower()


def test_fetch_synthetic_quota_invalid_payload():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"subscription": {"limit": "abc"}}

    with patch(
        "code_puppy.plugins.synthetic_status.status_api.requests.get"
    ) as mock_get:
        mock_get.return_value = mock_response
        result = status_api.fetch_synthetic_quota("test-key")

    assert result.ok is False
    assert "invalid numeric quota values" in (result.error or "").lower()


def test_fetch_synthetic_quota_timeout():
    with patch(
        "code_puppy.plugins.synthetic_status.status_api.requests.get",
        side_effect=status_api.requests.Timeout(),
    ):
        result = status_api.fetch_synthetic_quota("test-key")

    assert result.ok is False
    assert "timed out" in (result.error or "").lower()


def test_is_synthetic_only_provider_configured_true():
    def fake_get_api_key(env_name: str) -> str | None:
        return "x" if env_name == "SYN_API_KEY" else None

    with patch(
        "code_puppy.plugins.synthetic_status.register_callbacks.get_api_key",
        side_effect=fake_get_api_key,
    ):
        assert _is_synthetic_only_provider_configured() is True


def test_is_synthetic_only_provider_configured_false():
    def fake_get_api_key(env_name: str) -> str | None:
        if env_name in {"SYN_API_KEY", "OPENAI_API_KEY"}:
            return "x"
        return None

    with patch(
        "code_puppy.plugins.synthetic_status.register_callbacks.get_api_key",
        side_effect=fake_get_api_key,
    ):
        assert _is_synthetic_only_provider_configured() is False


def test_handle_provider_synthetic_status_command():
    quota = SyntheticQuota(
        limit=100,
        requests_used=25,
        renews_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    with (
        patch(
            "code_puppy.plugins.synthetic_status.register_callbacks.resolve_syn_api_key",
            return_value="test-key",
        ),
        patch(
            "code_puppy.plugins.synthetic_status.register_callbacks.fetch_synthetic_quota",
            return_value=SyntheticQuotaResult(quota=quota),
        ),
        patch(
            "code_puppy.plugins.synthetic_status.register_callbacks.emit_info"
        ) as mock_info,
    ):
        result = _handle_custom_command("/provider synthetic status", "provider")

    assert result is True
    assert mock_info.called


def test_handle_provider_other_is_not_owned():
    result = _handle_custom_command("/provider openai status", "provider")
    assert result is None


def test_handle_status_ambiguous_provider_message():
    with (
        patch(
            "code_puppy.plugins.synthetic_status.register_callbacks._is_synthetic_only_provider_configured",
            return_value=False,
        ),
        patch(
            "code_puppy.plugins.synthetic_status.register_callbacks.emit_warning"
        ) as mock_warning,
    ):
        result = _handle_custom_command("/status", "status")

    assert result is True
    assert mock_warning.called
