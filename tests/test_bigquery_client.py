"""Unit tests for BigQueryClient."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.plugins.walmart_specific.bigquery_client import (
    BigQueryClient,
    BigQueryError,
    BigQueryAuthError,
    BigQueryAPIError,
    BigQueryNotFoundError,
)


@pytest.fixture
def mock_bigquery_module():
    """Mock the google.cloud.bigquery module."""
    with patch(
        "code_puppy.plugins.walmart_specific.bigquery_client.bigquery"
    ) as mock_bq:
        mock_client = Mock()
        mock_client.project = "test-project-123"
        mock_bq.Client.return_value = mock_client
        yield mock_bq


@pytest.fixture
def mock_sqlparse():
    """Mock the sqlparse module."""
    with patch(
        "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse"
    ) as mock_sp:
        yield mock_sp


@pytest.fixture
def bigquery_client(mock_bigquery_module):
    """Create a BigQueryClient instance with mocked BigQuery."""
    return BigQueryClient()


class TestBigQueryClientInitialization:
    """Test suite for BigQueryClient initialization."""

    def test_init_success(self, mock_bigquery_module):
        """Test successful BigQueryClient initialization."""
        client = BigQueryClient()

        assert client.project_id == "test-project-123"
        mock_bigquery_module.Client.assert_called_once_with(project=None)

    def test_init_with_project_id(self, mock_bigquery_module):
        """Test initialization with specific project ID."""
        client = BigQueryClient(project_id="my-custom-project")

        assert client.project_id == "test-project-123"
        mock_bigquery_module.Client.assert_called_once_with(project="my-custom-project")

    def test_init_no_bigquery_library(self):
        """Test initialization when bigquery library is not installed."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.bigquery", None
        ):
            with pytest.raises(
                BigQueryAuthError, match="google-cloud-bigquery is not installed"
            ):
                BigQueryClient()

    def test_init_no_credentials(self, mock_bigquery_module):
        """Test initialization without valid credentials."""
        from google.auth.exceptions import DefaultCredentialsError

        mock_bigquery_module.Client.side_effect = DefaultCredentialsError(
            "No credentials found"
        )

        with pytest.raises(BigQueryAuthError, match="No valid credentials found"):
            BigQueryClient()

    def test_init_generic_error(self, mock_bigquery_module):
        """Test initialization with generic error."""
        mock_bigquery_module.Client.side_effect = Exception("Some error")

        with pytest.raises(
            BigQueryAuthError, match="Failed to initialize BigQuery client"
        ):
            BigQueryClient()


class TestBigQueryClientListProjects:
    """Test suite for list_projects method."""

    def test_list_projects(self, bigquery_client):
        """Test listing the default project."""
        projects = bigquery_client.list_projects()

        assert len(projects) == 1
        assert projects[0]["project_id"] == "test-project-123"
        assert projects[0]["state"] == "ACTIVE"
        assert "default project" in projects[0]["note"].lower()


