from pydantic import BaseModel
from pydantic_ai import RunContext

from .manager import (
    BackgroundTaskRecord,
    BackgroundTaskRequest,
    BackgroundTaskKind,
    get_background_manager,
)


class BackgroundTaskList(BaseModel):
    tasks: list[BackgroundTaskRecord]


def _register_start(agent):
    @agent.tool
    async def start_background_task(
        context: RunContext, request: BackgroundTaskRequest
    ) -> BackgroundTaskRecord:
        """Start a managed shell or subagent task and return immediately."""
        if request.kind is BackgroundTaskKind.SHELL:
            from code_puppy.callbacks import on_run_shell_command
            from code_puppy.permissions import authorize_shell_command

            callback_results = await on_run_shell_command(
                context,
                request.command or "",
                request.cwd,
                request.timeout_seconds or 60,
            )
            requires_approval = False
            sandbox_fallback = False
            for result in callback_results:
                if not isinstance(result, dict):
                    continue
                if result.get("blocked"):
                    raise PermissionError(
                        result.get(
                            "error_message", "Background command blocked by policy"
                        )
                    )
                requires_approval = requires_approval or bool(
                    result.get("requires_approval")
                )
                sandbox_fallback = sandbox_fallback or bool(
                    result.get("sandbox_fallback")
                )
            approved, _ = await authorize_shell_command(
                request.command or "",
                request.cwd,
                force_prompt=requires_approval,
            )
            if not approved:
                raise PermissionError("Background command denied by permission policy")
            request.metadata["_sandbox_fallback_approved"] = sandbox_fallback
        return get_background_manager().start(request, context)


def _register_list(agent):
    @agent.tool
    def list_background_tasks(context: RunContext) -> BackgroundTaskList:
        """List managed background tasks and their lifecycle state."""
        return BackgroundTaskList(tasks=get_background_manager().list())


def _register_wait(agent):
    @agent.tool
    async def wait_background_task(
        context: RunContext, task_id: str, timeout_seconds: float | None = None
    ) -> BackgroundTaskRecord:
        """Wait for a background task to settle, optionally with a timeout."""
        return await get_background_manager().wait(task_id, timeout_seconds)


def _register_output(agent):
    @agent.tool
    def read_background_task_output(
        context: RunContext, task_id: str, max_chars: int = 20_000
    ) -> str:
        """Read the tail of a background task's durable output log."""
        return get_background_manager().read_output(task_id, max_chars)


def _register_cancel(agent):
    @agent.tool
    def cancel_background_task(
        context: RunContext, task_id: str
    ) -> BackgroundTaskRecord:
        """Cancel a queued or running background task."""
        return get_background_manager().cancel(task_id)


TOOL_DEFINITIONS = [
    {"name": "start_background_task", "register_func": _register_start},
    {"name": "list_background_tasks", "register_func": _register_list},
    {"name": "wait_background_task", "register_func": _register_wait},
    {"name": "read_background_task_output", "register_func": _register_output},
    {"name": "cancel_background_task", "register_func": _register_cancel},
]
