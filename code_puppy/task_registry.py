"""Global task tracking for agent cancellation support."""

import asyncio
import threading
from typing import Dict, List, Optional, Set


class TaskRegistry:
    """Global registry for tracking agent tasks and their relationships."""

    def __init__(self):
        self._tasks: Dict[int, asyncio.Task] = {}
        self._parent_child: Dict[int, Set[int]] = {}
        self._child_parent: Dict[int, Optional[int]] = {}
        self._lock = threading.RLock()
        self._cancellation_in_progress = False
        self._task_creation_enabled = True

    def register_task(
        self, task: asyncio.Task, parent_task: Optional[asyncio.Task] = None
    ) -> int:
        """Register a task and optionally its parent relationship."""
        # Check if task creation is allowed (during cancellation)
        if self._cancellation_in_progress:
            task.cancel()
            raise RuntimeError("Task creation blocked during cancellation")

        task_id = id(task)

        with self._lock:
            self._tasks[task_id] = task
            self._child_parent[task_id] = id(parent_task) if parent_task else None

            if parent_task:
                parent_id = id(parent_task)
                if parent_id not in self._parent_child:
                    self._parent_child[parent_id] = set()
                self._parent_child[parent_id].add(task_id)

        return task_id

    def unregister_task(self, task: asyncio.Task) -> None:
        """Unregister a task and clean up relationships."""
        task_id = id(task)

        with self._lock:
            # Remove from tasks
            self._tasks.pop(task_id, None)

            # Remove from parent-child relationships
            parent_id = self._child_parent.pop(task_id, None)
            if parent_id and parent_id in self._parent_child:
                self._parent_child[parent_id].discard(task_id)
                if not self._parent_child[parent_id]:
                    del self._parent_child[parent_id]

            # Remove children relationships
            if task_id in self._parent_child:
                for child_id in self._parent_child[task_id]:
                    self._child_parent.pop(child_id, None)
                del self._parent_child[task_id]

    def get_task_hierarchy(self, root_task: asyncio.Task) -> List[asyncio.Task]:
        """Get all tasks in hierarchy starting from root_task."""
        root_id = id(root_task)
        hierarchy = []

        with self._lock:
            self._collect_hierarchy(root_id, hierarchy)

        return hierarchy

    def _collect_hierarchy(self, task_id: int, hierarchy: List[asyncio.Task]) -> None:
        """Recursively collect tasks in hierarchy."""
        if task_id in self._tasks:
            task = self._tasks[task_id]
            hierarchy.append(task)

            # Collect children
            if task_id in self._parent_child:
                for child_id in list(self._parent_child[task_id]):
                    self._collect_hierarchy(child_id, hierarchy)

    def start_cancellation(self) -> None:
        """Start cancellation mode - prevent new task creation."""
        with self._lock:
            self._cancellation_in_progress = True
            self._task_creation_enabled = False

    def end_cancellation(self) -> None:
        """End cancellation mode - allow normal task creation."""
        with self._lock:
            self._cancellation_in_progress = False
            self._task_creation_enabled = True

    def can_create_tasks(self) -> bool:
        """Check if task creation is currently allowed."""
        with self._lock:
            return self._task_creation_enabled

    def cancel_all_tasks(self, root_task: Optional[asyncio.Task] = None) -> int:
        """Cancel all tasks, optionally starting from a specific root."""
        cancelled_count = 0

        # Start cancellation mode to prevent new task creation
        self.start_cancellation()

        try:
            # Immediate cancellation - no delays, no multiple attempts
            with self._lock:
                if root_task:
                    tasks_to_cancel = self.get_task_hierarchy(root_task)
                else:
                    tasks_to_cancel = list(self._tasks.values())

                for task in tasks_to_cancel:
                    if not task.done():
                        task.cancel()
                        cancelled_count += 1

            # Force immediate cancellation without any delays
            return cancelled_count

        finally:
            # Always end cancellation mode, even if an error occurred
            self.end_cancellation()

        return cancelled_count

    def get_all_tasks(self) -> List[asyncio.Task]:
        """Get all registered tasks."""
        with self._lock:
            return list(self._tasks.values())

    def cleanup_completed_tasks(self) -> int:
        """Clean up completed tasks and return count of cleaned up tasks."""
        cleaned = 0

        with self._lock:
            completed_ids = []
            for task_id, task in self._tasks.items():
                if task.done():
                    completed_ids.append(task_id)

            for task_id in completed_ids:
                # Find the task object to unregister properly
                task = self._tasks.get(task_id)
                if task:
                    self.unregister_task(task)
                    cleaned += 1

        return cleaned


# Global instance
_task_registry = TaskRegistry()


def get_task_registry() -> TaskRegistry:
    """Get the global task registry instance."""
    return _task_registry


def track_agent_task(
    task: asyncio.Task, parent_task: Optional[asyncio.Task] = None
) -> int:
    """Track an agent task in the global registry."""
    return _task_registry.register_task(task, parent_task)


def untrack_agent_task(task: asyncio.Task) -> None:
    """Untrack an agent task from the global registry."""
    _task_registry.unregister_task(task)


def cancel_all_agent_tasks(root_task: Optional[asyncio.Task] = None) -> int:
    """Cancel all tracked agent tasks."""
    return _task_registry.cancel_all_tasks(root_task)


def cleanup_completed_tasks() -> int:
    """Clean up completed tasks from the registry."""
    return _task_registry.cleanup_completed_tasks()


def can_create_tasks() -> bool:
    """Check if task creation is currently allowed."""
    return _task_registry.can_create_tasks()


def start_cancellation_mode() -> None:
    """Start global cancellation mode."""
    _task_registry.start_cancellation()


def end_cancellation_mode() -> None:
    """End global cancellation mode."""
    _task_registry.end_cancellation()
