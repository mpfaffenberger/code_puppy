from unittest.mock import AsyncMock, patch

from code_puppy.permissions import (
    PermissionMode,
    authorize_file_operation,
    authorize_shell_command,
    get_permission_mode,
)


def test_explicit_permission_modes():
    for configured, expected in (
        ("ask", PermissionMode.ASK),
        ("acceptEdits", PermissionMode.ACCEPT_EDITS),
        ("auto", PermissionMode.AUTO),
    ):
        with patch("code_puppy.config.get_value", return_value=configured):
            assert get_permission_mode() is expected


def test_accept_edits_allows_files_without_prompt():
    with (
        patch(
            "code_puppy.permissions.get_permission_mode",
            return_value=PermissionMode.ACCEPT_EDITS,
        ),
        patch("code_puppy.tools.common.get_user_approval") as approval,
    ):
        assert authorize_file_operation("x.py", "write") is True
        approval.assert_not_called()


def test_ask_file_permission_fails_when_rejected():
    with (
        patch(
            "code_puppy.permissions.get_permission_mode",
            return_value=PermissionMode.ASK,
        ),
        patch("code_puppy.tools.common.get_user_approval", return_value=(False, None)),
    ):
        assert authorize_file_operation("x.py", "write") is False


async def test_accept_edits_still_prompts_for_shell():
    approval = AsyncMock(return_value=(False, "no"))
    with (
        patch(
            "code_puppy.permissions.get_permission_mode",
            return_value=PermissionMode.ACCEPT_EDITS,
        ),
        patch("code_puppy.tools.common.get_user_approval_async", approval),
    ):
        assert await authorize_shell_command("git status") == (False, "no")


async def test_force_prompt_overrides_auto_mode():
    approval = AsyncMock(return_value=(True, None))
    with (
        patch(
            "code_puppy.permissions.get_permission_mode",
            return_value=PermissionMode.AUTO,
        ),
        patch("code_puppy.tools.common.get_user_approval_async", approval),
    ):
        assert await authorize_shell_command("git status", force_prompt=True) == (
            True,
            None,
        )
        approval.assert_awaited_once()
