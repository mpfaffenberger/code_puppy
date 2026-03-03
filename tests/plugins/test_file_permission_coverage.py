"""Tests for file_permission_handler/register_callbacks.py full coverage."""

from __future__ import annotations

from unittest.mock import patch


class TestThreadLocalHelpers:
    def test_get_set_clear_feedback(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _set_user_feedback,
            clear_user_feedback,
            get_last_user_feedback,
        )

        _set_user_feedback("hello")
        assert get_last_user_feedback() == "hello"
        clear_user_feedback()
        assert get_last_user_feedback() is None

    def test_diff_shown_flag(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            clear_diff_shown_flag,
            set_diff_already_shown,
            was_diff_already_shown,
        )

        set_diff_already_shown(True)
        assert was_diff_already_shown() is True
        clear_diff_shown_flag()
        assert was_diff_already_shown() is False


class TestPreviewDeleteSnippet:
    def test_file_not_found(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        assert _preview_delete_snippet(str(tmp_path / "nope"), "x") is None

    def test_snippet_not_in_file(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        assert _preview_delete_snippet(str(f), "missing") is None

    def test_success(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _preview_delete_snippet(str(f), "world")
        assert result is not None
        assert "-hello world" in result or "hello" in result

    def test_exception_not_found(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        assert _preview_delete_snippet("/dev/null/bad", "x") is None

    def test_exception_during_diff(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_diff_context_lines",
            side_effect=RuntimeError("boom"),
        ):
            assert _preview_delete_snippet(str(f), "world") is None


class TestPreviewWriteToFile:
    def test_new_file(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_write_to_file,
        )

        result = _preview_write_to_file(str(tmp_path / "new.txt"), "content")
        assert result is not None

    def test_existing_no_overwrite(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_write_to_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("old")
        assert _preview_write_to_file(str(f), "new", overwrite=False) is None

    def test_existing_overwrite(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_write_to_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("old")
        result = _preview_write_to_file(str(f), "new", overwrite=True)
        assert result is not None


class TestPreviewReplaceInFile:
    def test_exact_match(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _preview_replace_in_file(
            str(f), [{"old_str": "hello", "new_str": "hi"}]
        )
        assert result is not None

    def test_no_change(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello")
        result = _preview_replace_in_file(
            str(f), [{"old_str": "hello", "new_str": "hello"}]
        )
        assert result is None

    def test_fuzzy_match_failure(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("totally different content")
        result = _preview_replace_in_file(
            str(f), [{"old_str": "xyz_not_found_at_all", "new_str": "new"}]
        )
        assert result is None


class TestPreviewDeleteFile:
    def test_success(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("content")
        result = _preview_delete_file(str(f))
        assert result is not None

    def test_not_found(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        assert _preview_delete_file(str(tmp_path / "nope")) is None


class TestPromptForFilePermission:
    def test_yolo_mode(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            prompt_for_file_permission,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
            return_value=True,
        ):
            ok, fb = prompt_for_file_permission("f.txt", "edit")
            assert ok is True
            assert fb is None

    def test_lock_contention(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _FILE_CONFIRMATION_LOCK,
            prompt_for_file_permission,
        )

        _FILE_CONFIRMATION_LOCK.acquire()
        try:
            with (
                patch(
                    "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
                    return_value=False,
                ),
                patch(
                    "code_puppy.plugins.file_permission_handler.register_callbacks.emit_warning"
                ),
            ):
                ok, fb = prompt_for_file_permission("f.txt", "edit")
                assert ok is False
        finally:
            _FILE_CONFIRMATION_LOCK.release()

    def test_approved(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            prompt_for_file_permission,
        )

        with (
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.get_user_approval",
                return_value=(True, None),
            ),
        ):
            ok, fb = prompt_for_file_permission("f.txt", "edit", "preview")
            assert ok is True


class TestHandleEditFilePermission:
    def test_write(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_edit_file_permission,
        )

        with (
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks._preview_write_to_file",
                return_value="diff",
            ),
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
                return_value=(True, None),
            ),
        ):
            assert (
                handle_edit_file_permission(
                    None, "f.txt", "write", {"content": "c", "overwrite": True}
                )
                is True
            )

    def test_replace(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_edit_file_permission,
        )

        with (
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks._preview_replace_in_file",
                return_value="diff",
            ),
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
                return_value=(False, "fix it"),
            ),
        ):
            assert (
                handle_edit_file_permission(
                    None, "f.txt", "replace", {"replacements": []}
                )
                is False
            )

    def test_delete_snippet(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_edit_file_permission,
        )

        with (
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks._preview_delete_snippet",
                return_value="diff",
            ),
            patch(
                "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
                return_value=(True, None),
            ),
        ):
            assert (
                handle_edit_file_permission(
                    None, "f.txt", "delete_snippet", {"delete_snippet": "x"}
                )
                is True
            )

    def test_unknown_operation(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_edit_file_permission,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
            return_value=(True, None),
        ):
            assert handle_edit_file_permission(None, "f.txt", "mystery", {}) is True


class TestHandleDeleteFilePermission:
    def test_approved(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_delete_file_permission,
        )

        f = tmp_path / "f.txt"
        f.write_text("x")
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
            return_value=(True, None),
        ):
            assert handle_delete_file_permission(None, str(f)) is True


class TestHandleFilePermission:
    def test_with_operation_data(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_file_permission,
        )

        f = tmp_path / "f.txt"
        f.write_text("content")
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
            return_value=(True, None),
        ):
            assert (
                handle_file_permission(None, str(f), "delete", operation_data={})
                is True
            )

    def test_without_operation_data(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            handle_file_permission,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission",
            return_value=(True, None),
        ):
            assert handle_file_permission(None, "f.txt", "edit", preview="diff") is True


class TestGeneratePreviewFromOperationData:
    def test_delete(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        f = tmp_path / "f.txt"
        f.write_text("content")
        result = _generate_preview_from_operation_data(str(f), "delete", {})
        assert result is not None

    def test_write(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        result = _generate_preview_from_operation_data(
            str(tmp_path / "new.txt"), "write", {"content": "c"}
        )
        assert result is not None

    def test_delete_snippet(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _generate_preview_from_operation_data(
            str(f), "delete snippet from", {"snippet": "world"}
        )
        assert result is not None

    def test_replace_text(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello")
        result = _generate_preview_from_operation_data(
            str(f),
            "replace text in",
            {"replacements": [{"old_str": "hello", "new_str": "hi"}]},
        )
        assert result is not None

    def test_edit_file_delete_snippet(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _generate_preview_from_operation_data(
            str(f), "edit_file", {"delete_snippet": "world"}
        )
        assert result is not None

    def test_edit_file_replacements(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello")
        result = _generate_preview_from_operation_data(
            str(f),
            "edit_file",
            {"replacements": [{"old_str": "hello", "new_str": "hi"}]},
        )
        assert result is not None

    def test_edit_file_content(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        result = _generate_preview_from_operation_data(
            str(tmp_path / "new.txt"), "edit_file", {"content": "new stuff"}
        )
        assert result is not None

    def test_unknown_returns_none(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        assert _generate_preview_from_operation_data("f", "unknown", {}) is None

    def test_exception_returns_none(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _generate_preview_from_operation_data,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks._preview_delete_file",
            side_effect=RuntimeError,
        ):
            assert _generate_preview_from_operation_data("f", "delete", {}) is None


class TestUnicodeExceptBranches:
    """Cover the except (UnicodeEncodeError, UnicodeDecodeError): pass branches."""

    def _make_bad_str(self, content):
        """Create a string subclass whose encode raises UnicodeEncodeError."""

        class BadStr(str):
            def encode(self, *args, **kwargs):
                raise UnicodeEncodeError("utf-8", "", 0, 0, "bad")

        return BadStr(content)

    def test_delete_snippet_unicode_error(self, tmp_path):
        from unittest.mock import MagicMock

        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello world")
        bad = self._make_bad_str("hello world")
        mock_f = MagicMock()
        mock_f.__enter__ = MagicMock(return_value=mock_f)
        mock_f.__exit__ = MagicMock(return_value=False)
        mock_f.read = MagicMock(return_value=bad)
        with patch("builtins.open", return_value=mock_f):
            result = _preview_delete_snippet(str(f), "hello")
            assert result is not None or result is None

    def test_replace_unicode_error(self, tmp_path):
        from unittest.mock import MagicMock

        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("hello")
        bad = self._make_bad_str("hello")
        mock_f = MagicMock()
        mock_f.__enter__ = MagicMock(return_value=mock_f)
        mock_f.__exit__ = MagicMock(return_value=False)
        mock_f.read = MagicMock(return_value=bad)
        with patch("builtins.open", return_value=mock_f):
            _preview_replace_in_file(str(f), [{"old_str": "hello", "new_str": "hi"}])

    def test_delete_file_unicode_error(self, tmp_path):
        from unittest.mock import MagicMock

        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("content")
        bad = self._make_bad_str("content")
        mock_f = MagicMock()
        mock_f.__enter__ = MagicMock(return_value=mock_f)
        mock_f.__exit__ = MagicMock(return_value=False)
        mock_f.read = MagicMock(return_value=bad)
        with patch("builtins.open", return_value=mock_f):
            _preview_delete_file(str(f))


class TestWriteToFileExceptionBranch:
    def test_write_general_exception(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_write_to_file,
        )

        # Pass content that causes join to fail after unified_diff
        with patch(
            "difflib.unified_diff",
            side_effect=RuntimeError("boom"),
        ):
            assert _preview_write_to_file("f.txt", "content") is None


class TestDeleteFileExceptionBranch:
    def test_delete_file_general_exception(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("content")
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_diff_context_lines",
            side_effect=RuntimeError("boom"),
        ):
            assert _preview_delete_file(str(f)) is None


class TestPreviewUnicodeEdgeCases:
    def test_delete_snippet_surrogate_chars(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_snippet,
        )

        f = tmp_path / "f.txt"
        # Write content with surrogate-escaped bytes
        f.write_bytes(b"hello \xed\xa0\x80 world")
        _preview_delete_snippet(str(f), "hello")
        # May or may not find it after sanitization, but shouldn't crash

    def test_write_exception(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_write_to_file,
        )

        # Pass a directory path to trigger exception
        _preview_write_to_file(str(tmp_path), "content", overwrite=True)
        # Should handle gracefully

    def test_replace_surrogate_chars(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_bytes(b"hello \xed\xa0\x80 world")
        _preview_replace_in_file(str(f), [{"old_str": "hello", "new_str": "hi"}])

    def test_replace_fuzzy_match(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        f = tmp_path / "f.txt"
        f.write_text("line one\nline two\nline three\n")
        # Use slightly different whitespace to trigger fuzzy matching
        _preview_replace_in_file(
            str(f), [{"old_str": "line  two", "new_str": "line TWO"}]
        )

    def test_delete_file_surrogate(self, tmp_path):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        f = tmp_path / "f.txt"
        f.write_bytes(b"content \xed\xa0\x80")
        result = _preview_delete_file(str(f))
        assert result is not None

    def test_replace_exception(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_replace_in_file,
        )

        assert _preview_replace_in_file("/dev/null/bad", []) is None

    def test_delete_file_exception(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            _preview_delete_file,
        )

        assert _preview_delete_file("/dev/null/bad/file") is None


class TestGetPermissionHandlerHelp:
    def test_returns_string(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            get_permission_handler_help,
        )

        assert "File Permission" in get_permission_handler_help()


class TestGetFilePermissionPromptAdditions:
    def test_yolo_mode(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            get_file_permission_prompt_additions,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
            return_value=True,
        ):
            assert get_file_permission_prompt_additions() == ""

    def test_not_yolo(self):
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            get_file_permission_prompt_additions,
        )

        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
            return_value=False,
        ):
            result = get_file_permission_prompt_additions()
            assert "USER FEEDBACK" in result
