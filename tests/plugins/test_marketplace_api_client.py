"""Tests for the Agent Marketplace API client.

Tests the authentication headers and user groups functionality.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest


class TestGetUserGroups:
    """Tests for _get_user_groups function."""

    def test_returns_groups_from_token_file(self, tmp_path):
        """Should return groups from marketplace_token.json."""
        from code_puppy.plugins.agent_marketplace import api_client

        # Create a mock token file with groups
        token_data = {
            "accessToken": "test-token",
            "user": {
                "id": "test@walmart.com",
                "groups": ["group1", "group2", "ad-test-group"]
            }
        }
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        # Patch CONFIG_DIR at the point of use
        with patch.object(api_client, "Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda self, x: token_file if x == "marketplace_token.json" else tmp_path / x
            mock_path_cls.return_value = tmp_path
            
            # Actually, let's patch the config module import
            with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)):
                groups = api_client._get_user_groups()

        assert groups == ["group1", "group2", "ad-test-group"]

    def test_returns_empty_list_when_no_file(self, tmp_path):
        """Should return empty list when token file doesn't exist."""
        from code_puppy.plugins.agent_marketplace import api_client

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)):
            groups = api_client._get_user_groups()

        assert groups == []

    def test_returns_empty_list_when_no_groups_field(self, tmp_path):
        """Should return empty list when user has no groups field."""
        from code_puppy.plugins.agent_marketplace import api_client

        token_data = {
            "accessToken": "test-token",
            "user": {
                "id": "test@walmart.com"
                # No groups field
            }
        }
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)):
            groups = api_client._get_user_groups()

        assert groups == []

    def test_returns_empty_list_on_invalid_json(self, tmp_path):
        """Should return empty list when token file is invalid JSON."""
        from code_puppy.plugins.agent_marketplace import api_client

        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text("not valid json {{{")

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)):
            groups = api_client._get_user_groups()

        assert groups == []

    def test_returns_empty_list_when_groups_not_a_list(self, tmp_path):
        """Should return empty list when groups is not a list."""
        from code_puppy.plugins.agent_marketplace import api_client

        token_data = {
            "accessToken": "test-token",
            "user": {
                "id": "test@walmart.com",
                "groups": "not-a-list"  # Wrong type
            }
        }
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)):
            groups = api_client._get_user_groups()

        assert groups == []


class TestGetAuthHeaders:
    """Tests for _get_auth_headers function."""

    def test_includes_user_groups_header(self, tmp_path):
        """Should include X-User-Groups header when groups are available."""
        from code_puppy.plugins.agent_marketplace import api_client

        # Create mock token file with groups
        token_data = {
            "accessToken": "test-token",
            "user": {
                "id": "test@walmart.com",
                "groups": ["colony-agent-builders", "element.users", "gcp-all-users"]
            }
        }
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)), \
             patch.object(api_client, "_get_marketplace_token", return_value="valid-token"), \
             patch.object(api_client, "is_token_expired", return_value=False):
            headers = api_client._get_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer valid-token"
        assert "X-User-Groups" in headers
        assert headers["X-User-Groups"] == "colony-agent-builders,element.users,gcp-all-users"

    def test_no_groups_header_when_no_groups(self, tmp_path):
        """Should not include X-User-Groups header when no groups available."""
        from code_puppy.plugins.agent_marketplace import api_client

        # Empty token file (no groups)
        token_data = {"accessToken": "test-token", "user": {}}
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)), \
             patch.object(api_client, "_get_marketplace_token", return_value="valid-token"), \
             patch.object(api_client, "is_token_expired", return_value=False):
            headers = api_client._get_auth_headers()

        assert "Authorization" in headers
        assert "X-User-Groups" not in headers

    def test_limits_groups_to_100(self, tmp_path):
        """Should limit groups to 100 to avoid header size issues."""
        from code_puppy.plugins.agent_marketplace import api_client

        # Create 150 groups
        many_groups = [f"group-{i}" for i in range(150)]
        token_data = {
            "accessToken": "test-token",
            "user": {
                "id": "test@walmart.com",
                "groups": many_groups
            }
        }
        token_file = tmp_path / "marketplace_token.json"
        token_file.write_text(json.dumps(token_data))

        with patch("code_puppy.config.CONFIG_DIR", str(tmp_path)), \
             patch.object(api_client, "_get_marketplace_token", return_value="valid-token"), \
             patch.object(api_client, "is_token_expired", return_value=False):
            headers = api_client._get_auth_headers()

        # Should only have 100 groups
        groups_header = headers.get("X-User-Groups", "")
        groups_count = len(groups_header.split(","))
        assert groups_count == 100

    def test_returns_empty_dict_when_no_token(self):
        """Should return empty dict when no token available."""
        from code_puppy.plugins.agent_marketplace import api_client

        with patch.object(api_client, "_get_marketplace_token", return_value=None):
            headers = api_client._get_auth_headers()

        assert headers == {}

    def test_returns_empty_dict_when_token_expired(self):
        """Should return empty dict when token is expired."""
        from code_puppy.plugins.agent_marketplace import api_client

        with patch.object(api_client, "_get_marketplace_token", return_value="expired-token"), \
             patch.object(api_client, "is_token_expired", return_value=True):
            headers = api_client._get_auth_headers()

        assert headers == {}
