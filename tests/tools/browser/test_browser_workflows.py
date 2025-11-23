"""Comprehensive tests for browser_workflows.py module.

Tests workflow management including saving, listing, and reading browser automation
workflows as markdown files. Achieves 70%+ coverage.
"""

import os

# Import the module directly to avoid circular imports
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.browser_workflows import (
    get_workflows_directory,
    list_workflows,
    read_workflow,
    register_list_workflows,
    register_read_workflow,
    register_save_workflow,
    save_workflow,
)


class BrowserWorkflowsBaseTest:
    """Base test class with common mocking for browser workflows."""

    @pytest.fixture
    def temp_workflows_dir(self):
        """Create a temporary directory for workflow files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_context(self):
        """Mock RunContext for testing registration functions."""
        return MagicMock()

    @pytest.fixture
    def sample_workflow_content(self):
        """Sample workflow content for testing."""
        return """# Test Workflow

## Description
This is a test automation workflow.

## Steps
1. Navigate to page
2. Click button
3. Fill form
4. Submit

## Code
```python
browser_click("#button")
browser_set_text("#input", "test")
```
"""


class TestGetWorkflowsDirectory(BrowserWorkflowsBaseTest):
    """Test get_workflows_directory function."""

    def test_get_workflows_directory_creates_directory(self):
        """Test that workflows directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock home directory
            mock_home = Path(temp_dir)

            with patch("pathlib.Path.home", return_value=mock_home):
                workflows_dir = get_workflows_directory()

                expected_dir = mock_home / ".code_puppy" / "browser_workflows"
                assert workflows_dir == expected_dir
                assert workflows_dir.exists()
                assert workflows_dir.is_dir()

    def test_get_workflows_directory_existing_directory(self):
        """Test returning existing workflows directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_home = Path(temp_dir)
            expected_dir = mock_home / ".code_puppy" / "browser_workflows"
            expected_dir.mkdir(parents=True, exist_ok=True)

            with patch("pathlib.Path.home", return_value=mock_home):
                workflows_dir = get_workflows_directory()

                assert workflows_dir == expected_dir
                assert workflows_dir.exists()

    def test_get_workflows_directory_path_object(self):
        """Test that get_workflows_directory returns a Path object."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path(temp_dir)
                workflows_dir = get_workflows_directory()
                assert isinstance(workflows_dir, Path)


