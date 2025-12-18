"""Unit tests for MS Graph Planner module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.planner import (
    msgraph_list_plans,
    msgraph_get_plan,
    msgraph_list_buckets,
    msgraph_list_tasks,
    msgraph_get_task,
    msgraph_create_task,
    msgraph_update_task,
    msgraph_delete_task,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphThrottledError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_plans_data():
    """Create mock plans list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "plan-123-abc",
                "title": "Sprint 42",
                "owner": "group-456-def",
                "createdBy": {
                    "user": {
                        "id": "user-789-ghi",
                    },
                },
                "createdDateTime": "2025-01-10T09:00:00Z",
            },
            {
                "id": "plan-456-def",
                "title": "Q1 Roadmap",
                "owner": "group-789-ghi",
                "createdBy": {
                    "user": {
                        "id": "user-abc-123",
                    },
                },
                "createdDateTime": "2025-01-05T10:00:00Z",
            },
        ]
    }


@pytest.fixture
def mock_plan_data():
    """Create mock single plan data from MS Graph API."""
    return {
        "id": "plan-123-abc",
        "title": "Sprint 42",
        "owner": "group-456-def",
        "createdBy": {
            "user": {
                "id": "user-789-ghi",
            },
        },
        "createdDateTime": "2025-01-10T09:00:00Z",
    }


