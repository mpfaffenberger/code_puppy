"""Unit tests for MS Graph common utilities including truncation."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.common import (
    truncate_content,
    truncate_list_response,
    apply_response_limit,
    MAX_RESPONSE_CHARS,
    msgraph_api_request,
    msgraph_authenticate,
    get_current_user_identity,
    should_skip_approval,
    require_user_approval,
    UserRejectedError,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestTruncateContent:
    """Test suite for truncate_content utility."""

    def test_truncate_content_no_truncation_needed(self):
        """Test that short content is not truncated."""
        content = "This is a short message."
        result = truncate_content(content)

        assert result["content"] == content
        assert result["truncated"] is False
        assert result["char_offset"] == 0
        assert result["next_offset"] is None
        assert result["total_chars"] == len(content)

    def test_truncate_content_truncation_applied(self):
        """Test that long content is truncated at max_chars."""
        # Create content larger than the limit
        content = "A" * 15000
        result = truncate_content(content, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is True
        assert result["char_offset"] == 0
        assert result["next_offset"] == 10000
        assert result["total_chars"] == 15000
        assert "message" in result

    def test_truncate_content_with_offset(self):
        """Test truncation with character offset."""
        content = "A" * 15000
        result = truncate_content(content, char_offset=5000, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is False  # Remaining after offset is exactly 10000
        assert result["char_offset"] == 5000
        assert result["next_offset"] is None
        assert result["total_chars"] == 15000

    def test_truncate_content_offset_with_more_truncation(self):
        """Test that offset + remaining content still needs truncation."""
        content = "A" * 25000
        result = truncate_content(content, char_offset=5000, max_chars=10000)

        assert len(result["content"]) == 10000
        assert result["truncated"] is True
        assert result["char_offset"] == 5000
        assert result["next_offset"] == 15000
        assert result["total_chars"] == 25000

    def test_truncate_content_offset_exceeds_length(self):
        """Test that offset beyond content length returns empty."""
        content = "A" * 100
        result = truncate_content(content, char_offset=200)

        assert result["content"] == ""
        assert result["truncated"] is False
        assert result["char_offset"] == 200
        assert result["next_offset"] is None
        assert result["total_chars"] == 100
        assert "message" in result  # Should have a message about offset exceeding

    def test_truncate_content_custom_max_chars(self):
        """Test truncation with custom max_chars limit."""
        content = "A" * 500
        result = truncate_content(content, max_chars=100)

        assert len(result["content"]) == 100
        assert result["truncated"] is True
        assert result["next_offset"] == 100

    def test_truncate_content_empty_string(self):
        """Test truncation with empty content."""
        result = truncate_content("")

        assert result["content"] == ""
        assert result["truncated"] is False
        assert result["total_chars"] == 0


class TestTruncateListResponse:
    """Test suite for truncate_list_response utility."""

    def test_truncate_list_no_truncation_needed(self):
        """Test that small lists are not truncated."""
        items = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
        result = truncate_list_response(items)

        assert result["items"] == items
        assert result["truncated"] is False
        assert result["item_offset"] == 0
        assert result["next_offset"] is None
        assert result["items_returned"] == 2
        assert result["total_items"] == 2

    def test_truncate_list_truncation_applied(self):
        """Test that large lists are truncated to fit max_chars."""
        # Create items that exceed the limit
        items = [{"id": i, "data": "X" * 500} for i in range(50)]
        result = truncate_list_response(items, max_chars=5000)

        assert len(result["items"]) < 50
        assert result["truncated"] is True
        assert result["next_offset"] is not None
        assert result["items_returned"] < 50
        assert "message" in result

    def test_truncate_list_with_item_offset(self):
        """Test list truncation with item offset."""
        items = [{"id": i, "name": f"Item {i}"} for i in range(20)]
        result = truncate_list_response(items, char_offset=10)

        # Should skip first 10 items
        assert result["items"][0]["id"] == 10
        assert result["item_offset"] == 10
        assert result["items_returned"] == 10

    def test_truncate_list_offset_exceeds_length(self):
        """Test that offset beyond list length returns empty."""
        items = [{"id": i} for i in range(5)]
        result = truncate_list_response(items, char_offset=10)

        assert result["items"] == []
        assert result["truncated"] is False
        assert result["items_returned"] == 0
        assert result["total_items"] == 5

    def test_truncate_list_empty_list(self):
        """Test truncation with empty list."""
        result = truncate_list_response([])

        assert result["items"] == []
        assert result["truncated"] is False
        assert result["items_returned"] == 0
        assert result["total_items"] == 0

    def test_truncate_list_single_large_item(self):
        """Test truncation when single item exceeds limit."""
        # Single item that's too large
        items = [{"data": "X" * 20000}]
        result = truncate_list_response(items, max_chars=1000)

        # Should return empty since no items fit
        assert result["items"] == []
        assert result["truncated"] is True


class TestApplyResponseLimit:
    """Test suite for apply_response_limit utility."""

    def test_apply_response_limit_no_truncation(self):
        """Test that small responses pass through unchanged."""
        response = {"success": True, "data": "small data"}
        result = apply_response_limit(response)

        assert result == response
        assert "_truncation_warning" not in result

    def test_apply_response_limit_adds_warning(self):
        """Test that large responses get warning metadata."""
        response = {"success": True, "body": "X" * 20000}
        result = apply_response_limit(response, max_chars=5000)

        assert "_response_size" in result
        assert "_truncation_warning" in result

    def test_apply_response_limit_truncates_large_fields(self):
        """Test that known large fields are truncated."""
        response = {"success": True, "body": "X" * 20000}
        result = apply_response_limit(response, max_chars=5000)

        # Body field should be truncated
        assert len(result["body"]) < 20000
        assert result.get("_body_truncated") is True
        assert result.get("_body_original_length") == 20000


class TestMsgraphApiRequest:
    """Test suite for msgraph_api_request tool."""

    def test_msgraph_api_request_get(self, mock_context):
        """Test GET request."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"id": "123", "name": "Test"}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/profile"
            )

            assert result["success"] is True
            assert result["method"] == "GET"
            assert result["endpoint"] == "/me/profile"
            assert result["truncated"] is False

    def test_msgraph_api_request_post(self, mock_context):
        """Test POST request."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "new-123"}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context,
                method="POST",
                endpoint="/me/messages",
                body={"subject": "Test"},
            )

            assert result["success"] is True
            assert result["method"] == "POST"
            mock_client.post.assert_called_once()

    def test_msgraph_api_request_invalid_method(self, mock_context):
        """Test invalid HTTP method."""
        result = msgraph_api_request(
            mock_context, method="INVALID", endpoint="/me/profile"
        )

        assert result["success"] is False
        assert result["error_type"] == "invalid_method"

    def test_msgraph_api_request_empty_endpoint(self, mock_context):
        """Test empty endpoint."""
        result = msgraph_api_request(mock_context, method="GET", endpoint="")

        assert result["success"] is False
        assert result["error_type"] == "invalid_endpoint"

    def test_msgraph_api_request_large_response_truncation(self, mock_context):
        """Test that large responses are truncated."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Return a large response
            mock_client.get.return_value = {"data": "X" * 15000}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/large-data"
            )

            assert result["success"] is True
            assert result["truncated"] is True
            assert result["total_chars"] > MAX_RESPONSE_CHARS
            assert result["next_offset"] is not None

    def test_msgraph_api_request_with_char_offset(self, mock_context):
        """Test char_offset parameter for pagination."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"data": "X" * 15000}
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context,
                method="GET",
                endpoint="/me/large-data",
                char_offset=10000,
            )

            assert result["success"] is True
            assert result["char_offset"] == 10000

    def test_msgraph_api_request_auth_error(self, mock_context):
        """Test authentication error handling."""
        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_api_request(
                mock_context, method="GET", endpoint="/me/profile"
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMsgraphAuthenticate:
    """Test suite for msgraph_authenticate tool."""

    def test_msgraph_authenticate_success(self, mock_context):
        """Test successful authentication."""
        with patch(
            "code_puppy.plugins.walmart_specific.msgraph_auth.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.return_value = "Authentication successful"

            result = msgraph_authenticate(mock_context)

            assert result["success"] is True
            assert "successful" in result["message"].lower()

    def test_msgraph_authenticate_failure(self, mock_context):
        """Test failed authentication."""
        with patch(
            "code_puppy.plugins.walmart_specific.msgraph_auth.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.return_value = "Authentication failed"

            result = msgraph_authenticate(mock_context)

            assert result["success"] is False

    def test_msgraph_authenticate_exception(self, mock_context):
        """Test authentication exception handling."""
        with patch(
            "code_puppy.plugins.walmart_specific.msgraph_auth.handle_msgraph_auth_command"
        ) as mock_auth:
            mock_auth.side_effect = Exception("Network error")

            result = msgraph_authenticate(mock_context)

            assert result["success"] is False
            assert "error" in result


class TestMaxResponseCharsConstant:
    """Test the MAX_RESPONSE_CHARS constant."""

    def test_max_response_chars_value(self):
        """Test that MAX_RESPONSE_CHARS is set to 10,000."""
        assert MAX_RESPONSE_CHARS == 10_000

    def test_max_response_chars_used_by_default(self):
        """Test that truncation uses MAX_RESPONSE_CHARS by default."""
        content = "A" * 15000
        result = truncate_content(content)

        assert len(result["content"]) == MAX_RESPONSE_CHARS
        assert result["next_offset"] == MAX_RESPONSE_CHARS


# =============================================================================
# APPROVAL SKIP TESTS (PUP-14)
# =============================================================================


class TestGetCurrentUserIdentity:
    """Test suite for get_current_user_identity helper."""

    def test_get_current_user_identity_success(self):
        """Test fetching current user identity from MS Graph."""
        # Clear cache first
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = None

        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "USER-123",
                "mail": "Test.User@walmart.com",
                "userPrincipalName": "test.user@walmart.com",
            }
            mock_get_client.return_value = mock_client

            result = get_current_user_identity()

            assert result is not None
            assert result["id"] == "user-123"  # Lowercased
            assert result["mail"] == "test.user@walmart.com"  # Lowercased
            assert result["upn"] == "test.user@walmart.com"  # Lowercased

        # Clear cache after test
        common_module._current_user_cache = None

    def test_get_current_user_identity_cached(self):
        """Test that identity is cached after first call."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = None

        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "USER-123",
                "mail": "test@example.com",
                "userPrincipalName": "test@example.com",
            }
            mock_get_client.return_value = mock_client

            # First call
            result1 = get_current_user_identity()
            # Second call
            result2 = get_current_user_identity()

            # Should only call the API once
            assert mock_client.get.call_count == 1
            assert result1 == result2

        common_module._current_user_cache = None

    def test_get_current_user_identity_api_failure(self):
        """Test graceful handling when API call fails."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = None

        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = Exception("Network error")
            mock_get_client.return_value = mock_client

            result = get_current_user_identity()

            assert result is None  # Should return None, not raise

        common_module._current_user_cache = None


class TestShouldSkipApproval:
    """Test suite for should_skip_approval function."""

    def test_skip_when_sending_to_self_by_email(self):
        """Test skip when recipient matches current user's email."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(["me@walmart.com"])

        assert should_skip is True
        assert "self" in reason.lower()

        common_module._current_user_cache = None

    def test_skip_when_sending_to_self_by_upn(self):
        """Test skip when recipient matches current user's UPN."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "my.upn@walmart.com",
        }

        should_skip, reason = should_skip_approval(["MY.UPN@walmart.com"])  # Case insensitive

        assert should_skip is True
        assert "self" in reason.lower()

        common_module._current_user_cache = None

    def test_skip_when_sending_to_self_by_id(self):
        """Test skip when recipient matches current user's ID."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "abc-123-def",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(["ABC-123-DEF"])  # Case insensitive

        assert should_skip is True
        assert "self" in reason.lower()

        common_module._current_user_cache = None

    def test_no_skip_when_sending_to_others(self):
        """Test no skip when sending to other users."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(["someone.else@walmart.com"])

        assert should_skip is False
        assert reason is None

        common_module._current_user_cache = None

    def test_no_skip_when_mixed_recipients(self):
        """Test no skip when some recipients are self and some are others."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(
            ["me@walmart.com", "someone.else@walmart.com"]
        )

        assert should_skip is False
        assert reason is None

        common_module._current_user_cache = None

    def test_no_skip_when_empty_recipients(self):
        """Test no skip when recipients list is empty."""
        should_skip, reason = should_skip_approval([])

        assert should_skip is False
        assert reason is None

    def test_no_skip_when_recipients_is_none(self):
        """Test handling of None recipients."""
        # should_skip_approval expects a list, but we want to ensure
        # the caller passes an empty list for None case
        should_skip, reason = should_skip_approval([])

        assert should_skip is False
        assert reason is None

    def test_no_skip_when_current_user_unavailable(self):
        """Test no skip when we can't fetch current user."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = None

        with patch(
            "code_puppy.tools.msgraph.common.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = Exception("Network error")
            mock_get_client.return_value = mock_client

            should_skip, reason = should_skip_approval(["anyone@walmart.com"])

            assert should_skip is False
            assert reason is None

        common_module._current_user_cache = None

    def test_handles_whitespace_in_recipients(self):
        """Test that whitespace in recipients is handled."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(["  me@walmart.com  "])

        assert should_skip is True

        common_module._current_user_cache = None


