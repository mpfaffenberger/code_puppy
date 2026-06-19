import asyncio
from pathlib import Path

from code_puppy.plugins.subagent_tasks.manager import (
    AgentTaskManager,
    AgentTaskRequest,
    TaskState,
)
from code_puppy.tools.agent_tools import AgentInvokeOutput


async def test_batch_enforces_parallelism_and_aggregates(tmp_path: Path):
    active = 0
    peak = 0

    async def invoke(_ctx, name, prompt, session_id, model_name):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return AgentInvokeOutput(response=prompt, agent_name=name)

    manager = AgentTaskManager(state_path=tmp_path / "tasks.json", invoke=invoke)
    records = manager.submit_batch(
        [AgentTaskRequest(agent_name="worker", prompt=str(i)) for i in range(6)],
        context=None,
        max_parallel=2,
    )

    batch = await manager.wait([record.task_id for record in records])

    assert peak == 2
    assert batch.succeeded == 6
    assert all(record.state is TaskState.SUCCEEDED for record in batch.tasks)


async def test_agent_error_is_structured_failure(tmp_path: Path):
    async def invoke(_ctx, name, prompt, session_id, model_name):
        return AgentInvokeOutput(
            response=None, agent_name=name, error="provider failed"
        )

    manager = AgentTaskManager(state_path=tmp_path / "tasks.json", invoke=invoke)
    record = manager.submit(AgentTaskRequest(agent_name="worker", prompt="x"), None)

    batch = await manager.wait([record.task_id])

    assert batch.failed == 1
    assert batch.tasks[0].error == "provider failed"


async def test_cancel_running_task(tmp_path: Path):
    started = asyncio.Event()

    async def invoke(_ctx, name, prompt, session_id, model_name):
        started.set()
        await asyncio.sleep(10)
        return AgentInvokeOutput(response="late", agent_name=name)

    manager = AgentTaskManager(state_path=tmp_path / "tasks.json", invoke=invoke)
    record = manager.submit(AgentTaskRequest(agent_name="worker", prompt="x"), None)
    await started.wait()
    manager.cancel([record.task_id])
    await manager.wait([record.task_id])

    assert record.state is TaskState.CANCELLED


def test_restart_marks_inflight_tasks_failed(tmp_path: Path):
    path = tmp_path / "tasks.json"
    path.write_text(
        '[{"task_id":"one","request":{"agent_name":"a","prompt":"p",'
        '"metadata":{}},"state":"running","created_at":"now"}]'
    )

    manager = AgentTaskManager(state_path=path)

    assert manager.get("one").state is TaskState.FAILED
    assert "restart" in manager.get("one").error
