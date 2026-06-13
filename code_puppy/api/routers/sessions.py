"""Sessions API endpoints for retrieving subagent session data."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_puppy.session_storage import load_session

_executor = ThreadPoolExecutor(max_workers=2)
FILE_IO_TIMEOUT = 10.0

router = APIRouter()


class SessionInfo(BaseModel):
    """Session metadata information."""

    session_id: str
    agent_name: Optional[str] = None
    initial_prompt: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    message_count: int = 0


class MessageContent(BaseModel):
    """Message content with role and optional timestamp."""

    role: str
    content: Any
    timestamp: Optional[str] = None


class SessionDetail(SessionInfo):
    """Session info with full message history."""

    messages: List[Dict[str, Any]] = []


def _get_sessions_dir() -> Path:
    from code_puppy.config import DATA_DIR

    return Path(DATA_DIR) / "subagent_sessions"


def _serialize_message(msg: Any) -> Dict[str, Any]:
    def _serialize_obj(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if isinstance(obj, dict):
            return {k: _serialize_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize_obj(item) for item in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: _serialize_obj(v) for k, v in obj.__dict__.items()}
        return str(obj)

    if isinstance(msg, dict) and "msg" in msg:
        actual_msg = msg["msg"]
        return {
            "msg": _serialize_obj(actual_msg),
            "agent": msg.get("agent"),
            "model": msg.get("model"),
            "ts": msg.get("ts"),
        }

    result = _serialize_obj(msg)
    if not isinstance(result, dict):
        return {"content": str(result)}
    return result


def _load_json_sync(file_path: Path) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_session_history_sync(file_path: Path) -> Any:
    return load_session(file_path.stem, file_path.parent)


@router.get("/")
async def list_sessions() -> List[SessionInfo]:
    sessions_dir = _get_sessions_dir()
    if not sessions_dir.exists():
        return []

    loop = asyncio.get_running_loop()
    sessions: list[SessionInfo] = []

    for txt_file in sessions_dir.glob("*.txt"):
        session_id = txt_file.stem
        try:
            metadata = await asyncio.wait_for(
                loop.run_in_executor(_executor, _load_json_sync, txt_file),
                timeout=FILE_IO_TIMEOUT,
            )
            sessions.append(
                SessionInfo(
                    session_id=session_id,
                    agent_name=metadata.get("agent_name"),
                    initial_prompt=metadata.get("initial_prompt"),
                    created_at=metadata.get("created_at"),
                    last_updated=metadata.get("last_updated"),
                    message_count=metadata.get("message_count", 0),
                )
            )
        except asyncio.TimeoutError:
            sessions.append(SessionInfo(session_id=session_id))
        except Exception:
            sessions.append(SessionInfo(session_id=session_id))

    return sessions


@router.get("/{session_id}")
async def get_session(session_id: str) -> SessionInfo:
    sessions_dir = _get_sessions_dir()
    txt_file = sessions_dir / f"{session_id}.txt"

    if not txt_file.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    loop = asyncio.get_running_loop()
    try:
        metadata = await asyncio.wait_for(
            loop.run_in_executor(_executor, _load_json_sync, txt_file),
            timeout=FILE_IO_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Timeout reading session '{session_id}'") from None

    return SessionInfo(
        session_id=session_id,
        agent_name=metadata.get("agent_name"),
        initial_prompt=metadata.get("initial_prompt"),
        created_at=metadata.get("created_at"),
        last_updated=metadata.get("last_updated"),
        message_count=metadata.get("message_count", 0),
    )


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    sessions_dir = _get_sessions_dir()
    session_file = sessions_dir / f"{session_id}.pkl"

    if not session_file.exists():
        raise HTTPException(404, f"Session '{session_id}' messages not found")

    loop = asyncio.get_running_loop()
    try:
        messages = await asyncio.wait_for(
            loop.run_in_executor(_executor, _load_session_history_sync, session_file),
            timeout=FILE_IO_TIMEOUT,
        )
        return [_serialize_message(msg) for msg in messages]
    except asyncio.TimeoutError:
        raise HTTPException(
            504, f"Timeout loading session '{session_id}' messages"
        ) from None
    except Exception as e:
        raise HTTPException(500, f"Error loading session messages: {e}") from e


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> Dict[str, str]:
    sessions_dir = _get_sessions_dir()
    txt_file = sessions_dir / f"{session_id}.txt"
    session_file = sessions_dir / f"{session_id}.pkl"

    if not txt_file.exists() and not session_file.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    if txt_file.exists():
        txt_file.unlink()
    if session_file.exists():
        session_file.unlink()

    return {"message": f"Session '{session_id}' deleted"}
