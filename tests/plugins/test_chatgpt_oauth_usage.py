from unittest.mock import Mock, patch

from code_puppy_core_plugins.chatgpt_oauth import usage


def test_parse_usage_payload_formats_remaining_percentages():
    parsed = usage.parse_usage_payload(
        {
            "rate_limit": {
                "primary_window": {"used_percent": 34},
                "secondary_window": {"used_percent": 10.4},
            }
        }
    )

    assert parsed is not None
    assert parsed.primary_remaining == 66
    assert parsed.secondary_remaining == 90
    assert parsed.format_status() == "5h 66% remaining · week 90% remaining"


def test_parse_usage_payload_rejects_missing_windows():
    assert usage.parse_usage_payload({"rate_limit": {}}) is None
    assert usage.parse_usage_payload(None) is None


def test_refresh_usage_fetches_wham_endpoint_in_background():
    response = Mock()
    response.json.return_value = {
        "rate_limit": {"primary_window": {"used_percent": 25}}
    }
    response.raise_for_status.return_value = None

    # _fetch writes a module-level cache; restore prior state so the leak
    # doesn't pollute later tests (e.g. spinner context formatting).
    cached_before, fetching_before = usage._cached_usage, usage._fetch_in_progress
    try:
        with patch.object(usage.requests, "get", return_value=response) as get:
            usage._fetch("token", "account")

        assert usage.get_usage_status() == "5h 75% remaining"
        get.assert_called_once_with(
            "https://chatgpt.com/backend-api/wham/usage",
            headers={
                "Authorization": "Bearer token",
                "ChatGPT-Account-Id": "account",
                "Accept": "application/json",
                "originator": "codex_cli_rs",
            },
            timeout=10,
        )
    finally:
        usage._cached_usage = cached_before
        usage._fetch_in_progress = fetching_before
