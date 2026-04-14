"""Integration tests for BigQuery functionality."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.walmart_specific.bigquery_client import (
    BigQueryClient,
    BigQueryAccessDeniedError,
    BigQueryAuthError,
    BigQueryAPIError,
    BigQueryNotFoundError,
)
from code_puppy.tools.bigquery_tools import (
    bigquery_get_default_project,
    bigquery_list_all_projects,
    bigquery_list_datasets,
    bigquery_list_tables,
    bigquery_execute_query,
    bigquery_get_table_schema,
    _extract_table_from_error,
)
from code_puppy.agents.agent_bigquery_explorer import BigQueryExplorerAgent


@pytest.fixture
def mock_bigquery_client():
    """Create a mock BigQuery client."""
    with patch("code_puppy.plugins.walmart_specific.bigquery_client.bigquery"):
        client = Mock(spec=BigQueryClient)
        client.project_id = "test-project"
        client.close = Mock()
        return client


@pytest.fixture
def mock_run_context():
    """Create a mock RunContext for tool testing."""
    ctx = Mock()
    return ctx


class TestBigQueryClientIntegration:
    """Integration tests for BigQueryClient."""

    def test_client_initialization_success(self):
        """Test successful BigQuery client initialization."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
        ) as mock_bq:
            mock_client_instance = Mock()
            mock_client_instance.project = "test-project-123"
            mock_bq.Client.return_value = mock_client_instance

            client = BigQueryClient()

            assert client.project_id == "test-project-123"
            mock_bq.Client.assert_called_once()

    def test_client_initialization_no_credentials(self):
        """Test client initialization without credentials."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
        ) as mock_bq:
            from google.auth.exceptions import DefaultCredentialsError

            mock_bq.Client.side_effect = DefaultCredentialsError("No credentials")

            with pytest.raises(BigQueryAuthError, match="No valid credentials"):
                BigQueryClient()

    def test_list_projects(self, mock_bigquery_client):
        """Test listing default project."""
        mock_bigquery_client.list_projects.return_value = [
            {"project_id": "my-project", "name": "my-project", "state": "ACTIVE"}
        ]
        projects = mock_bigquery_client.list_projects()

        assert len(projects) == 1
        assert projects[0]["project_id"] == "my-project"

    def test_sql_validation_safe_query(self, mock_bigquery_client):
        """Test SQL validation allows safe SELECT queries."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse"
        ) as mock_sqlparse:
            mock_statement = Mock()
            mock_statement.get_type.return_value = "SELECT"
            mock_statement.flatten.return_value = []
            mock_sqlparse.parse.return_value = [mock_statement]

            mock_bigquery_client._is_safe_query = BigQueryClient._is_safe_query.__get__(
                mock_bigquery_client
            )

            # Should return True for SELECT
            result = mock_bigquery_client._is_safe_query("SELECT * FROM table")
            assert result is True

    def test_sql_validation_dangerous_query(self, mock_bigquery_client):
        """Test SQL validation blocks dangerous queries."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse"
        ) as mock_sqlparse:
            mock_statement = Mock()
            mock_statement.get_type.return_value = "DELETE"
            mock_sqlparse.parse.return_value = [mock_statement]

            mock_bigquery_client._is_safe_query = BigQueryClient._is_safe_query.__get__(
                mock_bigquery_client
            )

            # Should return False for DELETE
            result = mock_bigquery_client._is_safe_query("DELETE FROM table")
            assert result is False


class TestBigQueryToolsIntegration:
    """Integration tests for BigQuery tools."""

    def test_get_default_project_tool(self, mock_run_context):
        """Test bigquery_get_default_project tool."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.project_id = "my-default-project"
            mock_client.list_projects.return_value = [
                {
                    "project_id": "my-default-project",
                    "name": "my-default-project",
                    "state": "ACTIVE",
                }
            ]
            MockClient.return_value = mock_client

            result = bigquery_get_default_project(mock_run_context)

            assert result["success"] is True
            assert result["default_project"] == "my-default-project"
            assert result["count"] == 1

    def test_list_all_projects_tool(self, mock_run_context):
        """Test bigquery_list_all_projects tool."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.list_all_projects.return_value = [
                {"project_id": "project-1", "name": "Project 1"},
                {"project_id": "project-2", "name": "Project 2"},
            ]
            MockClient.return_value = mock_client

            result = bigquery_list_all_projects(mock_run_context)

            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["projects"]) == 2

    def test_list_datasets_tool(self, mock_run_context):
        """Test bigquery_list_datasets tool."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.project_id = "test-project"
            mock_client.list_datasets.return_value = [
                {
                    "dataset_id": "dataset1",
                    "project": "test-project",
                    "full_id": "test-project.dataset1",
                }
            ]
            MockClient.return_value = mock_client

            result = bigquery_list_datasets(mock_run_context)

            assert result["success"] is True
            assert result["count"] == 1
            assert result["datasets"][0]["dataset_id"] == "dataset1"

    def test_list_tables_tool(self, mock_run_context):
        """Test bigquery_list_tables tool."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.project_id = "test-project"
            mock_client.list_tables.return_value = [
                {
                    "table_id": "table1",
                    "table_type": "TABLE",
                    "full_id": "test-project.dataset1.table1",
                }
            ]
            MockClient.return_value = mock_client

            result = bigquery_list_tables(mock_run_context, dataset_id="dataset1")

            assert result["success"] is True
            assert result["count"] == 1
            assert result["tables"][0]["table_id"] == "table1"

    def test_execute_query_tool_success(self, mock_run_context):
        """Test bigquery_execute_query tool with successful query."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.return_value = {
                "rows": [{"count": 100}],
                "schema": [{"name": "count", "type": "INTEGER"}],
                "total_rows": 1,
                "job_id": "job-123",
                "bytes_processed": 1024,
                "bytes_billed": 2048,
            }
            MockClient.return_value = mock_client

            result = bigquery_execute_query(
                mock_run_context, query="SELECT COUNT(*) as count FROM table"
            )

            assert result["success"] is True
            assert len(result["rows"]) == 1
            assert result["rows"][0]["count"] == 100

    def test_execute_query_tool_saves_results(self, mock_run_context, tmp_path: Path):
        """Test saving query results to a user-provided path."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.return_value = {
                "rows": [{"id": i, "value": f"row-{i}"} for i in range(10)],
                "schema": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "value", "type": "STRING"},
                ],
                "total_rows": 10,
                "job_id": "job-save-123",
                "bytes_processed": 512,
                "bytes_billed": 1024,
            }
            MockClient.return_value = mock_client

            output_file = tmp_path / "scan_and_go.csv"
            result = bigquery_execute_query(
                mock_run_context,
                query="SELECT * FROM table",
                max_results=10,
                save_results=True,
                output_path=str(output_file),
                preview_rows=5,
            )

            assert result["success"] is True
            assert result["saved_file_path"] == str(output_file)
            assert output_file.exists()
            assert result["rows_truncated"] is True
            assert len(result["rows"]) == 5
            assert result["rows_saved_to_file"] == 10

    def test_execute_query_tool_auto_saves_large_results(
        self, mock_run_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test automatic saving when result sets are large."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.return_value = {
                "rows": [{"id": i} for i in range(250)],
                "schema": [{"name": "id", "type": "INTEGER"}],
                "total_rows": 250,
                "job_id": "job-auto-456",
                "bytes_processed": 2048,
                "bytes_billed": 4096,
            }
            MockClient.return_value = mock_client

            monkeypatch.chdir(tmp_path)
            result = bigquery_execute_query(
                mock_run_context,
                query="SELECT * FROM big_table",
                max_results=250,
                preview_rows=25,
            )

            assert result["success"] is True
            assert result["saved_file_path"] is not None
            saved_path = Path(result["saved_file_path"])
            assert saved_path.exists()
            assert result["auto_saved_result_file"] is True
            assert result["rows_truncated"] is True
            assert len(result["rows"]) == 25
            assert saved_path.parent == Path.cwd() / "bigquery_results"

    def test_execute_query_tool_blocked(self, mock_run_context):
        """Test bigquery_execute_query blocks dangerous queries."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.side_effect = BigQueryAPIError(
                "Dangerous SQL operation detected: DELETE"
            )
            MockClient.return_value = mock_client

            result = bigquery_execute_query(mock_run_context, query="DELETE FROM table")

            assert result["success"] is False
            assert "Dangerous SQL operation" in result["error"]

    def test_get_table_schema_tool(self, mock_run_context):
        """Test bigquery_get_table_schema tool."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.project_id = "test-project"
            mock_client.get_table_schema.return_value = [
                {
                    "name": "id",
                    "type": "INTEGER",
                    "mode": "REQUIRED",
                    "description": "Primary key",
                },
                {
                    "name": "name",
                    "type": "STRING",
                    "mode": "NULLABLE",
                    "description": "User name",
                },
            ]
            MockClient.return_value = mock_client

            result = bigquery_get_table_schema(
                mock_run_context, table_id="users", dataset_id="my_dataset"
            )

            assert result["success"] is True
            assert len(result["schema"]) == 2
            assert result["schema"][0]["name"] == "id"
            assert result["schema"][1]["type"] == "STRING"

    def test_tool_error_handling(self, mock_run_context):
        """Test tool error handling."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            MockClient.side_effect = BigQueryAuthError("No credentials")

            result = bigquery_get_default_project(mock_run_context)

            assert result["success"] is False
            assert "error" in result
            assert "No credentials" in result["error"]


