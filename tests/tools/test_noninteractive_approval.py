from unittest.mock import MagicMock, patch

from code_puppy.callbacks import _callbacks, clear_callbacks, register_callback
from code_puppy.plugins.file_permission_handler.register_callbacks import (
    handle_file_permission,
)
from code_puppy.tools.file_modifications import write_to_file


class _NonTtyStdin:
    def isatty(self) -> bool:
        return False


def test_get_user_approval_fails_closed_without_tty():
    from code_puppy.tools.common import get_user_approval

    with (
        patch("code_puppy.tools.common.sys.stdin", new=_NonTtyStdin()),
        patch("code_puppy.tools.common.arrow_select") as mock_select,
        patch("code_puppy.tools.common.Console"),
        patch("code_puppy.tools.common.time.sleep", return_value=None),
    ):
        approved, feedback = get_user_approval("Test", "content", mist_name="Rex")

    assert approved is False
    assert feedback is None
    mock_select.assert_not_called()


async def test_get_user_approval_async_fails_closed_without_tty():
    from code_puppy.tools.common import get_user_approval_async

    with (
        patch("code_puppy.tools.common.sys.stdin", new=_NonTtyStdin()),
        patch("code_puppy.tools.common.arrow_select_async") as mock_select,
        patch("code_puppy.tools.common.Console"),
    ):
        approved, feedback = await get_user_approval_async(
            "Test", "content", mist_name="Rex"
        )

    assert approved is False
    assert feedback is None
    mock_select.assert_not_called()


def test_write_to_file_fails_closed_without_tty(tmp_path):
    target = tmp_path / "probe.txt"
    original_callbacks = _callbacks["file_permission"].copy()

    try:
        clear_callbacks("file_permission")
        register_callback("file_permission", handle_file_permission)

        with (
            patch("code_puppy.tools.common.sys.stdin", new=_NonTtyStdin()),
            patch("code_puppy.tools.common.arrow_select") as mock_select,
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
                return_value=False,
            ),
            patch("code_puppy.tools.common.Console"),
            patch("code_puppy.tools.common.time.sleep", return_value=None),
        ):
            result = write_to_file(MagicMock(), str(target), "changed by test\n", False)
    finally:
        _callbacks["file_permission"] = original_callbacks

    assert result["success"] is False
    assert result["changed"] is False
    assert result["user_rejection"] is True
    assert result["user_feedback"] is None
    assert target.exists() is False
    mock_select.assert_not_called()
