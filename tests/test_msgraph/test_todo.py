"""Tests for Microsoft To Do tools."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.todo import (
    msgraph_list_todo_lists,
    msgraph_get_todo_list,
    msgraph_create_todo_list,
    msgraph_delete_todo_list,
    msgraph_list_todo_tasks,
    msgraph_get_todo_task,
    msgraph_create_todo_task,
    msgraph_update_todo_task,
    msgraph_complete_todo_task,
    msgraph_delete_todo_task,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_todo_lists():
    """Sample To Do lists response."""
    return {
        "value": [
            {
                "id": "list-001",
                "displayName": "My Tasks",
                "isOwner": True,
                "isShared": False,
                "wellknownListName": "defaultList",
            },
            {
                "id": "list-002",
                "displayName": "Shopping",
                "isOwner": True,
                "isShared": False,
            },
        ]
    }


@pytest.fixture
def mock_todo_tasks():
    """Sample To Do tasks response."""
    return {
        "value": [
            {
                "id": "task-001",
                "title": "Buy groceries",
                "status": "notStarted",
                "importance": "normal",
                "isReminderOn": False,
                "createdDateTime": "2025-12-15T10:00:00Z",
            },
            {
                "id": "task-002",
                "title": "Call dentist",
                "status": "inProgress",
                "importance": "high",
                "dueDateTime": {
                    "dateTime": "2025-12-20T09:00:00",
                    "timeZone": "UTC",
                },
            },
        ]
    }


class TestMSGraphTodoLists:
    """Tests for To Do list operations."""

    def test_msgraph_list_todo_lists(self, mock_context, mock_todo_lists):
        """Test listing To Do lists."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_todo_lists
            mock_get_client.return_value = mock_client

            result = msgraph_list_todo_lists(mock_context)

            assert result["success"] is True
            assert result["total_count"] == 2
            assert len(result["lists"]) == 2
            assert result["lists"][0]["display_name"] == "My Tasks"

    def test_msgraph_get_todo_list(self, mock_context):
        """Test getting a specific To Do list."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "list-001",
                "displayName": "My Tasks",
                "isOwner": True,
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_todo_list(mock_context, "list-001")

            assert result["success"] is True
            assert result["list"]["display_name"] == "My Tasks"

    def test_msgraph_create_todo_list(self, mock_context):
        """Test creating a To Do list."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {
                "id": "new-list-001",
                "displayName": "Work Tasks",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_create_todo_list(mock_context, "Work Tasks")

            assert result["success"] is True
            assert result["list"]["display_name"] == "Work Tasks"

    def test_msgraph_delete_todo_list(self, mock_context):
        """Test deleting a To Do list."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_delete_todo_list(mock_context, "list-001")

            assert result["success"] is True
            assert result["message"] == "To Do list deleted"


class TestMSGraphTodoTasks:
    """Tests for To Do task operations."""

    def test_msgraph_list_todo_tasks(self, mock_context, mock_todo_tasks):
        """Test listing tasks in a To Do list."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_todo_tasks
            mock_get_client.return_value = mock_client

            result = msgraph_list_todo_tasks(mock_context, "list-001")

            assert result["success"] is True
            assert result["total_count"] == 2
            assert result["tasks"][0]["title"] == "Buy groceries"

    def test_msgraph_get_todo_task(self, mock_context):
        """Test getting a specific task."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "task-001",
                "title": "Buy groceries",
                "status": "notStarted",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_todo_task(mock_context, "list-001", "task-001")

            assert result["success"] is True
            assert result["task"]["title"] == "Buy groceries"

    def test_msgraph_create_todo_task(self, mock_context):
        """Test creating a task."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {
                "id": "new-task-001",
                "title": "New task",
                "status": "notStarted",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_create_todo_task(
                mock_context,
                "list-001",
                "New task",
                body="Task details",
                importance="high",
            )

            assert result["success"] is True
            assert result["task"]["title"] == "New task"

    def test_msgraph_update_todo_task(self, mock_context):
        """Test updating a task."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = {
                "id": "task-001",
                "title": "Updated task",
                "status": "inProgress",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_update_todo_task(
                mock_context,
                "list-001",
                "task-001",
                title="Updated task",
                status="inProgress",
            )

            assert result["success"] is True
            assert result["task"]["title"] == "Updated task"

    def test_msgraph_complete_todo_task(self, mock_context):
        """Test completing a task."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = {
                "id": "task-001",
                "title": "Completed task",
                "status": "completed",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_complete_todo_task(mock_context, "list-001", "task-001")

            assert result["success"] is True
            assert result["task"]["status"] == "completed"

    def test_msgraph_delete_todo_task(self, mock_context):
        """Test deleting a task."""
        with patch(
            "code_puppy.tools.msgraph.todo.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_delete_todo_task(mock_context, "list-001", "task-001")

            assert result["success"] is True
            assert result["message"] == "To Do task deleted"