class TestBigQueryAgentIntegration:
    """Integration tests for BigQueryExplorerAgent."""

    def test_agent_initialization(self):
        """Test BigQueryExplorerAgent initialization."""
        agent = BigQueryExplorerAgent()

        assert agent.name == "bigquery-explorer"
        assert agent.display_name == "BigQuery Explorer 📊"

    def test_agent_has_required_tools(self):
        """Test agent has all required tools registered."""
        agent = BigQueryExplorerAgent()
        tools = agent.get_available_tools()  # FIXED: use method instead of property

        expected_tools = [
            "bigquery_get_default_project",
            "bigquery_list_all_projects",
            "bigquery_list_datasets",
            "bigquery_list_tables",
            "bigquery_execute_query",
            "bigquery_get_table_schema",
            "list_files",
            "read_file",
            "grep",
            "edit_file",
            "delete_file",
            "agent_run_shell_command",
            "agent_share_your_reasoning",
        ]

        for tool in expected_tools:
            assert tool in tools, f"Tool {tool} not found in agent"

    def test_agent_system_prompt(self):
        """Test agent has proper system prompt."""
        agent = BigQueryExplorerAgent()
        system_prompt = (
            agent.get_system_prompt()
        )  # FIXED: use method instead of property

        # Check for key instructions
        assert "BigQuery" in system_prompt
        assert "SELECT" in system_prompt
        assert "read-only" in system_prompt or "READ-ONLY" in system_prompt


