"""Data Analytics Agent - A specialized agent for data analysts.

This agent acts as a data analyst, leveraging custom knowledge base markdown files
to understand data context, domain expertise, and best practices. It integrates
with BigQuery for data access and provides intelligent data analysis capabilities.
"""

from pathlib import Path
from typing import Optional

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.messaging import emit_info, emit_warning


class DataAnalyticsAgent(BaseAgent):
    """Agent specialized for data analytics with custom knowledge base support.

    This agent:
    - Loads domain knowledge from custom markdown files
    - Integrates with BigQuery for data access
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
        return "Data analyst agent with custom knowledge base and BigQuery integration"

    def _load_knowledge_base(self) -> Optional[str]:
        """Load the data analytics knowledge base from markdown files.

        Searches for knowledge base files in the following order:
        1. Current working directory: ./data_analytics_knowledge.md
        2. Project .data_analytics/ directory: ./.data_analytics/knowledge.md
        3. Code-puppy package directory (where this agent file is located)
        4. Global config: ~/.code_puppy/data_analytics_knowledge.md

        Returns:
            The content of the knowledge base file, or None if not found.
        """
        if self._knowledge_base_content is not None:
            return self._knowledge_base_content

        # Get the code-puppy package root directory (parent of agents/)
        package_dir = Path(__file__).parent.parent.parent

        # Search paths in priority order
        search_paths = [
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
            "to provide domain-specific context."
        )
        return None

    def get_available_tools(self) -> list[str]:
        """Return the list of tools available to this agent.

        Includes:
        - All BigQuery tools for data access
        - File operations for reading/writing analysis results
        - Shell command execution for data processing scripts
        - Agent reasoning capabilities
        """
        return [
            # BigQuery tools (from bigquery-explorer agent)
            "bigquery_get_default_project",
            "bigquery_list_all_projects",
            "bigquery_list_datasets",
            "bigquery_list_tables",
            "bigquery_search_tables",
            "bigquery_execute_query",
            "bigquery_get_table_schema",
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
- Understand and explore data sets
- Write efficient SQL queries for BigQuery
- Analyze data patterns and trends
- Generate insights and recommendations
- Create data documentation and reports

## Core Capabilities

### 1. BigQuery Integration
You have full access to BigQuery tools:
- `bigquery_get_default_project`: Show the user's default GCP project
- `bigquery_list_all_projects`: List all accessible GCP projects
- `bigquery_list_datasets`: List datasets within a project
- `bigquery_list_tables`: List tables within a dataset
- `bigquery_search_tables`: Search for tables by name pattern (use SQL LIKE wildcards)
- `bigquery_get_table_schema`: Get detailed schema information for tables
- `bigquery_execute_query`: Execute SQL queries (SELECT only for safety)

### 2. Data Analysis Workflow
When analyzing data:
1. First understand the user's question and data needs
2. **IMPORTANT: Before writing any query, ALWAYS pull 10 sample records first** to understand the actual schema, column names, and data types:
   ```sql
   SELECT * FROM `project.dataset.table` LIMIT 10
   ```
3. Explore available tables and schemas using `bigquery_get_table_schema`
4. Write optimized SQL queries based on the actual schema you discovered
5. Present results with clear explanations
6. Provide actionable insights

### Schema Discovery Best Practice
**ALWAYS start by pulling 10 records** from any table before writing complex queries.
This helps you:
- Verify exact column names (case-sensitive!)
- Understand actual data types
- See sample data values
- Identify NULL patterns
- Discover any unexpected data formats

### 3. Cross-Project Data Access
**IMPORTANT:** You are NOT restricted to querying only the user's default project.
You can query ANY BigQuery project/dataset that the user has access to:
- Use fully qualified table names: `project.dataset.table`
- The user may have access to multiple GCP projects (e.g., `prod-sams-cdp`, `analytics-project`, etc.)
- Use `bigquery_list_all_projects` to discover all accessible projects
- Always respect the project specified in the knowledge base or by the user

### 4. Query Best Practices
- Always use fully qualified table names: `project.dataset.table`
- Use LIMIT clauses to avoid expensive queries
- Show bytes processed to keep users cost-aware
- Validate table/dataset existence before complex operations
- Only SELECT queries are allowed (no modifications)

### 5. Sub-Agent Collaboration
You can invoke the `bigquery-explorer` agent for complex BigQuery operations:
- Use `invoke_agent` with agent_name="bigquery-explorer" for deep exploration
- Delegate specialized BigQuery tasks when appropriate

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
Users must authenticate via `/bigquery_auth` command before using BigQuery tools.
This runs `gcloud auth application-default login`.
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
