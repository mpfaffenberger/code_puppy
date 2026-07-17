"""Persistent background task lifecycle and local execution backend."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, model_validator


class BackgroundTaskKind(str, Enum):
    SHELL = "shell"
    AGENT = "agent"


class BackgroundTaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class BackgroundTaskRequest(BaseModel):
    kind: BackgroundTaskKind
    command: str | None = None
    cwd: str | None = None
    timeout_seconds: float | None = None
    agent_name: str | None = None
    prompt: str | None = None
    session_id: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_kind_fields(self):
        if self.kind is BackgroundTaskKind.SHELL and not self.command:
            raise ValueError("shell background tasks require command")
        if self.kind is BackgroundTaskKind.AGENT and (
            not self.agent_name or not self.prompt
        ):
            raise ValueError("agent background tasks require agent_name and prompt")
        return self


class BackgroundTaskRecord(BaseModel):
    task_id: str
    request: BackgroundTaskRequest
    state: BackgroundTaskState
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    output_path: str | None = None
    result: str | None = None
    error: str | None = None
    pid: int | None = None


Executor = Callable[[BackgroundTaskRecord, Any], Awaitable[str]]


def state_path() -> Path:
    from code_puppy.config import STATE_DIR

    return Path(STATE_DIR) / "background_tasks.json"


def logs_dir() -> Path:
    from code_puppy.config import STATE_DIR

    return Path(STATE_DIR) / "background_task_logs"


class BackgroundTaskManager:
    def __init__(
        self,
        *,
        metadata_path: Path | None = None,
        output_dir: Path | None = None,
        executor: Executor | None = None,
    ):
        self.metadata_path = metadata_path or state_path()
        self.output_dir = output_dir or logs_dir()
        self.executor = executor or self._execute
        self.records: dict[str, BackgroundTaskRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._load()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self) -> None:
        try:
            raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        changed = False
        for item in raw if isinstance(raw, list) else ():
            try:
                record = BackgroundTaskRecord.model_validate(item)
            except Exception:
                continue
            if record.state in {
                BackgroundTaskState.QUEUED,
                BackgroundTaskState.RUNNING,
            }:
                record.state = BackgroundTaskState.INTERRUPTED
                record.completed_at = self._now()
                record.error = "Task ownership lost during process restart"
                changed = True
            self.records[record.task_id] = record
        if changed:
            self._persist()

    def _persist(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.metadata_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                [record.model_dump(mode="json") for record in self.records.values()],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temp.replace(self.metadata_path)

    def start(
        self, request: BackgroundTaskRequest, context: Any
    ) -> BackgroundTaskRecord:
        task_id = uuid.uuid4().hex
        self.output_dir.mkdir(parents=True, exist_ok=True)
        record = BackgroundTaskRecord(
            task_id=task_id,
            request=request,
            state=BackgroundTaskState.QUEUED,
            created_at=self._now(),
            output_path=str(self.output_dir / f"{task_id}.log"),
        )
        self.records[task_id] = record
        self._persist()
        self._tasks[task_id] = asyncio.create_task(self._run(record, context))
        return record

    async def _run(self, record: BackgroundTaskRecord, context: Any) -> None:
        record.state = BackgroundTaskState.RUNNING
        record.started_at = self._now()
        self._persist()
        try:
            record.result = await self.executor(record, context)
            record.state = BackgroundTaskState.SUCCEEDED
        except asyncio.CancelledError:
            process = self._processes.get(record.task_id)
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    process.kill()
            record.state = BackgroundTaskState.CANCELLED
            raise
        except Exception as exc:
            record.state = BackgroundTaskState.FAILED
            record.error = str(exc)
        finally:
            record.completed_at = self._now()
            self._tasks.pop(record.task_id, None)
            self._processes.pop(record.task_id, None)
            self._persist()
            await self._notify(record)

    async def _execute(self, record: BackgroundTaskRecord, context: Any) -> str:
        request = record.request
        if request.kind is BackgroundTaskKind.AGENT:
            from code_puppy.tools.subagent_invocation import _invoke_agent_impl

            result = await _invoke_agent_impl(
                context=context,
                agent_name=request.agent_name or "",
                prompt=request.prompt or "",
                session_id=request.session_id,
                model_name=request.model_name,
            )
            if result.error:
                raise RuntimeError(result.error)
            output = result.response or ""
            Path(record.output_path or "").write_text(output, encoding="utf-8")
            return output

        from code_puppy.sandbox import prepare_shell_command

        prepared = prepare_shell_command(
            request.command or "",
            request.cwd,
            allow_unsandboxed_fallback=bool(
                request.metadata.get("_sandbox_fallback_approved", False)
            ),
        )
        process = await asyncio.create_subprocess_exec(
            *prepared.argv,
            cwd=prepared.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        record.pid = process.pid
        self._processes[record.task_id] = process
        self._persist()
        communicate = process.communicate()
        if request.timeout_seconds:
            try:
                stdout, _ = await asyncio.wait_for(
                    communicate, timeout=request.timeout_seconds
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise TimeoutError(
                    f"Background command timed out after {request.timeout_seconds}s"
                ) from None
        else:
            stdout, _ = await communicate
        text = stdout.decode(errors="replace") if stdout else ""
        Path(record.output_path or "").write_text(text, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"Command exited with status {process.returncode}")
        return text[-20_000:]

    async def _notify(self, record: BackgroundTaskRecord) -> None:
        from code_puppy.callbacks import on_notification
        from code_puppy.messaging import emit_info

        message = f"Background task {record.task_id[:8]} {record.state.value}"
        emit_info(message)
        await on_notification(
            message,
            "error" if record.state is BackgroundTaskState.FAILED else "info",
            {"task_id": record.task_id, "kind": record.request.kind.value},
        )

    def get(self, task_id: str) -> BackgroundTaskRecord:
        if task_id not in self.records:
            raise KeyError(f"Unknown background task: {task_id}")
        return self.records[task_id]

    def list(self) -> list[BackgroundTaskRecord]:
        return list(self.records.values())

    def read_output(self, task_id: str, max_chars: int = 20_000) -> str:
        record = self.get(task_id)
        if not record.output_path:
            return ""
        try:
            return Path(record.output_path).read_text(encoding="utf-8")[-max_chars:]
        except OSError:
            return ""

    async def wait(
        self, task_id: str, timeout: float | None = None
    ) -> BackgroundTaskRecord:
        task = self._tasks.get(task_id)
        if task is not None:
            waiter = asyncio.shield(task)
            try:
                if timeout is None:
                    await waiter
                else:
                    await asyncio.wait_for(waiter, timeout)
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
        return self.get(task_id)

    def cancel(self, task_id: str) -> BackgroundTaskRecord:
        record = self.get(task_id)
        task = self._tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()
        return record

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


_manager: BackgroundTaskManager | None = None


def get_background_manager() -> BackgroundTaskManager:
    global _manager
    if _manager is None:
        _manager = BackgroundTaskManager()
    return _manager
