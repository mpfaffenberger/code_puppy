"""Data Analytics Agent - A specialized agent for data analysts.

This agent acts as a data analyst, leveraging custom knowledge base markdown files
to understand data context, domain expertise, and best practices. It integrates
with BigQuery and Databricks for data access and provides intelligent data analysis
capabilities across multiple data platforms.
"""

from pathlib import Path
from typing import Optional

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.config import get_value, set_config_value
from code_puppy.messaging import emit_info, emit_warning

# Config key for custom knowledge base path
KNOWLEDGE_BASE_PATH_CONFIG_KEY = "data_analytics_knowledge_path"


class DataAnalyticsAgent(BaseAgent):
    """Agent specialized for data analytics with custom knowledge base support.

    This agent:
    - Loads domain knowledge from custom markdown files
    - Integrates with BigQuery (Google Cloud) for data access
    - Integrates with Databricks (Unity Catalog) for data access
    - Provides data analysis, insights, and recommendations
    - Helps data analysts with queries, visualizations, and reporting
    """

    # Default knowledge base file name
    KNOWLEDGE_BASE_FILENAME = "data_analytics_knowledge.md"

    def __init__(self):
        super().__init__()
        self._knowledge_base_content: Optional[str] = None

    @property
    def name(self) -> str:
        return "data-analytics"

    @property
    def display_name(self) -> str:
        return "Data Analytics Agent 📊"

    @property
    def description(self) -> str:
        return "Data analyst agent with custom knowledge base, BigQuery and Databricks integration"

    @staticmethod
    def get_configured_knowledge_path() -> Optional[str]:
        """Get the user-configured knowledge base path from config.

        Returns:
            The configured path string, or None if not set.
        """
        return get_value(KNOWLEDGE_BASE_PATH_CONFIG_KEY)

    @staticmethod
    def set_knowledge_base_path(path: str) -> bool:
        """Set a custom knowledge base file path.

        Args:
            path: Absolute or relative path to the knowledge base markdown file.

        Returns:
            True if the path was set successfully, False if the file doesn't exist.
        """
        # Expand user home directory (~) and resolve to absolute path
        resolved_path = Path(path).expanduser().resolve()

        if not resolved_path.exists():
            emit_warning(f"Knowledge base file not found: {resolved_path}")
            return False

        if not resolved_path.is_file():
            emit_warning(f"Path is not a file: {resolved_path}")
            return False

        # Save the resolved absolute path to config
        set_config_value(KNOWLEDGE_BASE_PATH_CONFIG_KEY, str(resolved_path))
        emit_info(f"Knowledge base path configured: {resolved_path}")
        return True

    @staticmethod
    def clear_knowledge_base_path() -> None:
        """Clear the custom knowledge base path configuration."""
        set_config_value(KNOWLEDGE_BASE_PATH_CONFIG_KEY, "")
        emit_info(
            "Knowledge base path configuration cleared. Using default search paths."
        )

    def _load_knowledge_base(self) -> Optional[str]:
        """Load the data analytics knowledge base from markdown files.

        Searches for knowledge base files in the following order:
        1. User-configured path (via set_knowledge_base_path or /set command)
        2. Current working directory: ./data_analytics_knowledge.md
        3. Project .data_analytics/ directory: ./.data_analytics/knowledge.md
        4. Code-puppy package directory (where this agent file is located)
        5. Global config: ~/.code_puppy/data_analytics_knowledge.md

        Returns:
            The content of the knowledge base file, or None if not found.
        """
        if self._knowledge_base_content is not None:
            return self._knowledge_base_content

        # Get the code-puppy package root directory (parent of agents/)
        package_dir = Path(__file__).parent.parent.parent

        # Build search paths - start with configured path if set
        search_paths = []

        # 1. Check for user-configured custom path first (highest priority)
        configured_path = self.get_configured_knowledge_path()
        if configured_path and configured_path.strip():
            search_paths.append(Path(configured_path).expanduser().resolve())

        # 2. Add default search paths
        search_paths.extend(
            [
                # Current directory (where user runs code-puppy from)
                Path.cwd() / self.KNOWLEDGE_BASE_FILENAME,
                Path.cwd() / "data_analytics_knowledge.md",
                # Project-specific directory
                Path.cwd() / ".data_analytics" / "knowledge.md",
                Path.cwd() / ".data_analytics" / "data_knowledge.md",
                # Hidden file in current directory
                Path.cwd() / ".data_analytics_knowledge.md",
                # Code-puppy package directory (where the repo/package is installed)
                package_dir / self.KNOWLEDGE_BASE_FILENAME,
                package_dir / "data_analytics_knowledge.md",
                # Global config directory
                Path.home() / ".code_puppy" / self.KNOWLEDGE_BASE_FILENAME,
                Path.home() / ".code_puppy" / "data_analytics" / "knowledge.md",
            ]
        )

        for path in search_paths:
            if path.exists() and path.is_file():
                try:
                    content = path.read_text(encoding="utf-8-sig")
                    self._knowledge_base_content = content
                    emit_info(f"Loaded data analytics knowledge base from: {path}")
                    return content
                except Exception as e:
                    emit_warning(f"Failed to read knowledge base from {path}: {e}")
                    continue

        # No knowledge base found - return None (agent will work without it)
        emit_warning(
            "No data analytics knowledge base found. "
            f"Create '{self.KNOWLEDGE_BASE_FILENAME}' in your project directory "
            f"or use '/set {KNOWLEDGE_BASE_PATH_CONFIG_KEY} /path/to/file.md' to configure."
        )
        return None

    def get_available_tools(self) -> list[str]:
        """Return the list of tools available to this agent.

        Includes:
        - All BigQuery tools for Google Cloud data access
        - All Databricks tools for Unity Catalog, notebooks, and code execution
        - Confluence search for documentation and knowledge base
        - PowerBI integration for visualization and dashboards
        - File operations for reading/writing analysis results
        - Shell command execution for data processing scripts
        - Agent reasoning capabilities and sub-agent delegation
        """
        return [
            # BigQuery tools (Google Cloud)
            "bigquery_get_default_project",
            "bigquery_list_all_projects",
            "bigquery_list_datasets",
            "bigquery_list_tables",
            "bigquery_search_tables",
            "bigquery_execute_query",
            "bigquery_get_table_schema",
            # Databricks tools (Unity Catalog - SQL/Query)
            "databricks_list_catalogs",
            "databricks_list_schemas",
            "databricks_list_tables",
            "databricks_get_table_schema",
            "databricks_list_warehouses",
            "databricks_execute_query",
            # Databricks workspace operations (read/write/execute)
            "databricks_list_workspace",
            "databricks_get_notebook",
            "databricks_upload_notebook",
            "databricks_run_notebook",
            "databricks_execute_code",
            # Confluence tools (documentation & knowledge base)
            "confluence_search",
            "confluence_read_page",
            "confluence_search_by_space",
            # File operations
            "list_files",
            "read_file",
            "grep",
            "edit_file",
            "delete_file",
            # Shell execution for data processing
            "agent_run_shell_command",
            # Agent capabilities
            "agent_share_your_reasoning",
            "list_agents",
            "invoke_agent",
        ]

    def get_system_prompt(self) -> str:
        """Generate the system prompt including any loaded knowledge base."""
        # Load knowledge base content
        knowledge_base = self._load_knowledge_base()

        # Build the system prompt
        base_prompt = """
You are the Data Analytics Agent - a specialized AI assistant for data analysts.

## Your Role
You act as an expert data analyst, helping users:
- Understand and explore data sets across multiple platforms
- Write efficient SQL queries for BigQuery and Databricks
- Analyze data patterns and trends
- Generate insights and recommendations
- Create data documentation and reports

## Core Capabilities

### 1. BigQuery Integration (Google Cloud)
You have full access to BigQuery tools:
- `bigquery_get_default_project`: Show the user's default GCP project
- `bigquery_list_all_projects`: List all accessible GCP projects
- `bigquery_list_datasets`: List datasets within a project
- `bigquery_list_tables`: List tables within a dataset
- `bigquery_search_tables`: Search for tables by name pattern (use SQL LIKE wildcards)
- `bigquery_get_table_schema`: Get detailed schema information for tables
- `bigquery_execute_query`: Execute SQL queries (SELECT only for safety)

### 2. Databricks Integration (Unity Catalog & Workspace)
You have full access to Databricks SQL and workspace tools:

**SQL & Query Tools:**
- `databricks_list_catalogs`: List all accessible catalogs in the workspace
- `databricks_list_schemas`: List schemas within a catalog
- `databricks_list_tables`: List tables within a schema
- `databricks_get_table_schema`: Get detailed schema for a specific table
- `databricks_list_warehouses`: List available SQL warehouses
- `databricks_execute_query`: Execute SQL queries (SELECT only for safety)

**Workspace & Notebook Tools:**
- `databricks_list_workspace`: Browse workspace directories and find analysis notebooks
- `databricks_get_notebook`: Read existing notebooks to understand analyses
- `databricks_upload_notebook`: Upload or update analysis notebooks
- `databricks_run_notebook`: Execute notebooks to run PySpark analyses
- `databricks_execute_code`: Execute PySpark/SQL code directly on clusters

#### Databricks Namespace Structure
Databricks uses Unity Catalog with a three-level namespace:
- **Catalog**: Top-level container (e.g., 'main', 'hive_metastore')
- **Schema**: Database within a catalog (e.g., 'default', 'analytics')
- **Table**: Actual data table

Fully qualified table name: `catalog.schema.table`

#### For Advanced Databricks Tasks
For job creation, pipeline management, or advanced cluster operations:
- Use `invoke_agent` with agent_name="databricks" to delegate
- Example: `invoke_agent databricks` to access job management and DLT pipelines

### 3. Confluence Integration (Documentation & Knowledge Base)
You have access to Confluence search and documentation tools:
- `confluence_search`: Search across Confluence for analysis documentation and references
- `confluence_read_page`: Read Confluence pages for detailed documentation and context
- `confluence_search_by_space`: Search within specific Confluence spaces for relevant docs

Use Confluence to:
- Find data dictionaries and table descriptions
- Reference previous analyses and reports
- Access business context and definitions
- Discover best practices and standards

### 4. PowerBI Integration (Dashboards & Visualizations)
For creating and managing Power BI dashboards:
- Use `invoke_agent` with agent_name="powerbi" to delegate
- The Power BI agent can help you:
  - Create interactive dashboards from your analysis
  - Connect to data sources
  - Build visualizations and reports
  - Share dashboards with stakeholders

### 5. Data Analysis Workflow
When analyzing data:
1. First understand the user's question and data needs
2. **DETERMINE THE PLATFORM**: Check if the user is asking about:
   - BigQuery data: Use `bigquery_*` tools (table format: `project.dataset.table`)
   - Databricks data: Use `databricks_*` tools (table format: `catalog.schema.table`)
3. **SEARCH FOR CONTEXT**: Use Confluence to find:
   - Data dictionaries and field definitions
   - Previous analyses on similar topics
   - Business definitions and metrics
4. **IMPORTANT: Before writing any query, ALWAYS pull 10 sample records first** to understand the actual schema:
   - BigQuery: SELECT * FROM `project.dataset.table` LIMIT 10
   - Databricks: SELECT * FROM catalog.schema.table LIMIT 10
5. Explore available tables and schemas using the appropriate `*_get_table_schema` tool
6. Write optimized SQL queries based on the actual schema you discovered
7. Consider running analysis in Databricks notebooks if complex transformations needed
8. Present results with clear explanations
9. Provide actionable insights
10. For dashboard creation, delegate to Power BI agent: `invoke_agent powerbi`

### 6. Schema Discovery Best Practice
**ALWAYS start by pulling 10 records** from any table before writing complex queries.
This helps you:
- Verify exact column names (case-sensitive!)
- Understand actual data types
- See sample data values
- Identify NULL patterns
- Discover any unexpected data formats

### 7. Cross-Platform and Cross-Project Data Access
**IMPORTANT:** You can access data from BOTH platforms:
- **BigQuery**: Use fully qualified table names: `project.dataset.table`
  - Use `bigquery_list_all_projects` to discover all accessible GCP projects
- **Databricks**: Use fully qualified table names: `catalog.schema.table`
  - Use `databricks_list_catalogs` to discover all accessible catalogs

### 8. Query Best Practices
- Always use fully qualified table names
- Use LIMIT clauses to avoid expensive queries
- BigQuery: Show bytes processed to keep users cost-aware
- Databricks: Be mindful of warehouse compute usage
- Validate table/dataset existence before complex operations
- Only SELECT queries are allowed for direct execution (no modifications)

### 9. Sub-Agent Delegation
You can delegate to specialized agents for complex operations:

**Data Exploration:**
- `invoke_agent bigquery-explorer` for deep BigQuery exploration
- `invoke_agent databricks` for advanced Databricks operations (jobs, pipelines, clusters)

**Knowledge & Documentation:**
- Confluence tools are available directly for documentation searches

**Visualization & Reporting:**
- `invoke_agent powerbi` for creating interactive dashboards and visualizations

## Query Results Format
- Queries return 5 preview rows to minimize token usage
- Results are saved to CSV by default
- For final results, always show:
  1. Preview rows as a markdown table
  2. The full file path for complete data access

## File Operations
You can:
- Read data files (CSV, JSON, etc.) from the local filesystem
- Write analysis results and reports
- Search through project files for relevant data documentation

## Safety Restrictions
- Only SELECT queries are allowed
- No destructive operations (DELETE, DROP, TRUNCATE)
- No modification operations (INSERT, UPDATE, MERGE)
- No schema changes (ALTER, CREATE, REPLACE)

## Authentication
- **BigQuery**: Users must authenticate via `/bigquery_auth` command (runs `gcloud auth application-default login`)
- **Databricks**: Users must authenticate via `/databricks_auth` command (OAuth browser-based login)
"""

        # Add knowledge base section if available
        if knowledge_base:
            knowledge_section = f"""

## Domain Knowledge Base

The following is your specialized knowledge base containing domain-specific
information about the data, business context, and analysis guidelines.
USE THIS KNOWLEDGE to provide contextually relevant analysis and insights.

---
{knowledge_base}
---

When answering questions:
1. Reference the knowledge base for domain context
2. Apply the guidelines and best practices defined above
3. Use the correct table names, field definitions, and business logic
4. Follow any naming conventions or data quality rules specified
"""
            base_prompt += knowledge_section
        else:
            no_knowledge_section = """

## Domain Knowledge Base

No knowledge base file was found. To enable domain-specific context:

1. Create a file named `data_analytics_knowledge.md` in your project directory
2. Or create `.data_analytics/knowledge.md` for project-specific knowledge
3. Or create `~/.code_puppy/data_analytics_knowledge.md` for global knowledge

The knowledge base should include:
- Data dictionary and table descriptions
- Business definitions and metrics
- Common query patterns
- Data quality rules
- Domain-specific terminology
"""
            base_prompt += no_knowledge_section

        closing_prompt = """

## Interaction Style
- Be precise and data-driven in your responses
- Explain your analysis approach and reasoning
- Provide SQL queries that are well-formatted and commented
- Offer insights beyond just raw data
- Suggest follow-up analyses when relevant

Be helpful, efficient, and always consider data accuracy and query costs.
"""
        return base_prompt + closing_prompt

    def reload_knowledge_base(self) -> bool:
        """Force reload the knowledge base from disk.

        Returns:
            True if knowledge base was loaded, False otherwise.
        """
        self._knowledge_base_content = None
        content = self._load_knowledge_base()
        return content is not None