class TestBigQuerySQLValidation:
    """Integration tests for SQL validation."""

    def test_allow_select_queries(self):
        """Test that SELECT queries are allowed."""
        safe_queries = [
            "SELECT * FROM table",
            "SELECT id, name FROM users WHERE active = true",
            "WITH cte AS (SELECT * FROM table) SELECT * FROM cte",
            "SELECT COUNT(*) FROM table GROUP BY category",
        ]

        with patch("code_puppy.plugins.walmart_specific.bigquery_client.bigquery"):
            with patch(
                "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse"
            ) as mock_sqlparse:
                for query in safe_queries:
                    mock_statement = Mock()
                    mock_statement.get_type.return_value = "SELECT"
                    mock_statement.flatten.return_value = []
                    mock_sqlparse.parse.return_value = [mock_statement]

                    client = BigQueryClient.__new__(BigQueryClient)
                    result = client._is_safe_query(query)
                    assert result is True, f"Query should be allowed: {query}"

    def test_block_dangerous_queries(self):
        """Test that dangerous queries are blocked."""
        dangerous_queries = [
            "DELETE FROM users WHERE id = 1",
            "DROP TABLE users",
            "TRUNCATE TABLE logs",
            "INSERT INTO users VALUES ('test')",
            "UPDATE users SET active = false",
            "CREATE TABLE new_table (id INT)",
            "ALTER TABLE users ADD COLUMN email STRING",
        ]

        with patch("code_puppy.plugins.walmart_specific.bigquery_client.bigquery"):
            with patch(
                "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse"
            ) as mock_sqlparse:
                for query in dangerous_queries:
                    mock_statement = Mock()
                    # Extract operation type from query
                    operation = query.split()[0].upper()
                    mock_statement.get_type.return_value = operation
                    mock_sqlparse.parse.return_value = [mock_statement]

                    client = BigQueryClient.__new__(BigQueryClient)
                    result = client._is_safe_query(query)
                    assert result is False, f"Query should be blocked: {query}"

    def test_empty_query_validation(self):
        """Test that empty queries are rejected."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
        ) as mock_bq:
            mock_client = Mock()
            mock_client.project = "test-project"
            mock_bq.Client.return_value = mock_client

            client = BigQueryClient()

            with pytest.raises(BigQueryAPIError, match="Query cannot be empty"):
                client._validate_query_safety("   ")


class TestBigQueryErrorHandling:
    """Integration tests for error handling."""

    def test_not_found_error(self):
        """Test BigQueryNotFoundError is raised for missing resources."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.list_tables.side_effect = BigQueryNotFoundError(
                "Dataset not found"
            )
            MockClient.return_value = mock_client

            result = bigquery_list_tables(Mock(), dataset_id="nonexistent")

            assert result["success"] is False
            assert "not found" in result["error"].lower()

    def test_auth_error(self):
        """Test BigQueryAuthError is raised for auth issues."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            MockClient.side_effect = BigQueryAuthError("Invalid credentials")

            result = bigquery_get_default_project(Mock())

            assert result["success"] is False
            assert "credentials" in result["error"].lower()

    def test_api_error(self):
        """Test BigQueryAPIError is raised for API failures."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.side_effect = BigQueryAPIError(
                "Query execution failed"
            )
            MockClient.return_value = mock_client

            result = bigquery_execute_query(Mock(), query="SELECT 1")

            assert result["success"] is False
            assert "failed" in result["error"].lower()