@pytest.fixture
def mock_buckets_data():
    """Create mock buckets list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "bucket-todo-123",
                "name": "To Do",
                "orderHint": "8586471076435036547",
                "planId": "plan-123-abc",
            },
            {
                "id": "bucket-inprogress-456",
                "name": "In Progress",
                "orderHint": "8586471076435036546",
                "planId": "plan-123-abc",
            },
            {
                "id": "bucket-done-789",
                "name": "Done",
                "orderHint": "8586471076435036545",
                "planId": "plan-123-abc",
            },
        ]
    }


@pytest.fixture
def mock_tasks_data():
    """Create mock tasks list data from MS Graph API."""
    return {
        "value": [
            {
                "id": "task-001",
                "title": "Implement login feature",
                "bucketId": "bucket-inprogress-456",
                "planId": "plan-123-abc",
                "percentComplete": 50,
                "priority": 3,
                "dueDateTime": "2025-01-20T17:00:00Z",
                "assignments": {
                    "user-alice-123": {
                        "@odata.type": "#microsoft.graph.plannerAssignment",
                        "assignedBy": {
                            "user": {"id": "user-manager-001"},
                        },
                        "assignedDateTime": "2025-01-15T10:00:00Z",
                        "orderHint": " !",
                    },
                },
            },
            {
                "id": "task-002",
                "title": "Write unit tests",
                "bucketId": "bucket-todo-123",
                "planId": "plan-123-abc",
                "percentComplete": 0,
                "priority": 5,
                "dueDateTime": None,
                "assignments": {},
            },
            {
                "id": "task-003",
                "title": "Code review",
                "bucketId": "bucket-inprogress-456",
                "planId": "plan-123-abc",
                "percentComplete": 25,
                "priority": 1,
                "dueDateTime": "2025-01-18T12:00:00Z",
                "assignments": {
                    "user-bob-456": {
                        "@odata.type": "#microsoft.graph.plannerAssignment",
                        "assignedBy": {
                            "user": {"id": "user-manager-001"},
                        },
                        "assignedDateTime": "2025-01-14T14:00:00Z",
                        "orderHint": " !",
                    },
                },
            },
        ]
    }


@pytest.fixture
def mock_task_full_data():
    """Create mock full task data from MS Graph API."""
    return {
        "id": "task-001",
        "title": "Implement login feature",
        "bucketId": "bucket-inprogress-456",
        "planId": "plan-123-abc",
        "percentComplete": 50,
        "priority": 3,
        "dueDateTime": "2025-01-20T17:00:00Z",
        "startDateTime": "2025-01-15T09:00:00Z",
        "createdDateTime": "2025-01-14T10:00:00Z",
        "completedDateTime": None,
        "hasDescription": True,
        "checklistItemCount": 5,
        "activeChecklistItemCount": 3,
        "assignments": {
            "user-alice-123": {
                "@odata.type": "#microsoft.graph.plannerAssignment",
                "assignedBy": {
                    "user": {"id": "user-manager-001"},
                },
                "assignedDateTime": "2025-01-15T10:00:00Z",
                "orderHint": " !",
            },
        },
        "@odata.etag": 'W/"JzEtVGFzayAgQEBAQEBAQEBAQEBAQEBARCc="',
    }


@pytest.fixture
def mock_created_task_data():
    """Create mock created task response from MS Graph API."""
    return {
        "id": "task-new-001",
        "title": "New Feature Task",
        "bucketId": "bucket-todo-123",
        "planId": "plan-123-abc",
        "percentComplete": 0,
        "priority": 5,
        "dueDateTime": None,
        "startDateTime": None,
        "createdDateTime": "2025-01-16T11:00:00Z",
        "completedDateTime": None,
        "hasDescription": False,
        "checklistItemCount": 0,
        "activeChecklistItemCount": 0,
        "assignments": {},
        "@odata.etag": 'W/"JzEtVGFzayAgQEBAQEBAQEBAQEBAQEBBRCc="',
    }


class TestMSGraphListPlans:
    """Test suite for msgraph_list_plans tool."""

    def test_msgraph_list_plans(self, mock_context, mock_plans_data):
        """Test listing user's plans successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_plans_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_plans(mock_context)

            assert result["success"] is True
            assert "plans" in result
            assert result["total_count"] == 2
            assert len(result["plans"]) == 2

            # Check first plan
            plan1 = result["plans"][0]
            assert plan1["id"] == "plan-123-abc"
            assert plan1["title"] == "Sprint 42"
            assert plan1["owner"] == "group-456-def"
            assert plan1["created_by"] == "user-789-ghi"
            assert plan1["created_datetime"] == "2025-01-10T09:00:00Z"

            # Verify API call - user's plans endpoint
            mock_client.get.assert_called_once_with("/me/planner/plans")

    def test_msgraph_list_plans_by_group(self, mock_context, mock_plans_data):
        """Test listing plans for a specific group."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_plans_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_plans(mock_context, group_id="group-456-def")

            assert result["success"] is True
            assert result["total_count"] == 2

            # Verify API call - group's plans endpoint
            mock_client.get.assert_called_once_with(
                "/groups/group-456-def/planner/plans"
            )

    def test_msgraph_list_plans_empty(self, mock_context):
        """Test listing plans when user has no plans."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_plans(mock_context)

            assert result["success"] is True
            assert result["plans"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_plans_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_list_plans(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]

    def test_msgraph_list_plans_throttled_error(self, mock_context):
        """Test handling of throttling error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphThrottledError("Too many requests")
            mock_get_client.return_value = mock_client

            result = msgraph_list_plans(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "throttled"


class TestMSGraphGetPlan:
    """Test suite for msgraph_get_plan tool."""

    def test_msgraph_get_plan(self, mock_context, mock_plan_data):
        """Test getting plan details successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_plan_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_plan(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert "plan" in result

            plan = result["plan"]
            assert plan["id"] == "plan-123-abc"
            assert plan["title"] == "Sprint 42"
            assert plan["owner"] == "group-456-def"
            assert plan["created_by"] == "user-789-ghi"

            # Verify API call
            mock_client.get.assert_called_once_with("/planner/plans/plan-123-abc")

    def test_msgraph_get_plan_not_found(self, mock_context):
        """Test handling of plan not found error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Plan not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_plan(mock_context, "nonexistent-plan-id")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "not_found"
            assert "not found" in result["error"].lower()

    def test_msgraph_get_plan_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_plan(mock_context, "plan-123-abc")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphListBuckets:
    """Test suite for msgraph_list_buckets tool."""

    def test_msgraph_list_buckets(self, mock_context, mock_buckets_data):
        """Test listing buckets successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_buckets_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_buckets(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert "buckets" in result
            assert result["total_count"] == 3
            assert result["plan_id"] == "plan-123-abc"
            assert len(result["buckets"]) == 3

            # Check first bucket
            bucket1 = result["buckets"][0]
            assert bucket1["id"] == "bucket-todo-123"
            assert bucket1["name"] == "To Do"
            assert bucket1["order_hint"] == "8586471076435036547"
            assert bucket1["plan_id"] == "plan-123-abc"

            # Verify API call
            mock_client.get.assert_called_once_with(
                "/planner/plans/plan-123-abc/buckets"
            )

    def test_msgraph_list_buckets_empty(self, mock_context):
        """Test listing buckets when plan has no buckets."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_buckets(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert result["buckets"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_buckets_plan_not_found(self, mock_context):
        """Test handling when plan doesn't exist."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Plan not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_buckets(mock_context, "nonexistent-plan")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphListTasks:
    """Test suite for msgraph_list_tasks tool."""

    def test_msgraph_list_tasks(self, mock_context, mock_tasks_data):
        """Test listing tasks successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_tasks_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert "tasks" in result
            assert result["total_count"] == 3
            assert result["plan_id"] == "plan-123-abc"
            assert result["bucket_id"] is None
            assert len(result["tasks"]) == 3

            # Check first task
            task1 = result["tasks"][0]
            assert task1["id"] == "task-001"
            assert task1["title"] == "Implement login feature"
            assert task1["bucket_id"] == "bucket-inprogress-456"
            assert task1["percent_complete"] == 50
            assert task1["priority"] == 3
            assert task1["priority_label"] == "important"
            assert task1["due_date"] == "2025-01-20T17:00:00Z"
            assert "user-alice-123" in task1["assigned_to"]

            # Verify API call with default limit
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/planner/plans/plan-123-abc/tasks" in call_args[0][0]
            assert call_args[1]["params"]["$top"] == 50

    def test_msgraph_list_tasks_by_bucket(self, mock_context, mock_tasks_data):
        """Test listing tasks filtered by bucket."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_tasks_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(
                mock_context, "plan-123-abc", bucket_id="bucket-inprogress-456"
            )

            assert result["success"] is True
            assert result["bucket_id"] == "bucket-inprogress-456"
            # Should only return tasks in the specified bucket
            assert result["total_count"] == 2  # task-001 and task-003
            for task in result["tasks"]:
                assert task["bucket_id"] == "bucket-inprogress-456"

    def test_msgraph_list_tasks_with_limit(self, mock_context, mock_tasks_data):
        """Test listing tasks with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_tasks_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(mock_context, "plan-123-abc", limit=100)

            assert result["success"] is True

            # Verify custom limit in API call
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 100

    def test_msgraph_list_tasks_empty(self, mock_context):
        """Test listing tasks when plan has no tasks."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert result["tasks"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_tasks_plan_not_found(self, mock_context):
        """Test handling when plan doesn't exist."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Plan not found")
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(mock_context, "nonexistent-plan")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_list_tasks_priority_mapping(self, mock_context):
        """Test priority values are correctly mapped to labels."""
        tasks_with_priorities = {
            "value": [
                {
                    "id": "t1",
                    "title": "Urgent",
                    "priority": 1,
                    "bucketId": "b1",
                    "assignments": {},
                },
                {
                    "id": "t2",
                    "title": "Important",
                    "priority": 3,
                    "bucketId": "b1",
                    "assignments": {},
                },
                {
                    "id": "t3",
                    "title": "Medium",
                    "priority": 5,
                    "bucketId": "b1",
                    "assignments": {},
                },
                {
                    "id": "t4",
                    "title": "Low",
                    "priority": 9,
                    "bucketId": "b1",
                    "assignments": {},
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = tasks_with_priorities
            mock_get_client.return_value = mock_client

            result = msgraph_list_tasks(mock_context, "plan-123-abc")

            assert result["success"] is True
            assert result["tasks"][0]["priority_label"] == "urgent"
            assert result["tasks"][1]["priority_label"] == "important"
            assert result["tasks"][2]["priority_label"] == "medium"
            assert result["tasks"][3]["priority_label"] == "low"


class TestMSGraphGetTask:
    """Test suite for msgraph_get_task tool."""

    def test_msgraph_get_task(self, mock_context, mock_task_full_data):
        """Test getting task details successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_task_full_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_task(mock_context, "task-001")

            assert result["success"] is True
            assert "task" in result

            task = result["task"]
            assert task["id"] == "task-001"
            assert task["title"] == "Implement login feature"
            assert task["bucket_id"] == "bucket-inprogress-456"
            assert task["plan_id"] == "plan-123-abc"
            assert task["percent_complete"] == 50
            assert task["priority"] == 3
            assert task["priority_label"] == "important"
            assert task["due_date"] == "2025-01-20T17:00:00Z"
            assert task["start_date"] == "2025-01-15T09:00:00Z"
            assert task["has_description"] is True
            assert task["checklist_item_count"] == 5
            assert task["active_checklist_item_count"] == 3
            assert "user-alice-123" in task["assigned_to"]
            assert task["etag"] == 'W/"JzEtVGFzayAgQEBAQEBAQEBAQEBAQEBARCc="'

            # Verify API call
            mock_client.get.assert_called_once_with("/planner/tasks/task-001")

    def test_msgraph_get_task_not_found(self, mock_context):
        """Test handling of task not found error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Task not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_task(mock_context, "nonexistent-task")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_get_task_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_task(mock_context, "task-001")

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphCreateTask:
    """Test suite for msgraph_create_task tool."""

    def test_msgraph_create_task(self, mock_context, mock_created_task_data):
        """Test creating a basic task successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_created_task_data
            mock_get_client.return_value = mock_client

            result = msgraph_create_task(
                mock_context,
                plan_id="plan-123-abc",
                title="New Feature Task",
            )

            assert result["success"] is True
            assert "task" in result
            assert result["task"]["id"] == "task-new-001"
            assert result["task"]["title"] == "New Feature Task"

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/planner/tasks"

            payload = call_args[1]["json"]
            assert payload["planId"] == "plan-123-abc"
            assert payload["title"] == "New Feature Task"
            assert "bucketId" not in payload
            assert "assignments" not in payload

    def test_msgraph_create_task_with_all_options(self, mock_context):
        """Test creating a task with all optional parameters."""
        created_task = {
            "id": "task-full-001",
            "title": "Complete Feature",
            "bucketId": "bucket-todo-123",
            "planId": "plan-123-abc",
            "percentComplete": 0,
            "priority": 1,
            "dueDateTime": "2025-01-25T17:00:00Z",
            "assignments": {
                "user-alice-123": {},
                "user-bob-456": {},
            },
            "@odata.etag": 'W/"test-etag"',
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_task
            mock_get_client.return_value = mock_client

            result = msgraph_create_task(
                mock_context,
                plan_id="plan-123-abc",
                title="Complete Feature",
                bucket_id="bucket-todo-123",
                assigned_to=["user-alice-123", "user-bob-456"],
                due_date="2025-01-25T17:00:00Z",
                priority=1,
            )

            assert result["success"] is True
            assert result["task"]["title"] == "Complete Feature"

            # Verify payload structure
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            assert payload["planId"] == "plan-123-abc"
            assert payload["title"] == "Complete Feature"
            assert payload["bucketId"] == "bucket-todo-123"
            assert payload["dueDateTime"] == "2025-01-25T17:00:00Z"
            assert payload["priority"] == 1

            # Check assignments format
            assert "assignments" in payload
            assert "user-alice-123" in payload["assignments"]
            assert "user-bob-456" in payload["assignments"]
            assert (
                payload["assignments"]["user-alice-123"]["@odata.type"]
                == "#microsoft.graph.plannerAssignment"
            )

    def test_msgraph_create_task_auth_error(self, mock_context):
        """Test handling of authentication error when creating task."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_create_task(
                mock_context,
                plan_id="plan-123-abc",
                title="Test Task",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_create_task_plan_not_found(self, mock_context):
        """Test creating task in non-existent plan."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphNotFoundError("Plan not found")
            mock_get_client.return_value = mock_client

            result = msgraph_create_task(
                mock_context,
                plan_id="nonexistent-plan",
                title="Test Task",
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphUpdateTask:
    """Test suite for msgraph_update_task tool."""

    def test_msgraph_update_task(self, mock_context, mock_task_full_data):
        """Test updating a task successfully."""
        updated_task = mock_task_full_data.copy()
        updated_task["title"] = "Updated Task Title"

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # First call: GET to retrieve etag
            mock_client.get.return_value = mock_task_full_data
            # Second call: PATCH to update
            mock_client.patch.return_value = updated_task
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-001",
                title="Updated Task Title",
            )

            assert result["success"] is True
            assert result["task"]["title"] == "Updated Task Title"

            # Verify GET was called first to get etag
            mock_client.get.assert_called_once_with("/planner/tasks/task-001")

            # Verify PATCH was called with If-Match header
            mock_client.patch.assert_called_once()
            patch_args = mock_client.patch.call_args
            assert patch_args[0][0] == "/planner/tasks/task-001"
            assert (
                patch_args[1]["headers"]["If-Match"]
                == 'W/"JzEtVGFzayAgQEBAQEBAQEBAQEBAQEBARCc="'
            )
            assert patch_args[1]["json"]["title"] == "Updated Task Title"

    def test_msgraph_update_task_etag_handling(self, mock_context):
        """Test that etag is properly fetched and used in If-Match header."""
        task_with_etag = {
            "id": "task-etag-test",
            "title": "Original Title",
            "@odata.etag": 'W/"unique-etag-12345"',
        }
        updated_task = {
            "id": "task-etag-test",
            "title": "New Title",
            "@odata.etag": 'W/"new-etag-67890"',
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = task_with_etag
            mock_client.patch.return_value = updated_task
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-etag-test",
                title="New Title",
            )

            assert result["success"] is True

            # Verify the etag from GET was used in PATCH
            patch_args = mock_client.patch.call_args
            assert patch_args[1]["headers"]["If-Match"] == 'W/"unique-etag-12345"'

    def test_msgraph_update_task_multiple_fields(
        self, mock_context, mock_task_full_data
    ):
        """Test updating multiple task fields."""
        updated_task = mock_task_full_data.copy()
        updated_task["title"] = "New Title"
        updated_task["percentComplete"] = 75

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_task_full_data
            mock_client.patch.return_value = updated_task
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-001",
                title="New Title",
                percent_complete=75,
                due_date="2025-02-01T17:00:00Z",
                priority=1,
            )

            assert result["success"] is True

            # Verify all fields in payload
            patch_args = mock_client.patch.call_args
            payload = patch_args[1]["json"]
            assert payload["title"] == "New Title"
            assert payload["percentComplete"] == 75
            assert payload["dueDateTime"] == "2025-02-01T17:00:00Z"
            assert payload["priority"] == 1

    def test_msgraph_update_task_no_fields_provided(self, mock_context):
        """Test updating task with no fields returns validation error."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"@odata.etag": 'W/"test"'}
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-001",
                # No fields provided
            )

            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert "No fields provided" in result["error"]

            # Verify PATCH was not called
            mock_client.patch.assert_not_called()

    def test_msgraph_update_task_invalid_percent_complete(
        self, mock_context, mock_task_full_data
    ):
        """Test updating task with invalid percent_complete."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_task_full_data
            mock_get_client.return_value = mock_client

            # Test > 100
            result = msgraph_update_task(
                mock_context,
                task_id="task-001",
                percent_complete=150,
            )

            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert "percent_complete" in result["error"]

    def test_msgraph_update_task_missing_etag(self, mock_context):
        """Test updating task when etag cannot be retrieved."""
        task_no_etag = {
            "id": "task-no-etag",
            "title": "Task Without Etag",
            # No @odata.etag
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = task_no_etag
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-no-etag",
                title="New Title",
            )

            assert result["success"] is False
            assert "etag" in result["error"].lower()

    def test_msgraph_update_task_not_found(self, mock_context):
        """Test updating a non-existent task."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Task not found")
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="nonexistent-task",
                title="New Title",
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_update_task_auth_error(self, mock_context):
        """Test handling of authentication error when updating."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_update_task(
                mock_context,
                task_id="task-001",
                title="New Title",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"


class TestMSGraphDeleteTask:
    """Test suite for msgraph_delete_task tool."""

    def test_msgraph_delete_task(self, mock_context, mock_task_full_data):
        """Test deleting a task successfully."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # First call: GET to retrieve etag
            mock_client.get.return_value = mock_task_full_data
            # Second call: DELETE
            mock_client.delete.return_value = None  # DELETE returns 204 No Content
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "task-001")

            assert result["success"] is True
            assert result["message"] == "Task deleted successfully"
            assert result["task_id"] == "task-001"

            # Verify GET was called first to get etag
            mock_client.get.assert_called_once_with("/planner/tasks/task-001")

            # Verify DELETE was called with If-Match header
            mock_client.delete.assert_called_once()
            delete_args = mock_client.delete.call_args
            assert delete_args[0][0] == "/planner/tasks/task-001"
            assert (
                delete_args[1]["headers"]["If-Match"]
                == 'W/"JzEtVGFzayAgQEBAQEBAQEBAQEBAQEBARCc="'
            )

    def test_msgraph_delete_task_etag_handling(self, mock_context):
        """Test that etag is properly fetched and used for deletion."""
        task_with_etag = {
            "id": "task-delete-etag",
            "title": "Task to Delete",
            "@odata.etag": 'W/"delete-etag-xyz"',
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = task_with_etag
            mock_client.delete.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "task-delete-etag")

            assert result["success"] is True

            # Verify the etag from GET was used in DELETE
            delete_args = mock_client.delete.call_args
            assert delete_args[1]["headers"]["If-Match"] == 'W/"delete-etag-xyz"'

    def test_msgraph_delete_task_missing_etag(self, mock_context):
        """Test deleting task when etag cannot be retrieved."""
        task_no_etag = {
            "id": "task-no-etag",
            "title": "Task Without Etag",
            # No @odata.etag
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = task_no_etag
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "task-no-etag")

            assert result["success"] is False
            assert "etag" in result["error"].lower()

            # Verify DELETE was not called
            mock_client.delete.assert_not_called()

    def test_msgraph_delete_task_not_found(self, mock_context):
        """Test deleting a non-existent task."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Task not found")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "nonexistent-task")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_delete_task_auth_error(self, mock_context):
        """Test handling of authentication error when deleting."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "task-001")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_delete_task_delete_fails(self, mock_context, mock_task_full_data):
        """Test handling when GET succeeds but DELETE fails."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_task_full_data
            mock_client.delete.side_effect = MSGraphNotFoundError(
                "Task was already deleted"
            )
            mock_get_client.return_value = mock_client

            result = msgraph_delete_task(mock_context, "task-001")

            assert result["success"] is False
            assert result["error_type"] == "not_found"


