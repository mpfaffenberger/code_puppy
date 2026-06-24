import os
import shutil
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
        if not hasattr(self, 'history'):
            self.history: List[FileChange] = []

    def record_change(self, file_path: str, action: str):
        original_content = None
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except Exception:
                pass  # Ignore binary files or unreadable files for now
        self.history.append(FileChange(file_path=file_path, original_content=original_content, action=action))

    def pop_change(self) -> Optional[FileChange]:
        if self.history:
            return self.history.pop()
        return None

    def undo_last(self) -> str:
        change = self.pop_change()
        if not change:
            return "No more actions to undo."
        
        try:
            if change.original_content is None:
                # File was created, so we delete it
                if os.path.exists(change.file_path):
                    os.remove(change.file_path)
                return f"Undid {change.action}: deleted {change.file_path}"
            else:
                # File was modified or deleted, restore original content
                with open(change.file_path, 'w', encoding='utf-8') as f:
                    f.write(change.original_content)
                return f"Undid {change.action}: restored {change.file_path}"
        except Exception as e:
            return f"Failed to undo {change.action} on {change.file_path}: {e}"