class TestRequireUserApprovalWithSkip:
    """Test suite for require_user_approval with skip functionality."""

    def test_skips_approval_when_sending_to_self(self):
        """Test that approval is skipped for self-send."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.tools.msgraph.common.emit_info"
        ) as mock_emit:
            # Should NOT raise, should NOT call approval TUI
            require_user_approval(
                "Send Email",
                {"To": "me@walmart.com", "Subject": "Test"},
                recipients=["me@walmart.com"],
            )

            # Should have emitted skip message
            mock_emit.assert_called_once()
            call_arg = mock_emit.call_args[0][0]
            assert "self" in call_arg.lower()

        common_module._current_user_cache = None

    def test_requires_approval_when_sending_to_others(self):
        """Test that approval is required for non-self recipients."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.tools.msgraph.approval_tui.request_approval"
        ) as mock_request:
            mock_request.return_value = False  # User rejects

            with pytest.raises(UserRejectedError):
                require_user_approval(
                    "Send Email",
                    {"To": "other@walmart.com", "Subject": "Test"},
                    recipients=["other@walmart.com"],
                )

            # Should have called approval TUI
            mock_request.assert_called_once()

        common_module._current_user_cache = None

    def test_backwards_compatible_without_recipients(self):
        """Test that require_user_approval works without recipients arg."""
        with patch(
            "code_puppy.tools.msgraph.approval_tui.request_approval"
        ) as mock_request:
            mock_request.return_value = True  # User approves

            # Should work without recipients argument (backwards compatible)
            require_user_approval(
                "Send Email",
                {"To": "anyone@walmart.com", "Subject": "Test"},
            )

            mock_request.assert_called_once()