class TestBigQueryAccessDenied:
    """Tests for graceful 403 / access-denied error handling (issue #172)."""

    # ------------------------------------------------------------------
    # _extract_table_from_error helper
    # ------------------------------------------------------------------

    def test_extract_table_backtick_format(self):
        """Extracts table from GCP backtick-quoted error strings."""
        err = (
            "403 Access Denied: Table `wmt-trans-bi.STORE.WM_DELIVERY_WINDOWS`: "
            "User does not have permission to query table."
        )
        assert _extract_table_from_error(err) == "wmt-trans-bi.STORE.WM_DELIVERY_WINDOWS"

    def test_extract_table_colon_format(self):
        """Extracts table from GCP colon-separated error strings."""
        err = "403 Access Denied: Table wmt-trans-bi:STORE.WM_DELIVERY_WINDOWS"
        result = _extract_table_from_error(err)
        assert result is not None
        assert "wmt-trans-bi" in result

    def test_extract_table_returns_none_when_not_found(self):
        """Returns None when no table reference is in the error."""
        assert _extract_table_from_error("generic network error") is None

    # ------------------------------------------------------------------
    # bigquery_client — exception detection
    # ------------------------------------------------------------------

    def test_client_raises_access_denied_on_403(self):
        """execute_query raises BigQueryAccessDeniedError when GCP returns 403."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
        ) as mock_bq:
            mock_bq_client = Mock()
            mock_bq_client.project = "test-project"
            mock_bq.Client.return_value = mock_bq_client

            mock_job = Mock()
            mock_job.result.side_effect = Exception(
                "403 Access Denied: Table `proj.ds.tbl`: "
                "User does not have permission to query table."
            )
            mock_bq_client.query.return_value = mock_job

            from code_puppy.plugins.walmart_specific.bigquery_client import (
                BigQueryClient,
            )

            client = BigQueryClient()
            with pytest.raises(BigQueryAccessDeniedError):
                client.execute_query("SELECT 1")

    def test_client_raises_access_denied_on_permission_denied(self):
        """execute_query raises BigQueryAccessDeniedError on 'permission denied'."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
        ) as mock_bq:
            mock_bq_client = Mock()
            mock_bq_client.project = "test-project"
            mock_bq.Client.return_value = mock_bq_client

            mock_job = Mock()
            mock_job.result.side_effect = Exception(
                "Permission denied on resource project wmt-trans-bi."
            )
            mock_bq_client.query.return_value = mock_job

            from code_puppy.plugins.walmart_specific.bigquery_client import (
                BigQueryClient,
            )

            client = BigQueryClient()
            with pytest.raises(BigQueryAccessDeniedError):
                client.execute_query("SELECT 1")

    # ------------------------------------------------------------------
    # bigquery_tools — graceful tool response
    # ------------------------------------------------------------------

    def test_tool_returns_graceful_access_denied_response(self):
        """Tool surfaces access_denied error_type with suggestion, not a crash."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.side_effect = BigQueryAccessDeniedError(
                "403 Access Denied: Table `wmt-trans-bi.STORE.WM_DELIVERY_WINDOWS`: "
                "User does not have permission to query table."
            )
            MockClient.return_value = mock_client

            result = bigquery_execute_query(
                Mock(),
                query="SELECT * FROM `wmt-trans-bi.STORE.WM_DELIVERY_WINDOWS`",
            )

        assert result["success"] is False
        assert result["error_type"] == "access_denied"
        assert "don't have access" in result["error"]
        assert "suggestion" in result
        assert result["table"] == "wmt-trans-bi.STORE.WM_DELIVERY_WINDOWS"

    def test_tool_access_denied_without_table_name(self):
        """Graceful response even when table name can't be parsed from error."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.execute_query.side_effect = BigQueryAccessDeniedError(
                "Access denied."
            )
            MockClient.return_value = mock_client

            result = bigquery_execute_query(Mock(), query="SELECT 1")

        assert result["success"] is False
        assert result["error_type"] == "access_denied"
        assert result["table"] is None
        assert "this table" in result["error"]

    def test_list_tables_access_denied_is_graceful(self):
        """list_tables also returns access_denied, not a generic api_error."""
        with patch("code_puppy.tools.bigquery_tools.BigQueryClient") as MockClient:
            mock_client = Mock()
            mock_client.list_tables.side_effect = BigQueryAccessDeniedError(
                "403 Access Denied: Dataset wmt-trans-bi:STORE"
            )
            MockClient.return_value = mock_client

            result = bigquery_list_tables(Mock(), dataset_id="STORE", project_id="wmt-trans-bi")

        assert result["success"] is False
        assert result["error_type"] == "access_denied"
