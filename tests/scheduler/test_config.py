"""Tests for scheduler configuration and task management."""

from unittest.mock import patch

import pytest

from code_puppy.scheduler.config import (
    ScheduledTask,
    add_task,
    delete_task,
    load_tasks,
    save_tasks,
    toggle_task,
)


class TestScheduledTask:
    """Tests for the ScheduledTask dataclass."""

    def test_create_task_with_defaults(self):
        """Test creating a task with default values."""
        task = ScheduledTask(name="Test Task", prompt="Do something")
        assert task.name == "Test Task"
        assert task.prompt == "Do something"
        assert task.agent == "code-puppy"
        assert task.enabled is True
        assert task.schedule_type == "interval"
        assert task.schedule_value == "1h"
        assert len(task.id) == 8

    def test_create_task_with_all_fields(self):
        """Test creating a task with all fields specified."""
        task = ScheduledTask(
            id="abc12345",
            name="Full Task",
            prompt="Complete prompt",
            agent="python-reviewer",
            model="gpt-4o",
            schedule_type="daily",
            schedule_value="24h",
            working_directory="/tmp",
            enabled=False,
        )
        assert task.id == "abc12345"
        assert task.agent == "python-reviewer"
        assert task.model == "gpt-4o"
        assert task.enabled is False

    def test_task_to_dict(self):
        """Test serializing task to dictionary."""
        task = ScheduledTask(name="Test", prompt="Prompt")
        d = task.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "Test"
        assert d["prompt"] == "Prompt"

    def test_task_from_dict(self):
        """Test deserializing task from dictionary."""
        data = {
            "id": "test123",
            "name": "From Dict",
            "prompt": "Test prompt",
            "agent": "code-puppy",
            "model": "",
            "schedule_type": "interval",
            "schedule_value": "30m",
            "enabled": True,
        }
        task = ScheduledTask.from_dict(data)
        assert task.id == "test123"
        assert task.name == "From Dict"


class TestTaskPersistence:
    """Tests for task persistence functions."""

    @pytest.fixture
    def temp_schedules_file(self, tmp_path):
        """Create a temporary schedules file."""
        schedules_dir = tmp_path / "scheduler_logs"
        schedules_dir.mkdir()
        schedules_file = tmp_path / "scheduled_tasks.json"
        with patch("code_puppy.scheduler.config.SCHEDULES_FILE", str(schedules_file)):
            with patch(
                "code_puppy.scheduler.config.SCHEDULER_LOG_DIR", str(schedules_dir)
            ):
                yield schedules_file

    def test_load_tasks_empty_file(self, temp_schedules_file):
        """Test loading tasks when file doesn't exist."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            tasks = load_tasks()
            assert tasks == []

    def test_save_and_load_tasks(self, temp_schedules_file):
        """Test saving and loading tasks."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            with patch(
                "code_puppy.scheduler.config.SCHEDULER_LOG_DIR",
                str(temp_schedules_file.parent / "logs"),
            ):
                tasks = [
                    ScheduledTask(name="Task 1", prompt="Prompt 1"),
                    ScheduledTask(name="Task 2", prompt="Prompt 2"),
                ]
                save_tasks(tasks)
                loaded = load_tasks()
                assert len(loaded) == 2
                assert loaded[0].name == "Task 1"
                assert loaded[1].name == "Task 2"

    def test_add_task(self, temp_schedules_file):
        """Test adding a task."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            with patch(
                "code_puppy.scheduler.config.SCHEDULER_LOG_DIR",
                str(temp_schedules_file.parent / "logs"),
            ):
                task = ScheduledTask(name="New Task", prompt="New prompt")
                add_task(task)
                tasks = load_tasks()
                assert len(tasks) == 1
                assert tasks[0].name == "New Task"

    def test_delete_task(self, temp_schedules_file):
        """Test deleting a task."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            with patch(
                "code_puppy.scheduler.config.SCHEDULER_LOG_DIR",
                str(temp_schedules_file.parent / "logs"),
            ):
                task = ScheduledTask(id="del123", name="To Delete", prompt="Delete me")
                add_task(task)
                assert delete_task("del123") is True
                assert load_tasks() == []

    def test_delete_nonexistent_task(self, temp_schedules_file):
        """Test deleting a task that doesn't exist."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            assert delete_task("nonexistent") is False

    def test_toggle_task(self, temp_schedules_file):
        """Test toggling a task's enabled state."""
        with patch(
            "code_puppy.scheduler.config.SCHEDULES_FILE", str(temp_schedules_file)
        ):
            with patch(
                "code_puppy.scheduler.config.SCHEDULER_LOG_DIR",
                str(temp_schedules_file.parent / "logs"),
            ):
                task = ScheduledTask(
                    id="tog123", name="Toggle Me", prompt="Toggle", enabled=True
                )
                add_task(task)

                result = toggle_task("tog123")
                assert result is False  # Was True, now False

                result = toggle_task("tog123")
                assert result is True  # Was False, now True
