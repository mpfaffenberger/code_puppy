"""SQLite persistence layer for the Code Puppy WS API.

Stores session history in ~/.puppy_desk/chat_messages.db — the same
database that the Desk Puppy Electron FE reads from.

All database operations are async coroutines backed by aiosqlite.
"""

from code_puppy.api.db.connection import close_db, get_db, init_db
from code_puppy.api.db.queries import (
    get_active_messages,
    get_next_seq,
    get_session_metadata,
    get_session_row,
    insert_compaction_log,
    insert_message,
    insert_tool_call,
    mark_messages_compacted,
    session_exists,
    soft_delete_session,
    update_session_stats,
    update_session_working_directory,
    upsert_session,
    write_system_message_to_sqlite,
    write_turn_to_sqlite,
)

__all__ = [
    "init_db",
    "close_db",
    "get_db",
    "get_session_row",
    "get_session_metadata",
    "session_exists",
    "upsert_session",
    "soft_delete_session",
    "update_session_stats",
    "update_session_working_directory",
    "write_system_message_to_sqlite",
    "get_next_seq",
    "insert_message",
    "insert_tool_call",
    "get_active_messages",
    "mark_messages_compacted",
    "insert_compaction_log",
    "write_turn_to_sqlite",
]