class TestSaveWorkflow(BrowserWorkflowsBaseTest):
    """Test save_workflow function and its registration."""

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_success(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test successful workflow saving."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await save_workflow("test-workflow", sample_workflow_content)

        assert result["success"] is True
        assert result["name"] == "test-workflow.md"
        assert result["size"] == len(sample_workflow_content)
        assert result["path"] == str(temp_workflows_dir / "test-workflow.md")

        # Verify file was created and content matches
        workflow_file = temp_workflows_dir / "test-workflow.md"
        assert workflow_file.exists()
        with open(workflow_file, "r", encoding="utf-8") as f:
            assert f.read() == sample_workflow_content

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_with_special_chars(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test saving workflow with special characters in name."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await save_workflow("Workflow with Spaces & Special!", "content")

        assert result["success"] is True
        assert result["name"] == "workflow-with-spaces--special.md"

        workflow_file = temp_workflows_dir / "workflow-with-spaces--special.md"
        assert workflow_file.exists()

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_already_exists(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test overwriting existing workflow."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create initial workflow
        workflow_file = temp_workflows_dir / "test.md"
        with open(workflow_file, "w") as f:
            f.write("old content")

        result = await save_workflow("test", sample_workflow_content)

        assert result["success"] is True

        # Verify content was updated
        with open(workflow_file, "r") as f:
            assert f.read() == sample_workflow_content

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_directory_creation_error(
        self, mock_get_dir, sample_workflow_content
    ):
        """Test error when directory creation fails."""
        mock_get_dir.side_effect = PermissionError("Cannot create directory")

        result = await save_workflow("test", sample_workflow_content)

        assert result["success"] is False
        assert "Cannot create directory" in result["error"]
        assert result["name"] == "test"

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_file_write_error(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test error when file write fails."""
        mock_get_dir.return_value = temp_workflows_dir

        # Make the directory read-only
        os.chmod(temp_workflows_dir, 0o444)

        try:
            result = await save_workflow("test", "content")

            assert result["success"] is False
            assert "Permission denied" in result["error"]
        finally:
            # Restore permissions for cleanup
            os.chmod(temp_workflows_dir, 0o755)

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_empty_name(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test saving workflow with empty name."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await save_workflow("", sample_workflow_content)

        assert result["success"] is True
        assert result["name"] == "workflow.md"

        workflow_file = temp_workflows_dir / "workflow.md"
        assert workflow_file.exists()

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_save_workflow_with_md_extension(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test saving workflow with .md extension already included."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await save_workflow("test.md", sample_workflow_content)

        assert result["success"] is True
        assert result["name"] == "test.md"

        workflow_file = temp_workflows_dir / "test.md"
        assert workflow_file.exists()

    def test_register_save_workflow(self, mock_context):
        """Test registration of save_workflow tool."""
        agent = MagicMock()

        register_save_workflow(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_save_workflow"


class TestListWorkflows(BrowserWorkflowsBaseTest):
    """Test list_workflows function and its registration."""

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_list_workflows_empty_directory(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test listing workflows in empty directory."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await list_workflows()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["workflows"] == []
        assert result["directory"] == str(temp_workflows_dir)

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_list_workflows_multiple_files(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test listing multiple workflow files."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create test workflow files
        workflows = [
            ("login.md", "# Login Workflow"),
            ("search.md", "# Search Workflow"),
            ("checkout.md", "# Checkout Workflow"),
        ]

        for filename, content in workflows:
            (temp_workflows_dir / filename).write_text(content)

        # Sleep to ensure different modification times
        import time

        time.sleep(0.1)
        (temp_workflows_dir / "recent.md").write_text("# Recent Workflow")

        result = await list_workflows()

        assert result["success"] is True
        assert result["count"] == 4
        assert len(result["workflows"]) == 4

        # Should be sorted by modification time (newest first)
        workflow_names = [w["name"] for w in result["workflows"]]
        assert workflow_names[0] == "recent.md"  # Most recent
        assert "login.md" in workflow_names
        assert "search.md" in workflow_names
        assert "checkout.md" in workflow_names

        # Verify workflow properties
        for workflow in result["workflows"]:
            assert "name" in workflow
            assert "path" in workflow
            assert "size" in workflow
            assert "modified" in workflow
            assert workflow["size"] > 0

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_list_workflows_ignores_non_md_files(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test that only .md files are listed."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create mix of files
        files = [
            ("workflow.md", "# Workflow"),
            ("not-workflow.txt", "Not a workflow"),
            ("script.py", "print('hello')"),
            ("another.md", "# Another Workflow"),
            ("readme.md", "# README"),
        ]

        for filename, content in files:
            (temp_workflows_dir / filename).write_text(content)

        result = await list_workflows()

        assert result["success"] is True
        assert result["count"] == 3  # Only .md files

        workflow_names = [w["name"] for w in result["workflows"]]
        assert "workflow.md" in workflow_names
        assert "another.md" in workflow_names
        assert "readme.md" in workflow_names
        assert "not-workflow.txt" not in workflow_names
        assert "script.py" not in workflow_names

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_list_workflows_directory_error(self, mock_get_dir):
        """Test error when workflows directory doesn't exist."""
        mock_get_dir.side_effect = FileNotFoundError("Directory not found")

        result = await list_workflows()

        assert result["success"] is False
        assert "Directory not found" in result["error"]

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_list_workflows_file_read_error(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test handling of unreadable files."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create a readable file and an unreadable file
        good_file = temp_workflows_dir / "good.md"
        good_file.write_text("# Good Workflow")

        bad_file = temp_workflows_dir / "bad.md"
        bad_file.write_text("# Bad Workflow")
        bad_file.chmod(0o000)  # Make unreadable

        try:
            result = await list_workflows()

            assert result["success"] is True
            # Should still return readable files
            workflow_names = [w["name"] for w in result["workflows"]]
            assert "good.md" in workflow_names
            # bad.md might be skipped due to permissions
        finally:
            # Restore permissions for cleanup
            if bad_file.exists():
                bad_file.chmod(0o644)

    def test_register_list_workflows(self, mock_context):
        """Test registration of list_workflows tool."""
        agent = MagicMock()

        register_list_workflows(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_list_workflows"


class TestReadWorkflow(BrowserWorkflowsBaseTest):
    """Test read_workflow function and its registration."""

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_success(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test successful workflow reading."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create workflow file
        workflow_file = temp_workflows_dir / "test-workflow.md"
        workflow_file.write_text(sample_workflow_content, encoding="utf-8")

        result = await read_workflow("test-workflow")

        assert result["success"] is True
        assert result["name"] == "test-workflow.md"
        assert result["content"] == sample_workflow_content
        assert result["size"] == len(sample_workflow_content)
        assert result["path"] == str(workflow_file)

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_with_extension(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test reading workflow with .md extension included."""
        mock_get_dir.return_value = temp_workflows_dir

        workflow_file = temp_workflows_dir / "already-with-ext.md"
        workflow_file.write_text(sample_workflow_content)

        result = await read_workflow("already-with-ext.md")

        assert result["success"] is True
        assert result["name"] == "already-with-ext.md"
        assert result["content"] == sample_workflow_content

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_not_found(self, mock_get_dir, temp_workflows_dir):
        """Test reading non-existent workflow."""
        mock_get_dir.return_value = temp_workflows_dir

        result = await read_workflow("nonexistent-workflow")

        assert result["success"] is False
        assert "not found" in result["error"]
        assert result["name"] == "nonexistent-workflow.md"

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_directory_error(self, mock_get_dir):
        """Test error when workflows directory is inaccessible."""
        mock_get_dir.side_effect = PermissionError("Access denied")

        result = await read_workflow("test-workflow")

        assert result["success"] is False
        assert "Access denied" in result["error"]

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_file_read_error(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test error when file cannot be read."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create file but make it unreadable
        workflow_file = temp_workflows_dir / "unreadable.md"
        workflow_file.write_text("Content")
        workflow_file.chmod(0o000)

        try:
            result = await read_workflow("unreadable")

            assert result["success"] is False
            assert "Permission denied" in result["error"]
        finally:
            # Restore permissions for cleanup
            if workflow_file.exists():
                workflow_file.chmod(0o644)

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_empty_file(self, mock_get_dir, temp_workflows_dir):
        """Test reading empty workflow file."""
        mock_get_dir.return_value = temp_workflows_dir

        workflow_file = temp_workflows_dir / "empty.md"
        workflow_file.write_text("")

        result = await read_workflow("empty")

        assert result["success"] is True
        assert result["content"] == ""
        assert result["size"] == 0

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_large_file(self, mock_get_dir, temp_workflows_dir):
        """Test reading large workflow file."""
        mock_get_dir.return_value = temp_workflows_dir

        # Create a large content
        large_content = "# Large Workflow\n\n" + "This is a line.\n" * 1000

        workflow_file = temp_workflows_dir / "large.md"
        workflow_file.write_text(large_content)

        result = await read_workflow("large")

        assert result["success"] is True
        assert result["content"] == large_content
        assert result["size"] == len(large_content)

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_read_workflow_unicode_content(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test reading workflow with unicode content."""
        mock_get_dir.return_value = temp_workflows_dir

        unicode_content = "# Unicode Workflow\n\n😀 🐶 🍕 Café Résumé"

        workflow_file = temp_workflows_dir / "unicode.md"
        workflow_file.write_text(unicode_content, encoding="utf-8")

        result = await read_workflow("unicode")

        assert result["success"] is True
        assert result["content"] == unicode_content

    def test_register_read_workflow(self, mock_context):
        """Test registration of read_workflow tool."""
        agent = MagicMock()

        register_read_workflow(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_read_workflow"


class TestIntegrationScenarios(BrowserWorkflowsBaseTest):
    """Integration test scenarios for workflow management."""

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_complete_workflow_lifecycle(
        self, mock_get_dir, temp_workflows_dir, sample_workflow_content
    ):
        """Test complete save -> list -> read workflow lifecycle."""
        mock_get_dir.return_value = temp_workflows_dir

        # 1. List empty directory
        list_result1 = await list_workflows()
        assert list_result1["success"] is True
        assert list_result1["count"] == 0

        # 2. Save a workflow
        save_result = await save_workflow("my-workflow", sample_workflow_content)
        assert save_result["success"] is True
        assert save_result["name"] == "my-workflow.md"

        # 3. List directory with workflow
        list_result2 = await list_workflows()
        assert list_result2["success"] is True
        assert list_result2["count"] == 1
        assert list_result2["workflows"][0]["name"] == "my-workflow.md"

        # 4. Read the workflow
        read_result = await read_workflow("my-workflow")
        assert read_result["success"] is True
        assert read_result["content"] == sample_workflow_content

        # 5. Save another workflow
        another_content = "# Another Workflow\n\nMore content here."
        save_result2 = await save_workflow("another-workflow", another_content)
        assert save_result2["success"] is True

        # 6. List with both workflows
        list_result3 = await list_workflows()
        assert list_result3["success"] is True
        assert list_result3["count"] == 2

        workflow_names = [w["name"] for w in list_result3["workflows"]]
        assert "another-workflow.md" in workflow_names  # Should be first (newer)
        assert "my-workflow.md" in workflow_names

        # 7. Read both workflows
        read_result1 = await read_workflow("my-workflow")
        read_result2 = await read_workflow("another-workflow")

        assert read_result1["content"] == sample_workflow_content
        assert read_result2["content"] == another_content

    @patch("tools.browser.browser_workflows.get_workflows_directory")
    @pytest.mark.asyncio
    async def test_workflow_name_sanitization_cycle(
        self, mock_get_dir, temp_workflows_dir
    ):
        """Test that workflow names are properly sanitized and can be recalled."""
        mock_get_dir.return_value = temp_workflows_dir

        # Save workflow with problematic name
        original_name = "My Workflow Test!@#$%^&*()"
        content = "# Test Content"

        save_result = await save_workflow(original_name, content)
        assert save_result["success"] is True

        sanitized_name = save_result["name"]
        assert sanitized_name == "my-workflow-test.md"

        # Should be able to read using sanitized name
        read_result = await read_workflow("my-workflow-test")
        assert read_result["success"] is True
        assert read_result["content"] == content

        # Should also be able to read using full name with extension
        read_result2 = await read_workflow("my-workflow-test.md")
        assert read_result2["success"] is True
        assert read_result2["content"] == content


if __name__ == "__main__":
    pytest.main([__file__])
