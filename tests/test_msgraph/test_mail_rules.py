"""Tests for mail rules management."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.mail_rules import (
    msgraph_list_mail_rules,
    msgraph_get_mail_rule,
    msgraph_create_mail_rule,
    msgraph_update_mail_rule,
    msgraph_delete_mail_rule,
    msgraph_create_noise_filter_rule,
    msgraph_list_mail_folders,
    _format_rule,
)


@pytest.fixture
def mock_ctx():
    """Create a mock context."""
    return MagicMock()


@pytest.fixture
def sample_rule():
    """Sample mail rule data."""
    return {
        "id": "rule-123",
        "displayName": "Test Rule",
        "sequence": 1,
        "isEnabled": True,
        "conditions": {
            "fromAddresses": [{"emailAddress": {"address": "test@example.com"}}],
            "subjectContains": ["newsletter"],
        },
        "actions": {
            "delete": True,
            "stopProcessingRules": True,
        },
    }


class TestFormatRule:
    """Tests for _format_rule helper."""

    def test_format_basic_rule(self, sample_rule):
        """Test formatting a basic rule."""
        result = _format_rule(sample_rule)
        assert result["id"] == "rule-123"
        assert result["name"] == "Test Rule"
        assert result["sequence"] == 1
        assert result["is_enabled"] is True
        assert "delete" in result["actions"]
        assert "stop_processing" in result["actions"]

    def test_format_rule_with_move_action(self):
        """Test formatting a rule with move action."""
        rule = {
            "id": "rule-456",
            "displayName": "Move Rule",
            "actions": {"moveToFolder": "folder-id"},
            "conditions": {},
        }
        result = _format_rule(rule)
        assert "move" in result["actions"]

    def test_format_rule_with_forward_action(self):
        """Test formatting a rule with forward action."""
        rule = {
            "id": "rule-789",
            "displayName": "Forward Rule",
            "actions": {"forwardTo": [{"emailAddress": {"address": "fwd@example.com"}}]},
            "conditions": {},
        }
        result = _format_rule(rule)
        assert "forward" in result["actions"]

    def test_format_rule_with_multiple_conditions(self):
        """Test formatting with multiple condition types."""
        rule = {
            "id": "rule-multi",
            "displayName": "Multi Condition",
            "conditions": {
                "fromAddresses": [{"emailAddress": {"address": "a@b.com"}}],
                "subjectContains": ["urgent"],
                "senderContains": ["acme.com"],
            },
            "actions": {},
        }
        result = _format_rule(rule)
        assert len(result["conditions"]) == 3

    def test_format_rule_empty(self):
        """Test formatting an empty rule."""
        result = _format_rule({})
        assert result["name"] == "Unnamed Rule"
        assert result["actions"] == ["unknown"]
        assert result["conditions"] == ["unknown"]


class TestListMailRules:
    """Tests for msgraph_list_mail_rules."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_list_rules_success(self, mock_client, mock_ctx, sample_rule):
        """Test listing mail rules successfully."""
        mock_client.return_value.get.return_value = {"value": [sample_rule]}

        result = msgraph_list_mail_rules(mock_ctx)

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["rules"]) == 1
        assert result["rules"][0]["name"] == "Test Rule"

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_list_rules_groups_by_action(self, mock_client, mock_ctx):
        """Test that rules are grouped by action type."""
        rules = [
            {"id": "1", "displayName": "Rule 1", "actions": {"delete": True}, "conditions": {}},
            {"id": "2", "displayName": "Rule 2", "actions": {"delete": True}, "conditions": {}},
            {"id": "3", "displayName": "Rule 3", "actions": {"moveToFolder": "x"}, "conditions": {}},
        ]
        mock_client.return_value.get.return_value = {"value": rules}

        result = msgraph_list_mail_rules(mock_ctx)

        assert "delete" in result["by_action"]
        assert len(result["by_action"]["delete"]) == 2

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_list_rules_not_authenticated(self, mock_client, mock_ctx):
        """Test listing when not authenticated."""
        mock_client.return_value = None

        result = msgraph_list_mail_rules(mock_ctx)

        assert result["success"] is False


class TestGetMailRule:
    """Tests for msgraph_get_mail_rule."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_get_rule_success(self, mock_client, mock_ctx, sample_rule):
        """Test getting a specific rule."""
        mock_client.return_value.get.return_value = sample_rule

        result = msgraph_get_mail_rule(mock_ctx, rule_id="rule-123")

        assert result["success"] is True
        assert result["rule"]["name"] == "Test Rule"

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_get_rule_not_found(self, mock_client, mock_ctx):
        """Test getting a non-existent rule."""
        mock_client.return_value.get.side_effect = Exception("Not found")

        result = msgraph_get_mail_rule(mock_ctx, rule_id="nonexistent")

        assert result["success"] is False


class TestCreateMailRule:
    """Tests for msgraph_create_mail_rule."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_rule_success(self, mock_client, mock_ctx, sample_rule):
        """Test creating a mail rule."""
        mock_client.return_value.post.return_value = sample_rule

        result = msgraph_create_mail_rule(
            mock_ctx,
            name="Test Rule",
            conditions={"subjectContains": ["test"]},
            actions={"delete": True},
        )

        assert result["success"] is True
        assert "rule" in result
        mock_client.return_value.post.assert_called_once()

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_rule_with_options(self, mock_client, mock_ctx, sample_rule):
        """Test creating a rule with all options."""
        mock_client.return_value.post.return_value = sample_rule

        result = msgraph_create_mail_rule(
            mock_ctx,
            name="Full Options Rule",
            conditions={"fromAddresses": [{"emailAddress": {"address": "x@y.com"}}]},
            actions={"moveToFolder": "folder-id"},
            is_enabled=False,
            stop_processing=False,
        )

        assert result["success"] is True
        call_args = mock_client.return_value.post.call_args
        payload = call_args[1]["json"]
        assert payload["isEnabled"] is False
        assert payload["actions"]["stopProcessingRules"] is False


