"""Typed subagent task queue with bounded concurrency and persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from code_puppy.tools.agent_tools import AgentInvokeOutput


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTaskRequest(BaseModel):
    agent_name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    session_id: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTaskRecord(BaseModel):
    task_id: str
    request: AgentTaskRequest
    state: TaskState = TaskState.QUEUED
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: AgentInvokeOutput | None = None
    error: str | None = None


class AgentTaskBatch(BaseModel):
    tasks: list[AgentTaskRecord]
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0

    @classmethod
    def from_records(cls, records: list[AgentTaskRecord]) -> "AgentTaskBatch":
        return cls(
            tasks=records,
            succeeded=sum(record.state is TaskState.SUCCEEDED for record in records),
            failed=sum(record.state is TaskState.FAILED for record in records),
            cancelled=sum(record.state is TaskState.CANCELLED for record in records),
        )


InvokeFunction = Callable[
    [Any, str, str, str | None, str | None], Awaitable[AgentInvokeOutput]
]


def default_state_path() -> Path:
    from code_puppy.config import STATE_DIR

    return Path(STATE_DIR) / "subagent_tasks.json"


class AgentTaskManager:
    def __init__(
        self,
        *,
        state_path: Path | None = None,
        invoke: InvokeFunction | None = None,
    ):
        self.state_path = state_path or default_state_path()
        self.invoke = invoke or self._default_invoke
        self.records: dict[str, AgentTaskRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._load()

    @staticmethod
    async def _default_invoke(
        context: Any,
        agent_name: str,
        prompt: str,
        session_id: str | None,
        model_name: str | None,
    ) -> AgentInvokeOutput:
        from code_puppy.tools.subagent_invocation import _invoke_agent_impl

        return await _invoke_agent_impl(
            context=context,
            agent_name=agent_name,
            prompt=prompt,
            session_id=session_id,
            model_name=model_name,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        for item in raw if isinstance(raw, list) else ():
            try:
                record = AgentTaskRecord.model_validate(item)
            except Exception:
                continue
            if record.state in {TaskState.QUEUED, TaskState.RUNNING}:
                record.state = TaskState.FAILED
                record.error = "Task interrupted by process restart"
                record.completed_at = self._now()
            self.records[record.task_id] = record

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                [record.model_dump(mode="json") for record in self.records.values()],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temp.replace(self.state_path)

    def submit(
        self,
        request: AgentTaskRequest,
        context: Any,
        *,
        gate: asyncio.Semaphore | None = None,
    ) -> AgentTaskRecord:
        task_id = uuid.uuid4().hex
        record = AgentTaskRecord(
            task_id=task_id,
            request=request,
            created_at=self._now(),
        )
        self.records[task_id] = record
        self._persist()
        self._tasks[task_id] = asyncio.create_task(self._run(record, context, gate))
        return record

    async def _run(
        self,
        record: AgentTaskRecord,
        context: Any,
        gate: asyncio.Semaphore | None,
    ) -> None:
        try:
            if gate is None:
                await self._invoke_record(record, context)
            else:
                async with gate:
                    await self._invoke_record(record, context)
        except asyncio.CancelledError:
            record.state = TaskState.CANCELLED
            record.completed_at = self._now()
            self._persist()
            raise
        except Exception as exc:
            record.state = TaskState.FAILED
            record.error = str(exc)
            record.completed_at = self._now()
            self._persist()
        finally:
            self._tasks.pop(record.task_id, None)

    async def _invoke_record(self, record: AgentTaskRecord, context: Any) -> None:
        record.state = TaskState.RUNNING
        record.started_at = self._now()
        self._persist()
        request = record.request
        result = await self.invoke(
            context,
            request.agent_name,
            request.prompt,
            request.session_id,
            request.model_name,
        )
        record.result = result
        record.completed_at = self._now()
        if result.error:
            record.state = TaskState.FAILED
            record.error = result.error
        else:
            record.state = TaskState.SUCCEEDED
        self._persist()

    def submit_batch(
        self,
        requests: list[AgentTaskRequest],
        context: Any,
        *,
        max_parallel: int = 4,
    ) -> list[AgentTaskRecord]:
        gate = asyncio.Semaphore(max(1, min(max_parallel, 32)))
        return [self.submit(request, context, gate=gate) for request in requests]

    def get(self, task_id: str) -> AgentTaskRecord:
        if task_id not in self.records:
            raise KeyError(f"Unknown agent task: {task_id}")
        return self.records[task_id]

    def list(self, states: set[TaskState] | None = None) -> list[AgentTaskRecord]:
        records = list(self.records.values())
        if states:
            records = [record for record in records if record.state in states]
        return records

    async def wait(
        self,
        task_ids: list[str],
        timeout: float | None = None,
    ) -> AgentTaskBatch:
        tasks = [self._tasks[task_id] for task_id in task_ids if task_id in self._tasks]
        if tasks:
            done = asyncio.gather(*tasks, return_exceptions=True)
            if timeout is None:
                await done
            else:
                try:
                    await asyncio.wait_for(asyncio.shield(done), timeout=timeout)
                except TimeoutError:
                    pass
        return AgentTaskBatch.from_records([self.get(task_id) for task_id in task_ids])

    def cancel(self, task_ids: list[str]) -> AgentTaskBatch:
        records: list[AgentTaskRecord] = []
        for task_id in task_ids:
            record = self.get(task_id)
            task = self._tasks.get(task_id)
            if task is not None and not task.done():
                task.cancel()
            records.append(record)
        return AgentTaskBatch.from_records(records)


_manager: AgentTaskManager | None = None


def get_task_manager() -> AgentTaskManager:
    global _manager
    if _manager is None:
        _manager = AgentTaskManager()
    return _manager
