"""Regression coverage for safe deletion previews and deletion results."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.text import Text

from code_puppy.tools import deletion_preview
from code_puppy.tools.deletion_preview import (
    PlainTextDeletionPreview,
    classify_deletion_content,
    create_deletion_diff,
)


@pytest.mark.parametrize(
    "raw",
    [
        "plain UTF-8 text\nreplacement character: \ufffd\n".encode(),
        "BOM text\n".encode("utf-8-sig"),
        "BOM text\n".encode("utf-16"),
        b"\xfe\xff" + "BOM text\n".encode("utf-16-be"),
        "BOM text\n".encode("utf-32"),
        b"\x00\x00\xfe\xff" + "BOM text\n".encode("utf-32-be"),
    ],
)
def test_supported_utf8_and_bom_text_is_preserved(raw):
    result = classify_deletion_content(raw)

    assert result.kind == "text"
    assert result.size_bytes == len(raw)
    assert result.text is not None
    assert "BOM text" in result.text or "plain UTF-8 text" in result.text


@pytest.mark.parametrize(
    "raw",
    [
        b"PK\x03\x04zip fixture\x00payload",
        b"bad UTF-8: \xff\xfe",
        b"embedded escape: \x1b[31mred\x1b[0m",
        b"C1 byte invalid UTF-8: \x85",
        "UTF-8 encoded C1 control: \u0085".encode("utf-8"),
        b"DEL control: \x7f",
        b"bare carriage return: first\rsecond\n",
        b"truncated UTF-8 BOM: \xef\xbb\xbf\xff",
        b"truncated UTF-16 BOM: \xff\xfe\x00",
        b"truncated UTF-32 BOM: \x00\x00\xfe\xff\x00",
        "Unicode line separator: \u2028".encode("utf-8"),
        "Unicode paragraph separator: \u2029".encode("utf-8"),
    ],
)
def test_binary_invalid_or_unsafe_bytes_are_omitted(raw):
    result = classify_deletion_content(raw)

    assert result.kind == "omitted"
    assert result.text is None
    assert result.size_bytes == len(raw)


def test_empty_crlf_and_literal_replacement_text_are_preserved():
    assert classify_deletion_content(b"").kind == "text"
    crlf = classify_deletion_content("tab\there\r\nnext line\n".encode())
    assert crlf.kind == "text"
    assert crlf.text == "tab\there\r\nnext line\n"

    # Backend strings are inspected as-is, not re-encoded or lossily decoded.
    literal_replacement = classify_deletion_content("literal \ufffd remains")
    assert literal_replacement.kind == "text"
    assert literal_replacement.text == "literal \ufffd remains"
    assert literal_replacement.size_bytes is None

    unsafe_backend_text = classify_deletion_content("secret\x00control")
    assert unsafe_backend_text.kind == "omitted"
    assert unsafe_backend_text.omission_reason == "unsafe"
    assert unsafe_backend_text.size_bytes is None

    backend_surrogate = classify_deletion_content("secret\udcff")
    assert backend_surrogate.kind == "omitted"
    assert backend_surrogate.omission_reason == "unsafe"
    assert backend_surrogate.size_bytes is None


def test_unified_diff_preserves_text_and_escapes_control_filename():
    diff = create_deletion_diff("bad\x1bname\nnext.txt", "ordinary\n", 3)

    assert "ordinary" in diff
    assert "bad\\x1bname\\x0anext.txt" in diff
    assert "\x1b" not in diff


def test_omission_summary_is_plain_text_not_a_termflow_diff(monkeypatch, tmp_path):
    from code_puppy.tools import common
    from code_puppy.tools.file_modifications import _deletion_permission_preview

    target = tmp_path / "archive.zip"
    target.write_bytes(b"PK\x03\x04\x00fixture")
    preparation = deletion_preview.prepare_deletion(str(target))
    preview = _deletion_permission_preview(str(target), preparation)

    assert isinstance(preview, PlainTextDeletionPreview)
    assert str(len(b"PK\x03\x04\x00fixture")) in preview
    assert "binary file" in preview
    assert "PK" not in preview
    assert "\x1b" not in preview

    monkeypatch.setattr(
        common,
        "format_diff_with_colors",
        lambda *_args, **_kwargs: pytest.fail("plain summary passed to diff renderer"),
    )
    rendered, is_diff = common._approval_preview_text(preview)
    assert isinstance(rendered, Text)
    assert rendered.plain == str(preview)
    assert is_diff is False


def test_plain_summary_does_not_mark_diff_shown_but_real_diff_does(monkeypatch):
    from code_puppy.tools import common

    shown = []
    monkeypatch.setattr(common, "set_diff_already_shown", shown.append)
    monkeypatch.setattr(
        common, "format_diff_with_colors", lambda _diff: Text("formatted diff")
    )

    summary_panel = Text()
    common._append_approval_preview(
        summary_panel, PlainTextDeletionPreview("Text preview omitted.")
    )
    assert "Text preview omitted." in summary_panel.plain
    assert shown == []

    diff_panel = Text()
    common._append_approval_preview(diff_panel, "--- a/file.txt\n+++ b/file.txt\n")
    assert "formatted diff" in diff_panel.plain
    assert shown == [True]


def _register_real_permission_callback(monkeypatch, *, approved, captured):
    import code_puppy.callbacks as callbacks

    permission = importlib.import_module(
        "code_puppy_core_plugins.file_permission_handler.register_callbacks"
    )

    async def prompt(path, operation, preview, message_group):
        captured.update(path=path, operation=operation, preview=preview)
        return approved, None

    def regenerate_preview(*_args):
        raise AssertionError("permission callback regenerated the safe preview")

    monkeypatch.setattr(permission, "prompt_for_file_permission_async", prompt)
    monkeypatch.setattr(
        permission, "_generate_preview_from_operation_data", regenerate_preview
    )
    callbacks.clear_callbacks("file_permission")
    callbacks.register_callback(
        "file_permission", permission.handle_file_permission_async
    )


def test_sync_delete_real_permission_callback_omits_binary_and_keeps_approval(
    monkeypatch, tmp_path
):
    import code_puppy.tools.file_modifications as modifications

    target = tmp_path / "archive.bin"
    raw = b"PK\x03\x04secret\x00payload"
    target.write_bytes(raw)
    captured = {}
    emitted = []

    monkeypatch.setattr(modifications.UndoManager, "record_change", lambda *_args: None)
    monkeypatch.setattr(
        modifications, "_emit_diff_message", lambda *args: emitted.append(args)
    )
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)

    result = modifications._delete_file(MagicMock(), str(target))

    assert captured["operation"] == "delete"
    assert isinstance(captured["preview"], PlainTextDeletionPreview)
    assert str(len(raw)) in captured["preview"]
    assert "secret" not in captured["preview"]
    assert result["success"] is True
    assert result["diff"] == ""
    assert str(len(raw)) in result["message"]
    assert "secret" not in result["message"]
    assert emitted == []
    assert not target.exists()


def test_sync_text_delete_keeps_unified_diff(monkeypatch, tmp_path):
    import code_puppy.tools.file_modifications as modifications

    target = tmp_path / "ordinary.txt"
    target.write_text("first line\nsecond line\n", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(modifications.UndoManager, "record_change", lambda *_args: None)
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)

    result = modifications._delete_file(MagicMock(), str(target))

    assert result["success"] is True
    assert "--- a/ordinary.txt" in result["diff"]
    assert "-first line" in result["diff"]
    assert "-second line" in result["diff"]
    assert "binary file" not in captured["preview"]
    assert not target.exists()


def test_delete_denial_preserves_binary_without_returning_payload(
    monkeypatch, tmp_path
):
    import code_puppy.tools.file_modifications as modifications

    target = tmp_path / "denied.bin"
    raw = b"secret\x00binary"
    target.write_bytes(raw)
    captured = {}

    monkeypatch.setattr(modifications.UndoManager, "record_change", lambda *_args: None)
    _register_real_permission_callback(monkeypatch, approved=False, captured=captured)

    result = modifications._delete_file(MagicMock(), str(target))

    assert result["success"] is False
    assert target.read_bytes() == raw
    assert isinstance(captured["preview"], PlainTextDeletionPreview)
    assert "secret" not in captured["preview"]
    assert "diff" not in result


@pytest.mark.asyncio
async def test_async_delete_uses_backend_text_as_is_off_event_loop(monkeypatch):
    import code_puppy.tools.file_modifications as modifications
    from code_puppy.tools.io_backends import set_filesystem_backend

    class Backend:
        deleted = False

        @staticmethod
        def _assert_worker_thread():
            with pytest.raises(RuntimeError, match="no running event loop"):
                asyncio.get_running_loop()

        def exists(self, _path):
            self._assert_worker_thread()
            return True

        def is_file(self, _path):
            self._assert_worker_thread()
            return True

        def read_text_file(self, _path, line=None, limit=None):
            self._assert_worker_thread()
            assert line is None and limit is None
            return "backend text with \ufffd\n"

        def delete_file(self, _path):
            self._assert_worker_thread()
            self.deleted = True

    backend = Backend()
    captured = {}
    monkeypatch.setattr(modifications, "_emit_diff_message", lambda *_args: None)
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)
    monkeypatch.setattr(
        deletion_preview,
        "open",
        lambda *_args, **_kwargs: pytest.fail("backend deletion bypassed the backend"),
        raising=False,
    )
    set_filesystem_backend(backend)
    try:
        result = await modifications._delete_file_async(
            MagicMock(), "/virtual/file.txt"
        )
    finally:
        set_filesystem_backend(None)

    assert captured["operation"] == "delete"
    assert "backend text with \ufffd" in captured["preview"]
    assert backend.deleted is True
    assert result["success"] is True
    assert "backend text with \ufffd" in result["diff"]


@pytest.mark.asyncio
async def test_backend_unsafe_text_has_unknown_size_and_no_diff(monkeypatch):
    import code_puppy.tools.file_modifications as modifications
    from code_puppy.tools.io_backends import set_filesystem_backend

    class Backend:
        deleted = False

        def exists(self, _path):
            return True

        def is_file(self, _path):
            return True

        def read_text_file(self, _path, line=None, limit=None):
            return "secret\x00unsafe"

        def delete_file(self, _path):
            self.deleted = True

    backend = Backend()
    captured = {}
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)
    monkeypatch.setattr(
        modifications,
        "_emit_diff_message",
        lambda *_args: pytest.fail("unsafe backend text emitted a diff"),
    )
    set_filesystem_backend(backend)
    try:
        result = await modifications._delete_file_async(
            MagicMock(), "/virtual/unsafe.txt"
        )
    finally:
        set_filesystem_backend(None)

    assert isinstance(captured["preview"], PlainTextDeletionPreview)
    assert "size unavailable" in captured["preview"]
    assert "secret" not in captured["preview"]
    assert result["success"] is True
    assert result["diff"] == ""
    assert "size unavailable" in result["message"]
    assert "secret" not in result["message"]
    assert backend.deleted is True


def test_sync_read_failure_logs_original_traceback_and_refuses_delete(monkeypatch):
    import code_puppy.tools.file_modifications as modifications
    from code_puppy.tools.io_backends import set_filesystem_backend

    class PreviewReadError(OSError):
        pass

    class Backend:
        deleted = False

        def exists(self, _path):
            return True

        def is_file(self, _path):
            return True

        def read_text_file(self, _path, line=None, limit=None):
            raise PreviewReadError("sync preview read unavailable")

        def delete_file(self, _path):
            self.deleted = True

    backend = Backend()
    captured = {}
    diagnostics = []
    monkeypatch.setattr(modifications.UndoManager, "record_change", lambda *_args: None)
    monkeypatch.setattr(
        modifications,
        "emit_error",
        lambda message, **_kwargs: diagnostics.append(str(message)),
    )
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)
    set_filesystem_backend(backend)
    try:
        result = modifications._delete_file(MagicMock(), "/virtual/unreadable")
    finally:
        set_filesystem_backend(None)

    diagnostic = "\n".join(diagnostics)
    assert captured["operation"] == "delete"
    assert "preview unavailable" in captured["preview"].lower()
    assert "PreviewReadError" in diagnostic
    assert "sync preview read unavailable" in diagnostic
    assert "read_text_file" in diagnostic
    assert "NoneType: None" not in diagnostic
    assert result.get("success") is not True
    assert result["diff"] == ""
    assert backend.deleted is False


@pytest.mark.asyncio
async def test_read_failure_requests_permission_but_refuses_to_delete(monkeypatch):
    import code_puppy.tools.file_modifications as modifications
    from code_puppy.tools.io_backends import set_filesystem_backend

    class PreviewReadError(OSError):
        pass

    class Backend:
        deleted = False

        def exists(self, _path):
            return True

        def is_file(self, _path):
            return True

        def read_text_file(self, _path, line=None, limit=None):
            raise PreviewReadError("async preview read unavailable")

        def delete_file(self, _path):
            self.deleted = True

    backend = Backend()
    captured = {}
    diagnostics = []
    monkeypatch.setattr(
        modifications,
        "emit_error",
        lambda message, **_kwargs: diagnostics.append(str(message)),
    )
    _register_real_permission_callback(monkeypatch, approved=True, captured=captured)
    set_filesystem_backend(backend)
    try:
        result = await modifications._delete_file_async(
            MagicMock(), "/virtual/unreadable"
        )
    finally:
        set_filesystem_backend(None)

    assert captured["operation"] == "delete"
    assert isinstance(captured["preview"], PlainTextDeletionPreview)
    assert "preview unavailable" in captured["preview"].lower()
    diagnostic = "\n".join(diagnostics)
    assert "PreviewReadError" in diagnostic
    assert "async preview read unavailable" in diagnostic
    assert "read_text_file" in diagnostic
    assert "NoneType: None" not in diagnostic
    assert result.get("success") is not True
    assert result["diff"] == ""
    assert backend.deleted is False


@pytest.mark.asyncio
async def test_yolo_binary_delete_result_still_reports_safe_omission(monkeypatch):
    import code_puppy.callbacks as callbacks
    import code_puppy.tools.file_modifications as modifications
    from code_puppy.tools.io_backends import set_filesystem_backend

    class Backend:
        deleted = False

        def exists(self, _path):
            return True

        def is_file(self, _path):
            return True

        def read_text_file(self, _path, line=None, limit=None):
            return "binary\x00secret"

        def delete_file(self, _path):
            self.deleted = True

    permission = importlib.import_module(
        "code_puppy_core_plugins.file_permission_handler.register_callbacks"
    )
    monkeypatch.setattr(permission, "get_yolo_mode", lambda: True)
    callbacks.clear_callbacks("file_permission")
    callbacks.register_callback(
        "file_permission", permission.handle_file_permission_async
    )
    backend = Backend()
    set_filesystem_backend(backend)
    try:
        result = await modifications._delete_file_async(
            MagicMock(), "/virtual/private.bin"
        )
    finally:
        set_filesystem_backend(None)

    assert result["success"] is True
    assert result["diff"] == ""
    assert "size unavailable" in result["message"]
    assert "secret" not in result["message"]
    assert backend.deleted is True


@pytest.mark.asyncio
async def test_async_denial_preserves_binary_file(monkeypatch, tmp_path):
    import code_puppy.tools.file_modifications as modifications

    target = tmp_path / "async-denied.bin"
    raw = b"PK\x03\x04private\x00payload"
    target.write_bytes(raw)
    captured = {}
    monkeypatch.setattr(modifications.UndoManager, "record_change", lambda *_args: None)
    _register_real_permission_callback(monkeypatch, approved=False, captured=captured)

    result = await modifications._delete_file_async(MagicMock(), str(target))

    assert result["success"] is False
    assert target.read_bytes() == raw
    assert isinstance(captured["preview"], PlainTextDeletionPreview)
    assert "private" not in captured["preview"]
    assert "diff" not in result


def test_deletion_locales_have_all_safe_omission_messages():
    from code_puppy.i18n import get_locale, ngettext, set_locale, t

    locale_dir = Path(__file__).parents[2] / "code_puppy" / "i18n" / "locales"
    keys = {
        "tools.deletion.binary_preview_omitted",
        "tools.deletion.unsafe_preview_omitted",
        "tools.deletion.omission_size_unknown",
        "tools.deletion.preview_unavailable",
        "tools.deletion.read_failed",
    }
    original_locale = get_locale()
    try:
        for locale in ("en-US", "es", "fr-CA"):
            messages = json.loads(
                (locale_dir / f"{locale}.json").read_text(encoding="utf-8")
            )
            assert keys <= messages.keys()
            set_locale(locale)
            for count in (1, 2):
                rendered = ngettext(
                    "tools.deletion.binary_preview_omitted",
                    count,
                    filename="sample.bin",
                    size=count,
                )
                assert "sample.bin" in rendered
                assert str(count) in rendered
                assert "{" not in rendered and "}" not in rendered
            assert "sample.bin" in t(
                "tools.deletion.read_failed", filename="sample.bin"
            )
    finally:
        set_locale(original_locale)