class TestBigQueryClientListAllProjects:
    """Test suite for list_all_projects method."""

    def test_list_all_projects_success(self, bigquery_client):
        """Test successfully listing all projects via gcloud."""
        mock_projects = [
            {
                "projectId": "project-1",
                "name": "Project One",
                "projectNumber": "123456",
                "lifecycleState": "ACTIVE",
            },
            {
                "projectId": "project-2",
                "name": "Project Two",
                "projectNumber": "789012",
                "lifecycleState": "ACTIVE",
            },
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout=str(mock_projects).replace("'", '"')
            )

            projects = bigquery_client.list_all_projects()

            assert len(projects) == 2
            assert projects[0]["project_id"] == "project-1"
            assert projects[1]["project_id"] == "project-2"

    def test_list_all_projects_gcloud_error(self, bigquery_client):
        """Test list_all_projects when gcloud fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1, stderr="gcloud auth required", stdout=""
            )

            with pytest.raises(BigQueryAPIError, match="Failed to list projects"):
                bigquery_client.list_all_projects()

    def test_list_all_projects_gcloud_not_installed(self, bigquery_client):
        """Test list_all_projects when gcloud is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(BigQueryAPIError, match="gcloud CLI is not installed"):
                bigquery_client.list_all_projects()

    def test_list_all_projects_timeout(self, bigquery_client):
        """Test list_all_projects timeout."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            with pytest.raises(
                BigQueryAPIError, match="Timeout while listing projects"
            ):
                bigquery_client.list_all_projects()


class TestBigQueryClientListDatasets:
    """Test suite for list_datasets method."""

    def test_list_datasets_success(self, bigquery_client):
        """Test successfully listing datasets."""
        mock_dataset = Mock()
        mock_dataset.dataset_id = "my_dataset"
        mock_dataset.project = "test-project-123"

        bigquery_client._client.list_datasets = Mock(return_value=[mock_dataset])

        datasets = bigquery_client.list_datasets()

        assert len(datasets) == 1
        assert datasets[0]["dataset_id"] == "my_dataset"
        assert datasets[0]["project"] == "test-project-123"
        assert datasets[0]["full_id"] == "test-project-123.my_dataset"

    def test_list_datasets_with_project_id(self, bigquery_client):
        """Test listing datasets in a specific project."""
        mock_dataset = Mock()
        mock_dataset.dataset_id = "dataset1"
        mock_dataset.project = "other-project"

        bigquery_client._client.list_datasets = Mock(return_value=[mock_dataset])

        datasets = bigquery_client.list_datasets(project_id="other-project")

        assert len(datasets) == 1
        bigquery_client._client.list_datasets.assert_called_once_with(
            project="other-project"
        )

    def test_list_datasets_error(self, bigquery_client):
        """Test list_datasets with error."""
        bigquery_client._client.list_datasets = Mock(side_effect=Exception("API error"))

        with pytest.raises(BigQueryAPIError, match="Failed to list datasets"):
            bigquery_client.list_datasets()


class TestBigQueryClientListTables:
    """Test suite for list_tables method."""

    def test_list_tables_success(self, bigquery_client):
        """Test successfully listing tables."""
        mock_table = Mock()
        mock_table.table_id = "users"
        mock_table.table_type = "TABLE"
        mock_table.project = "test-project-123"
        mock_table.dataset_id = "my_dataset"

        bigquery_client._client.list_tables = Mock(return_value=[mock_table])

        tables = bigquery_client.list_tables(dataset_id="my_dataset")

        assert len(tables) == 1
        assert tables[0]["table_id"] == "users"
        assert tables[0]["table_type"] == "TABLE"
        assert tables[0]["full_id"] == "test-project-123.my_dataset.users"

    def test_list_tables_dataset_not_found(self, bigquery_client):
        """Test list_tables when dataset doesn't exist."""
        bigquery_client._client.list_tables = Mock(
            side_effect=Exception("Dataset not found")
        )

        with pytest.raises(BigQueryNotFoundError, match="Dataset.*not found"):
            bigquery_client.list_tables(dataset_id="nonexistent")


class TestBigQueryClientSQLValidation:
    """Test suite for SQL query validation."""

    def test_is_safe_query_select(self, bigquery_client, mock_sqlparse):
        """Test that SELECT queries are allowed."""
        mock_statement = Mock()
        mock_statement.get_type.return_value = "SELECT"
        mock_statement.flatten.return_value = []
        mock_sqlparse.parse.return_value = [mock_statement]

        result = bigquery_client._is_safe_query("SELECT * FROM table")

        assert result is True

    def test_is_safe_query_with_clause(self, bigquery_client, mock_sqlparse):
        """Test that WITH (CTE) queries are allowed."""
        mock_statement = Mock()
        mock_statement.get_type.return_value = "WITH"
        mock_statement.flatten.return_value = []
        mock_sqlparse.parse.return_value = [mock_statement]

        result = bigquery_client._is_safe_query(
            "WITH cte AS (SELECT * FROM table) SELECT * FROM cte"
        )

        assert result is True

    def test_is_safe_query_delete(self, bigquery_client, mock_sqlparse):
        """Test that DELETE queries are blocked."""
        mock_statement = Mock()
        mock_statement.get_type.return_value = "DELETE"
        mock_sqlparse.parse.return_value = [mock_statement]

        result = bigquery_client._is_safe_query("DELETE FROM table")

        assert result is False

    def test_is_safe_query_drop(self, bigquery_client, mock_sqlparse):
        """Test that DROP queries are blocked."""
        mock_statement = Mock()
        mock_statement.get_type.return_value = "DROP"
        mock_sqlparse.parse.return_value = [mock_statement]

        result = bigquery_client._is_safe_query("DROP TABLE table")

        assert result is False

    def test_is_safe_query_dangerous_keyword_in_token(
        self, bigquery_client, mock_sqlparse
    ):
        """Test detection of dangerous keywords in tokens."""
        import sqlparse as sp

        mock_token = Mock()
        mock_token.ttype = sp.tokens.Keyword.DML
        mock_token.value = "DELETE"

        mock_statement = Mock()
        mock_statement.get_type.return_value = "UNKNOWN"
        mock_statement.flatten.return_value = [mock_token]
        mock_sqlparse.parse.return_value = [mock_statement]
        mock_sqlparse.tokens = sp.tokens

        result = bigquery_client._is_safe_query("SELECT * FROM table")

        assert result is False

    def test_is_safe_query_no_sqlparse(self, bigquery_client):
        """Test query validation when sqlparse is not available."""
        with patch(
            "code_puppy.plugins.walmart_specific.bigquery_client.sqlparse", None
        ):
            result = bigquery_client._is_safe_query("SELECT * FROM table")

            # Should return False (reject) when sqlparse unavailable
            assert result is False

    def test_is_safe_query_parse_error(self, bigquery_client, mock_sqlparse):
        """Test query validation when parsing fails."""
        mock_sqlparse.parse.side_effect = Exception("Parse error")

        result = bigquery_client._is_safe_query("INVALID SQL")

        # Should return False on parse error
        assert result is False

    def test_validate_query_safety_empty_query(self, bigquery_client):
        """Test that empty queries are rejected."""
        with pytest.raises(BigQueryAPIError, match="Query cannot be empty"):
            bigquery_client._validate_query_safety("   ")

    def test_validate_query_safety_dangerous_query(
        self, bigquery_client, mock_sqlparse
    ):
        """Test validation rejects dangerous queries."""
        mock_statement = Mock()
        mock_statement.get_type.return_value = "DELETE"
        mock_sqlparse.parse.return_value = [mock_statement]

        with pytest.raises(
            BigQueryAPIError, match="Only read-only SELECT queries are allowed"
        ):
            bigquery_client._validate_query_safety("DELETE FROM table")


