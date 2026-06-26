from pydantic_ai import RunContext

from .manager import AgentTaskBatch, AgentTaskRequest, get_task_manager


def _register_submit(agent):
    @agent.tool
    async def submit_agent_tasks(
        context: RunContext,
        tasks: list[AgentTaskRequest],
        max_parallel: int = 4,
        wait: bool = True,
    ) -> AgentTaskBatch:
        """Submit typed subagent tasks with bounded parallelism."""
        manager = get_task_manager()
        records = manager.submit_batch(tasks, context, max_parallel=max_parallel)
        if wait:
            return await manager.wait([record.task_id for record in records])
        return AgentTaskBatch.from_records(records)


def _register_list(agent):
    @agent.tool
    def list_agent_tasks(context: RunContext) -> AgentTaskBatch:
        """List subagent task state and structured results."""
        return AgentTaskBatch.from_records(get_task_manager().list())


def _register_wait(agent):
    @agent.tool
    async def wait_agent_tasks(
        context: RunContext, task_ids: list[str], timeout_seconds: float | None = None
    ) -> AgentTaskBatch:
        """Wait for selected subagent tasks, optionally with a timeout."""
        return await get_task_manager().wait(task_ids, timeout_seconds)


def _register_cancel(agent):
    @agent.tool
    def cancel_agent_tasks(context: RunContext, task_ids: list[str]) -> AgentTaskBatch:
        """Cancel queued or running subagent tasks."""
        return get_task_manager().cancel(task_ids)


TOOL_DEFINITIONS = [
    {"name": "submit_agent_tasks", "register_func": _register_submit},
    {"name": "list_agent_tasks", "register_func": _register_list},
    {"name": "wait_agent_tasks", "register_func": _register_wait},
    {"name": "cancel_agent_tasks", "register_func": _register_cancel},
]