class TestApprovalWhitelist:
    """Test suite for context-specific whitelist-based approval skip."""

    def test_mail_whitelist_works_for_mail_context(self):
        """Test that mail whitelist applies to mail context."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["boss@walmart.com", "team@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["boss@walmart.com"], context="mail"
            )

            assert should_skip is True
            assert "whitelist" in reason.lower()

        common_module._current_user_cache = None

    def test_mail_whitelist_does_not_apply_to_teams(self):
        """Test that mail whitelist does NOT apply to teams context."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_mail_whitelist, patch(
            "code_puppy.config.get_msgraph_teams_whitelist"
        ) as mock_teams_whitelist:
            mock_mail_whitelist.return_value = ["boss@walmart.com"]
            mock_teams_whitelist.return_value = []  # Empty teams whitelist

            should_skip, reason = should_skip_approval(
                ["boss@walmart.com"], context="teams"
            )

            assert should_skip is False
            assert reason is None

        common_module._current_user_cache = None

    def test_teams_whitelist_works_for_teams_context(self):
        """Test that teams whitelist applies to teams context."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_teams_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["coworker@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["coworker@walmart.com"], context="teams"
            )

            assert should_skip is True
            assert "whitelist" in reason.lower()

        common_module._current_user_cache = None

    def test_teams_whitelist_does_not_apply_to_mail(self):
        """Test that teams whitelist does NOT apply to mail context."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_mail_whitelist, patch(
            "code_puppy.config.get_msgraph_teams_whitelist"
        ) as mock_teams_whitelist:
            mock_mail_whitelist.return_value = []  # Empty mail whitelist
            mock_teams_whitelist.return_value = ["coworker@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["coworker@walmart.com"], context="mail"
            )

            assert should_skip is False
            assert reason is None

        common_module._current_user_cache = None

    def test_multiple_whitelisted_recipients_skip(self):
        """Test that multiple whitelisted recipients all skip."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["boss@walmart.com", "team@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["boss@walmart.com", "team@walmart.com"], context="mail"
            )

            assert should_skip is True

        common_module._current_user_cache = None

    def test_partial_whitelist_requires_approval(self):
        """Test that mixed whitelisted/non-whitelisted requires approval."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["boss@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["boss@walmart.com", "stranger@walmart.com"], context="mail"
            )

            assert should_skip is False
            assert reason is None

        common_module._current_user_cache = None

    def test_self_plus_whitelisted_skips(self):
        """Test that combining self and whitelisted recipients skips."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["boss@walmart.com"]

            should_skip, reason = should_skip_approval(
                ["me@walmart.com", "boss@walmart.com"], context="mail"
            )

            assert should_skip is True

        common_module._current_user_cache = None

    def test_empty_whitelist_falls_back_to_self_check(self):
        """Test that empty whitelist still allows self-send."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = []  # Empty whitelist

            # Self-send should still work
            should_skip, reason = should_skip_approval(
                ["me@walmart.com"], context="mail"
            )
            assert should_skip is True
            assert "self" in reason.lower()

            # Other recipients should require approval
            should_skip, reason = should_skip_approval(
                ["other@walmart.com"], context="mail"
            )
            assert should_skip is False

        common_module._current_user_cache = None

    def test_whitelist_case_insensitive(self):
        """Test that whitelist matching is case-insensitive."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        with patch(
            "code_puppy.config.get_msgraph_mail_whitelist"
        ) as mock_whitelist:
            mock_whitelist.return_value = ["boss@walmart.com"]  # lowercase

            # Should match regardless of case
            should_skip, reason = should_skip_approval(
                ["BOSS@WALMART.COM"], context="mail"
            )

            assert should_skip is True

        common_module._current_user_cache = None


class TestTeamsSelfChatSkip:
    """Test suite for Teams 48:notes self-chat skip."""

    def test_48_notes_skips_approval(self):
        """Test that 48:notes (Teams self-chat) skips confirmation."""
        # Should work without any user cache
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = None

        should_skip, reason = should_skip_approval(["48:notes"])

        assert should_skip is True
        assert "48:notes" in reason

    def test_48_notes_case_insensitive(self):
        """Test that 48:notes matching is case-insensitive."""
        should_skip, reason = should_skip_approval(["48:NOTES"])
        assert should_skip is True

        should_skip, reason = should_skip_approval(["48:Notes"])
        assert should_skip is True

    def test_random_chat_id_requires_approval(self):
        """Test that random chat IDs still require approval."""
        should_skip, reason = should_skip_approval(["19:abc123@thread.tacv2"])
        assert should_skip is False
        assert reason is None

    def test_48_notes_mixed_with_other_requires_approval(self):
        """Test that 48:notes + another recipient requires approval."""
        import code_puppy.tools.msgraph.common as common_module
        common_module._current_user_cache = {
            "id": "user-123",
            "mail": "me@walmart.com",
            "upn": "me@walmart.com",
        }

        should_skip, reason = should_skip_approval(["48:notes", "other@walmart.com"])

        assert should_skip is False
        assert reason is None

        common_module._current_user_cache = None
