import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from code_puppy.plugins.background_tasks.manager import (
    BackgroundTaskKind,
    BackgroundTaskManager,
    BackgroundTaskRequest,
    BackgroundTaskState,
)


async def test_background_task_lifecycle_and_notification(tmp_path: Path):
    async def execute(record, _context):
        await asyncio.sleep(0)
        return "finished"

    manager = BackgroundTaskManager(
        metadata_path=tmp_path / "tasks.json",
        output_dir=tmp_path / "logs",
        executor=execute,
    )
    notification = AsyncMock(return_value=[])
    with (
        patch("code_puppy.callbacks.on_notification", notification),
        patch("code_puppy.messaging.emit_info"),
    ):
        record = manager.start(
            BackgroundTaskRequest(kind=BackgroundTaskKind.SHELL, command="echo hi"),
            None,
        )
        settled = await manager.wait(record.task_id)

    assert settled.state is BackgroundTaskState.SUCCEEDED
    assert settled.result == "finished"
    notification.assert_awaited_once()
    persisted = json.loads((tmp_path / "tasks.json").read_text())
    assert persisted[0]["state"] == "succeeded"


async def test_background_failure_is_recorded(tmp_path: Path):
    async def execute(_record, _context):
        raise RuntimeError("boom")

    manager = BackgroundTaskManager(
        metadata_path=tmp_path / "tasks.json",
        output_dir=tmp_path / "logs",
        executor=execute,
    )
    with (
        patch("code_puppy.callbacks.on_notification", AsyncMock(return_value=[])),
        patch("code_puppy.messaging.emit_info"),
    ):
        record = manager.start(
            BackgroundTaskRequest(kind=BackgroundTaskKind.SHELL, command="false"),
            None,
        )
        await manager.wait(record.task_id)

    assert record.state is BackgroundTaskState.FAILED
    assert record.error == "boom"


async def test_cancel_background_task(tmp_path: Path):
    started = asyncio.Event()

    async def execute(_record, _context):
        started.set()
        await asyncio.sleep(10)
        return "late"

    manager = BackgroundTaskManager(
        metadata_path=tmp_path / "tasks.json",
        output_dir=tmp_path / "logs",
        executor=execute,
    )
    with (
        patch("code_puppy.callbacks.on_notification", AsyncMock(return_value=[])),
        patch("code_puppy.messaging.emit_info"),
    ):
        record = manager.start(
            BackgroundTaskRequest(kind=BackgroundTaskKind.SHELL, command="sleep 10"),
            None,
        )
        await started.wait()
        manager.cancel(record.task_id)
        await manager.wait(record.task_id)

    assert record.state is BackgroundTaskState.CANCELLED


def test_restart_marks_owned_tasks_interrupted(tmp_path: Path):
    metadata = tmp_path / "tasks.json"
    metadata.write_text(
        '[{"task_id":"x","request":{"kind":"shell","command":"sleep 1",'
        '"metadata":{}},"state":"running","created_at":"now"}]'
    )

    manager = BackgroundTaskManager(
        metadata_path=metadata,
        output_dir=tmp_path / "logs",
    )

    assert manager.get("x").state is BackgroundTaskState.INTERRUPTED


def test_request_validation_requires_kind_specific_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BackgroundTaskRequest(kind=BackgroundTaskKind.SHELL)
    with pytest.raises(ValidationError):
        BackgroundTaskRequest(kind=BackgroundTaskKind.AGENT, agent_name="worker")
