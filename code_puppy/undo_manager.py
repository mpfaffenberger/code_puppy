from typing import Optional, List
from dataclasses import dataclass


@dataclass
class FileChange:
    file_path: str
    original_content: Optional[str]  # None if the file was created
    action: str  # e.g., 'replace_in_file', 'create_file', 'delete_file'


class UndoManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UndoManager, cls).__new__(cls)
            cls._instance.history = []
        return cls._instance

    def __init__(self):
        if not hasattr(self, "history"):
            self.history: List[FileChange] = []

    def capture_change(self, file_path: str, action: str) -> FileChange:
        """Snapshot pre-mutation state WITHOUT touching undo history.

        Callers must pass the result to ``commit_change`` only after their
        filesystem mutation actually succeeds. This keeps a failed mutation
        from ever entering history, and avoids needing an LIFO ``pop_change``
        rollback (which can drop a different, concurrently-succeeded edit).
        """
        # Route via the fs facade + resolve_path so undo matches whatever
        # filesystem the tools wrote to (local disk or an installed backend).
        from code_puppy.tools import fs_access
        from code_puppy.tools.common import resolve_path

        file_path = resolve_path(file_path)
        original_content = None
        if fs_access.exists(file_path):
            try:
                original_content = fs_access.read_text(file_path)
            except Exception:
                pass  # Ignore binary files or unreadable files for now
        return FileChange(
            file_path=file_path, original_content=original_content, action=action
        )

    def commit_change(self, change: FileChange) -> None:
        """Publish a snapshot from ``capture_change`` after a successful mutation."""
        self.history.append(change)

    def record_change(self, file_path: str, action: str) -> None:
        """Immediate capture+commit. Kept for callers with no failure path to
        guard against; new mutation code should prefer capture_change/
        commit_change so a failed write can never poison undo history.
        """
        self.commit_change(self.capture_change(file_path, action))

    def pop_change(self) -> Optional[FileChange]:
        if self.history:
            return self.history.pop()
        return None

    def undo_last(self) -> str:
        change = self.pop_change()
        if not change:
            return "No more actions to undo."

        try:
            from code_puppy.tools import fs_access

            if change.original_content is None:
                # File was created, so we delete it
                if fs_access.exists(change.file_path):
                    fs_access.delete_file(change.file_path)
                return f"Undid {change.action}: deleted {change.file_path}"
            else:
                # File was modified or deleted, restore original content
                fs_access.write_text(change.file_path, change.original_content)
                return f"Undid {change.action}: restored {change.file_path}"
        except Exception as e:
            return f"Failed to undo {change.action} on {change.file_path}: {e}"