class TestUpdateMailRule:
    """Tests for msgraph_update_mail_rule."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_update_rule_name(self, mock_client, mock_ctx, sample_rule):
        """Test updating a rule's name."""
        mock_client.return_value.patch.return_value = sample_rule

        result = msgraph_update_mail_rule(
            mock_ctx, rule_id="rule-123", name="New Name"
        )

        assert result["success"] is True
        mock_client.return_value.patch.assert_called_once()

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_update_rule_no_changes(self, mock_client, mock_ctx):
        """Test updating with no changes."""
        result = msgraph_update_mail_rule(mock_ctx, rule_id="rule-123")

        assert result["success"] is False
        assert "No updates" in result["error"]

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_update_rule_enable_disable(self, mock_client, mock_ctx, sample_rule):
        """Test enabling/disabling a rule."""
        mock_client.return_value.patch.return_value = sample_rule

        result = msgraph_update_mail_rule(
            mock_ctx, rule_id="rule-123", is_enabled=False
        )

        assert result["success"] is True
        call_args = mock_client.return_value.patch.call_args
        assert call_args[1]["json"]["isEnabled"] is False


class TestDeleteMailRule:
    """Tests for msgraph_delete_mail_rule."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_delete_rule_success(self, mock_client, mock_ctx):
        """Test deleting a rule."""
        mock_client.return_value.delete.return_value = None

        result = msgraph_delete_mail_rule(mock_ctx, rule_id="rule-123")

        assert result["success"] is True
        mock_client.return_value.delete.assert_called_once()

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_delete_rule_not_found(self, mock_client, mock_ctx):
        """Test deleting a non-existent rule."""
        mock_client.return_value.delete.side_effect = Exception("Not found")

        result = msgraph_delete_mail_rule(mock_ctx, rule_id="nonexistent")

        assert result["success"] is False


class TestCreateNoiseFilterRule:
    """Tests for msgraph_create_noise_filter_rule."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_noise_filter_delete(self, mock_client, mock_ctx):
        """Test creating a noise filter with delete action."""
        mock_client.return_value.post.return_value = {
            "id": "noise-1",
            "displayName": "Noise Filter",
            "actions": {"delete": True},
            "conditions": {},
        }

        result = msgraph_create_noise_filter_rule(
            mock_ctx,
            name="Newsletter Noise",
            from_addresses=["newsletter@spam.com"],
            action="delete",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_noise_filter_archive(self, mock_client, mock_ctx):
        """Test creating a noise filter with archive action."""
        mock_client.return_value.get.return_value = {"id": "archive-folder"}
        mock_client.return_value.post.return_value = {
            "id": "noise-2",
            "displayName": "Archive Filter",
            "actions": {"moveToFolder": "archive-folder"},
            "conditions": {},
        }

        result = msgraph_create_noise_filter_rule(
            mock_ctx,
            name="Archive Spam",
            subject_contains=["unsubscribe"],
            action="archive",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_noise_filter_move_creates_folder(self, mock_client, mock_ctx):
        """Test creating a noise filter that creates a new folder."""
        mock_client.return_value.get.return_value = {"value": []}  # No existing folder
        mock_client.return_value.post.side_effect = [
            {"id": "new-folder-id"},  # Create folder
            {"id": "rule-id", "displayName": "Test", "actions": {}, "conditions": {}},  # Create rule
        ]

        result = msgraph_create_noise_filter_rule(
            mock_ctx,
            name="Move to Folder",
            sender_contains=["noreply"],
            action="move",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_create_noise_filter_no_conditions(self, mock_client, mock_ctx):
        """Test creating a noise filter with no conditions fails."""
        result = msgraph_create_noise_filter_rule(
            mock_ctx,
            name="Empty Filter",
            action="delete",
        )

        assert result["success"] is False
        assert "At least one condition" in result["error"]


class TestListMailFolders:
    """Tests for msgraph_list_mail_folders."""

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_list_folders_success(self, mock_client, mock_ctx):
        """Test listing mail folders."""
        mock_client.return_value.get.return_value = {
            "value": [
                {
                    "id": "inbox-id",
                    "displayName": "Inbox",
                    "unreadItemCount": 5,
                    "totalItemCount": 100,
                    "childFolderCount": 0,
                },
                {
                    "id": "sent-id",
                    "displayName": "Sent Items",
                    "unreadItemCount": 0,
                    "totalItemCount": 50,
                    "childFolderCount": 0,
                },
            ]
        }

        result = msgraph_list_mail_folders(mock_ctx)

        assert result["success"] is True
        assert result["count"] == 2
        assert result["folders"][0]["name"] == "Inbox"

    @patch("code_puppy.tools.msgraph.mail_rules.get_msgraph_client")
    def test_list_folders_with_children(self, mock_client, mock_ctx):
        """Test listing folders including children."""
        mock_client.return_value.get.side_effect = [
            {
                "value": [
                    {
                        "id": "parent-id",
                        "displayName": "Parent",
                        "childFolderCount": 1,
                        "unreadItemCount": 0,
                        "totalItemCount": 10,
                    }
                ]
            },
            {
                "value": [
                    {
                        "id": "child-id",
                        "displayName": "Child",
                        "unreadItemCount": 2,
                        "totalItemCount": 5,
                    }
                ]
            },
        ]

        result = msgraph_list_mail_folders(mock_ctx, include_children=True)

        assert result["success"] is True
        assert result["count"] == 2
        assert result["folders"][1]["name"] == "Parent/Child"