class TestMSGraphPlannerFormatting:
    """Test suite for Planner data formatting."""

    def test_task_fields_are_formatted_correctly(
        self, mock_context, mock_task_full_data
    ):
        """Verify all task fields are properly mapped from API response."""
        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_task_full_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_task(mock_context, "task-001")

            task = result["task"]
            assert task["id"] == "task-001"
            assert task["title"] == "Implement login feature"
            assert task["bucket_id"] == "bucket-inprogress-456"
            assert task["plan_id"] == "plan-123-abc"
            assert task["percent_complete"] == 50
            assert task["priority"] == 3
            assert task["priority_label"] == "important"
            assert task["due_date"] == "2025-01-20T17:00:00Z"
            assert task["start_date"] == "2025-01-15T09:00:00Z"
            assert task["created_datetime"] == "2025-01-14T10:00:00Z"
            assert task["completed_datetime"] is None
            assert task["assigned_to"] == ["user-alice-123"]
            assert task["has_description"] is True
            assert task["checklist_item_count"] == 5
            assert task["active_checklist_item_count"] == 3

    def test_missing_fields_have_defaults(self, mock_context):
        """Test handling of missing optional fields in task data."""
        minimal_task = {
            "id": "minimal-task",
            "title": "Minimal Task",
            # All other fields missing
        }

        with patch(
            "code_puppy.tools.msgraph.planner.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = minimal_task
            mock_get_client.return_value = mock_client

            result = msgraph_get_task(mock_context, "minimal-task")

            task = result["task"]
            assert task["id"] == "minimal-task"
            assert task["title"] == "Minimal Task"
            assert task["bucket_id"] is None
            assert task["percent_complete"] == 0
            assert task["priority"] == 5  # Default priority
            assert task["priority_label"] == "medium"
            assert task["assigned_to"] == []
            assert task["has_description"] is False
            assert task["checklist_item_count"] == 0