class TestBigQueryClientExecuteQuery:
    """Test suite for execute_query method."""

    def test_execute_query_success(self, bigquery_client, mock_sqlparse):
        """Test successful query execution."""
        # Mock safe query validation
        mock_statement = Mock()
        mock_statement.get_type.return_value = "SELECT"
        mock_statement.flatten.return_value = []
        mock_sqlparse.parse.return_value = [mock_statement]

        # Mock query results
        mock_row = {"id": 1, "name": "test"}
        mock_field = Mock()
        mock_field.name = "id"
        mock_field.field_type = "INTEGER"
        mock_field.mode = "REQUIRED"

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_result.schema = [mock_field]
        mock_result.total_rows = 1

        mock_query_job = Mock()
        mock_query_job.result.return_value = mock_result
        mock_query_job.job_id = "job-123"
        mock_query_job.total_bytes_processed = 1024
        mock_query_job.total_bytes_billed = 2048

        bigquery_client._client.query.return_value = mock_query_job

        result = bigquery_client.execute_query("SELECT * FROM table")

        assert result["total_rows"] == 1
        assert len(result["rows"]) == 1
        assert result["rows"][0]["id"] == 1
        assert result["job_id"] == "job-123"

    def test_execute_query_max_results_exceeded(self, bigquery_client):
        """Test query with max_results exceeding limit."""
        with pytest.raises(BigQueryAPIError, match="max_results too large"):
            bigquery_client.execute_query("SELECT 1", max_results=20000)

    def test_execute_query_negative_max_results(self, bigquery_client):
        """Test query with negative max_results."""
        with pytest.raises(BigQueryAPIError, match="max_results must be positive"):
            bigquery_client.execute_query("SELECT 1", max_results=-1)


class TestBigQueryClientGetTableSchema:
    """Test suite for get_table_schema method."""

    def test_get_table_schema_success(self, bigquery_client):
        """Test successfully getting table schema."""
        mock_field1 = Mock()
        mock_field1.name = "id"
        mock_field1.field_type = "INTEGER"
        mock_field1.mode = "REQUIRED"
        mock_field1.description = "Primary key"

        mock_field2 = Mock()
        mock_field2.name = "name"
        mock_field2.field_type = "STRING"
        mock_field2.mode = "NULLABLE"
        mock_field2.description = "User name"

        mock_table = Mock()
        mock_table.schema = [mock_field1, mock_field2]

        bigquery_client._client.get_table = Mock(return_value=mock_table)

        schema = bigquery_client.get_table_schema(
            table_id="users", dataset_id="my_dataset"
        )

        assert len(schema) == 2
        assert schema[0]["name"] == "id"
        assert schema[0]["type"] == "INTEGER"
        assert schema[1]["name"] == "name"
        assert schema[1]["type"] == "STRING"

    def test_get_table_schema_table_not_found(self, bigquery_client):
        """Test get_table_schema when table doesn't exist."""
        bigquery_client._client.get_table = Mock(
            side_effect=Exception("Table not found")
        )

        with pytest.raises(BigQueryNotFoundError, match="Table.*not found"):
            bigquery_client.get_table_schema(
                table_id="nonexistent", dataset_id="my_dataset"
            )


class TestBigQueryExceptions:
    """Test suite for BigQuery exception hierarchy."""

    def test_bigquery_error_base(self):
        """Test BigQueryError base exception."""
        error = BigQueryError("Base error")
        assert str(error) == "Base error"
        assert isinstance(error, Exception)

    def test_bigquery_auth_error(self):
        """Test BigQueryAuthError exception."""
        error = BigQueryAuthError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, BigQueryError)

    def test_bigquery_api_error(self):
        """Test BigQueryAPIError exception."""
        error = BigQueryAPIError("API call failed")
        assert str(error) == "API call failed"
        assert isinstance(error, BigQueryError)

    def test_bigquery_not_found_error(self):
        """Test BigQueryNotFoundError exception."""
        error = BigQueryNotFoundError("Resource not found")
        assert str(error) == "Resource not found"
        assert isinstance(error, BigQueryError)
