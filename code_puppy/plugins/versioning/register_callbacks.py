from __future__ import annotations

from typing import Any, Dict

from code_puppy.callbacks import register_callback
from code_puppy.version_store import record_change


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return None
    return str(value)


def _on_edit_file(result: Dict[str, Any]) -> None:
    # Expect structure from file_modifications helpers
    changed = bool(result.get("changed"))
    if not changed:
        return
    file_path = result.get("path") or result.get("file_path")
    change_type = result.get("change_type") or "modify"
    before_content = _to_str_or_none(result.get("before_content"))
    after_content = _to_str_or_none(result.get("after_content"))
    diff = _to_str_or_none(result.get("diff")) or ""
    if not file_path:
        return
    record_change(
        file_path=file_path,
        change_type=change_type,
        before_content=before_content,
        after_content=after_content,
        diff=diff,
    )


def _on_delete_file(result: Dict[str, Any]) -> None:
    # Expect structure from delete_file helper
    changed = bool(result.get("changed"))
    if not changed:
        return
    file_path = result.get("path") or result.get("file_path")
    before_content = _to_str_or_none(result.get("before_content"))
    diff = _to_str_or_none(result.get("diff")) or ""
    if not file_path:
        return
    record_change(
        file_path=file_path,
        change_type="delete",
        before_content=before_content,
        after_content=None,
        diff=diff,
    )


# Register callbacks on import
register_callback("edit_file", _on_edit_file)
register_callback("delete_file", _on_delete_file)
