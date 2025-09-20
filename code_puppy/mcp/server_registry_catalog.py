"""
MCP Server Registry Catalog - Pre-configured MCP servers.
A curated collection of MCP servers that can be easily searched and installed.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class MCPServerRequirements:
    """Comprehensive requirements for an MCP server installation."""

    environment_vars: List[str] = field(
        default_factory=list
    )  # ["GITHUB_TOKEN", "API_KEY"]
    command_line_args: List[Dict[str, Union[str, bool]]] = field(
        default_factory=list
    )  # [{"name": "port", "prompt": "Port number", "default": "3000", "required": False}]
    required_tools: List[str] = field(
        default_factory=list
    )  # ["node", "python", "npm", "npx"]
    package_dependencies: List[str] = field(
        default_factory=list
    )  # ["jupyter", "@modelcontextprotocol/server-discord"]
    system_requirements: List[str] = field(
        default_factory=list
    )  # ["Docker installed", "Git configured"]


@dataclass
class MCPServerTemplate:
    """Template for a pre-configured MCP server."""

    id: str
    name: str
    display_name: str
    description: str
    category: str
    tags: List[str]
    type: str  # "stdio", "http", "sse"
    config: Dict
    author: str = "Community"
    verified: bool = False
    popular: bool = False
    requires: Union[List[str], MCPServerRequirements] = field(
        default_factory=list
    )  # Backward compatible
    example_usage: str = ""

    def get_requirements(self) -> MCPServerRequirements:
        """Get requirements as MCPServerRequirements object."""
        if isinstance(self.requires, list):
            # Backward compatibility - treat as required_tools
            return MCPServerRequirements(required_tools=self.requires)
        return self.requires

    def get_environment_vars(self) -> List[str]:
        """Get list of required environment variables."""
        requirements = self.get_requirements()
        env_vars = requirements.environment_vars.copy()

        # Also check config for env vars (existing logic)
        if "env" in self.config:
            for key, value in self.config["env"].items():
                if isinstance(value, str) and value.startswith("$"):
                    var_name = value[1:]
                    if var_name not in env_vars:
                        env_vars.append(var_name)

        return env_vars

    def get_command_line_args(self) -> List[Dict]:
        """Get list of configurable command line arguments."""
        return self.get_requirements().command_line_args

    def get_required_tools(self) -> List[str]:
        """Get list of required system tools."""
        return self.get_requirements().required_tools

    def get_package_dependencies(self) -> List[str]:
        """Get list of package dependencies."""
        return self.get_requirements().package_dependencies

    def get_system_requirements(self) -> List[str]:
        """Get list of system requirements."""
        return self.get_requirements().system_requirements

    def to_server_config(self, custom_name: Optional[str] = None, **cmd_args) -> Dict:
        """Convert template to server configuration with optional overrides.

        Replaces placeholders in the config with actual values.
        Placeholders are in the format ${ARG_NAME} in args array.
        """
        import copy

        config = {
            "name": custom_name or self.name,
            "type": self.type,
            **copy.deepcopy(self.config),
        }

        # Apply command line argument substitutions
        if cmd_args and "args" in config:
            new_args = []
            for arg in config["args"]:
                # Check if this arg contains a placeholder like ${db_path}
                if isinstance(arg, str) and "${" in arg:
                    # Replace all placeholders in this arg
                    new_arg = arg
                    for key, value in cmd_args.items():
                        placeholder = f"${{{key}}}"
                        if placeholder in new_arg:
                            new_arg = new_arg.replace(placeholder, str(value))
                    new_args.append(new_arg)
                else:
                    new_args.append(arg)
            config["args"] = new_args

        # Also handle environment variable placeholders
        if "env" in config:
            for env_key, env_value in config["env"].items():
                if isinstance(env_value, str) and "${" in env_value:
                    # Replace placeholders in env values
                    for key, value in cmd_args.items():
                        placeholder = f"${{{key}}}"
                        if placeholder in env_value:
                            config["env"][env_key] = env_value.replace(
                                placeholder, str(value)
                            )

        return config


# Pre-configured MCP Server Registry
MCP_SERVER_REGISTRY: List[MCPServerTemplate] = [
    MCPServerTemplate(
        id="serena",
        name="serena",
        display_name="Serena",
        description="Code Generation MCP Tooling",
        tags=["Agentic", "Code", "SDK", "AI"],
        category="Code",
        type="stdio",
        config={
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/oraios/serena",
                "serena",
                "start-mcp-server",
            ],
        },
        verified=True,
        popular=True,
        example_usage="Agentic AI for writing programs",
        requires=["uvx"],
    ),
    # ========== File System & Storage ==========
    MCPServerTemplate(
        id="filesystem",
        name="filesystem",
        display_name="Filesystem Access",
        description="Read and write files in specified directories",
        category="Storage",
        tags=["files", "io", "read", "write", "directory"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=["node", "npm"],
        example_usage="Access and modify files in /tmp directory",
    ),
    MCPServerTemplate(
        id="filesystem-home",
        name="filesystem-home",
        display_name="Home Directory Access",
        description="Read and write files in user's home directory",
        category="Storage",
        tags=["files", "home", "user", "personal"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "~"],
            "timeout": 30,
        },
        verified=True,
        requires=["node", "npm"],
    ),
    # Enhanced server with comprehensive requirements
    MCPServerTemplate(
        id="gdrive",
        name="gdrive",
        display_name="Google Drive",
        description="Access and manage Google Drive files with OAuth2 authentication",
        category="Storage",
        tags=["google", "drive", "cloud", "storage", "sync", "oauth"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gdrive"],
            "env": {
                "GOOGLE_CLIENT_ID": "$GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET": "$GOOGLE_CLIENT_SECRET",
            },
        },
        requires=MCPServerRequirements(
            environment_vars=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
            command_line_args=[
                {
                    "name": "port",
                    "prompt": "OAuth redirect port",
                    "default": "3000",
                    "required": False,
                },
                {
                    "name": "scope",
                    "prompt": "Google Drive API scope",
                    "default": "https://www.googleapis.com/auth/drive.readonly",
                    "required": False,
                },
            ],
            required_tools=["node", "npx", "npm"],
            package_dependencies=["@modelcontextprotocol/server-gdrive"],
            system_requirements=["Internet connection for OAuth"],
        ),
        verified=True,
        popular=True,
        example_usage="List files: 'Show me my Google Drive files'",
    ),
    # Regular server (backward compatible)
    MCPServerTemplate(
        id="filesystem-simple",
        name="filesystem-simple",
        display_name="Simple Filesystem",
        description="Basic filesystem access",
        category="Storage",
        tags=["files", "basic"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
            command_line_args=[
                {
                    "name": "port",
                    "prompt": "OAuth redirect port",
                    "default": "3000",
                    "required": False,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-gdrive"],
        ),
    ),
    # ========== Databases ==========
    MCPServerTemplate(
        id="postgres",
        name="postgres",
        display_name="PostgreSQL Database",
        description="Connect to and query PostgreSQL databases",
        category="Database",
        tags=["database", "sql", "postgres", "postgresql", "query"],
        type="stdio",
        config={
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-postgres",
                "${connection_string}",
            ],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["DATABASE_URL"],
            command_line_args=[
                {
                    "name": "connection_string",
                    "prompt": "PostgreSQL connection string",
                    "default": "postgresql://localhost/mydb",
                    "required": True,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-postgres"],
            system_requirements=["PostgreSQL server running"],
        ),
        example_usage="postgresql://user:password@localhost:5432/dbname",
    ),
    MCPServerTemplate(
        id="sqlite",
        name="sqlite",
        display_name="SQLite Database",
        description="Connect to and query SQLite databases",
        category="Database",
        tags=["database", "sql", "sqlite", "local", "embedded"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "mcp-sqlite", "${db_path}"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            command_line_args=[
                {
                    "name": "db_path",
                    "prompt": "Path to SQLite database file",
                    "default": "./database.db",
                    "required": True,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-sqlite"],
        ),
    ),
    MCPServerTemplate(
        id="mysql",
        name="mysql",
        display_name="MySQL Database",
        description="Connect to and query MySQL databases",
        category="Database",
        tags=["database", "sql", "mysql", "mariadb", "query"],
        type="stdio",
        config={
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-mysql",
                "${connection_string}",
            ],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["MYSQL_URL"],
            command_line_args=[
                {
                    "name": "connection_string",
                    "prompt": "MySQL connection string",
                    "default": "mysql://localhost/mydb",
                    "required": True,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-mysql"],
            system_requirements=["MySQL server running"],
        ),
    ),
    MCPServerTemplate(
        id="mongodb",
        name="mongodb",
        display_name="MongoDB Database",
        description="Connect to and query MongoDB databases",
        category="Database",
        tags=["database", "nosql", "mongodb", "document", "query"],
        type="stdio",
        config={
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-mongodb",
                "${connection_string}",
            ],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["MONGODB_URI"],
            command_line_args=[
                {
                    "name": "connection_string",
                    "prompt": "MongoDB connection string",
                    "default": "mongodb://localhost:27017/mydb",
                    "required": True,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-mongodb"],
            system_requirements=["MongoDB server running"],
        ),
    ),
    # ========== Development Tools ==========
    MCPServerTemplate(
        id="git",
        name="git",
        display_name="Git Repository",
        description="Manage Git repositories and perform version control operations",
        category="Development",
        tags=["git", "version-control", "repository", "commit", "branch"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-git"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx", "git"],
            package_dependencies=["@modelcontextprotocol/server-git"],
            system_requirements=["Git repository initialized"],
        ),
    ),
    MCPServerTemplate(
        id="github",
        name="github",
        display_name="GitHub API",
        description="Access GitHub repositories, issues, PRs, and more",
        category="Development",
        tags=["github", "api", "repository", "issues", "pull-requests"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["GITHUB_TOKEN"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-github"],
            system_requirements=["GitHub account with personal access token"],
        ),
    ),
    MCPServerTemplate(
        id="gitlab",
        name="gitlab",
        display_name="GitLab API",
        description="Access GitLab repositories, issues, and merge requests",
        category="Development",
        tags=["gitlab", "api", "repository", "issues", "merge-requests"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {"GITLAB_TOKEN": "$GITLAB_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["GITLAB_TOKEN"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-gitlab"],
            system_requirements=["GitLab account with personal access token"],
        ),
    ),
    # ========== Web & Browser ==========
    MCPServerTemplate(
        id="puppeteer",
        name="puppeteer",
        display_name="Puppeteer Browser",
        description="Control headless Chrome for web scraping and automation",
        category="Web",
        tags=["browser", "web", "scraping", "automation", "chrome", "puppeteer"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
            "timeout": 60,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            command_line_args=[
                {
                    "name": "headless",
                    "prompt": "Run in headless mode",
                    "default": "true",
                    "required": False,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-puppeteer"],
            system_requirements=["Chrome/Chromium browser"],
        ),
    ),
    MCPServerTemplate(
        id="playwright",
        name="playwright",
        display_name="Playwright Browser",
        description="Cross-browser automation for web testing and scraping",
        category="Web",
        tags=["browser", "web", "testing", "automation", "playwright"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-playwright"],
            "timeout": 60,
        },
        verified=True,
        requires=MCPServerRequirements(
            command_line_args=[
                {
                    "name": "browser",
                    "prompt": "Browser to use",
                    "default": "chromium",
                    "required": False,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-playwright"],
            system_requirements=["Playwright browsers (will be installed)"],
        ),
    ),
    MCPServerTemplate(
        id="fetch",
        name="fetch",
        display_name="Web Fetch",
        description="Fetch and process web pages and APIs",
        category="Web",
        tags=["web", "http", "api", "fetch", "request"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-fetch"],
        ),
    ),
    # ========== Communication ==========
    MCPServerTemplate(
        id="slack",
        name="slack",
        display_name="Slack Integration",
        description="Send messages and interact with Slack workspaces",
        category="Communication",
        tags=["slack", "chat", "messaging", "notification"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": {"SLACK_TOKEN": "$SLACK_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["SLACK_TOKEN"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-slack"],
            system_requirements=["Slack app with bot token"],
        ),
    ),
    MCPServerTemplate(
        id="discord",
        name="discord",
        display_name="Discord Bot",
        description="Interact with Discord servers and channels",
        category="Communication",
        tags=["discord", "chat", "bot", "messaging"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-discord"],
            "env": {"DISCORD_TOKEN": "$DISCORD_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["DISCORD_TOKEN"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-discord"],
            system_requirements=["Discord bot token"],
        ),
    ),
    MCPServerTemplate(
        id="email",
        name="email",
        display_name="Email (SMTP/IMAP)",
        description="Send and receive emails",
        category="Communication",
        tags=["email", "smtp", "imap", "mail"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-email"],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASS"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-email"],
        ),
    ),
    # ========== AI & Machine Learning ==========
    MCPServerTemplate(
        id="openai",
        name="openai",
        display_name="OpenAI API",
        description="Access OpenAI models for text, image, and embedding generation",
        category="AI",
        tags=["ai", "openai", "gpt", "dalle", "embedding"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-openai"],
            "env": {"OPENAI_API_KEY": "$OPENAI_API_KEY"},
            "timeout": 60,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["OPENAI_API_KEY"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-openai"],
        ),
    ),
    MCPServerTemplate(
        id="anthropic",
        name="anthropic",
        display_name="Anthropic Claude API",
        description="Access Anthropic's Claude models",
        category="AI",
        tags=["ai", "anthropic", "claude", "llm"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-anthropic"],
            "env": {"ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY"},
            "timeout": 60,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["ANTHROPIC_API_KEY"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-anthropic"],
        ),
    ),
    # ========== Data Processing ==========
    MCPServerTemplate(
        id="pandas",
        name="pandas",
        display_name="Pandas Data Analysis",
        description="Process and analyze data using Python pandas",
        category="Data",
        tags=["data", "pandas", "python", "analysis", "csv", "dataframe"],
        type="stdio",
        config={
            "command": "python",
            "args": ["-m", "mcp_server_pandas"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            required_tools=["python", "pip"],
            package_dependencies=["pandas", "mcp-server-pandas"],
        ),
    ),
    MCPServerTemplate(
        id="jupyter",
        name="jupyter",
        display_name="Jupyter Notebook",
        description="Execute code in Jupyter notebooks",
        category="Data",
        tags=["jupyter", "notebook", "python", "data-science"],
        type="stdio",
        config={
            "command": "python",
            "args": ["-m", "mcp_server_jupyter"],
            "timeout": 60,
        },
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["python", "pip", "jupyter"],
            package_dependencies=["jupyter", "mcp-server-jupyter"],
        ),
    ),
    # ========== Cloud Services ==========
    MCPServerTemplate(
        id="aws-s3",
        name="aws-s3",
        display_name="AWS S3 Storage",
        description="Manage AWS S3 buckets and objects",
        category="Cloud",
        tags=["aws", "s3", "storage", "cloud", "bucket"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-aws-s3"],
            "env": {
                "AWS_ACCESS_KEY_ID": "$AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY": "$AWS_SECRET_ACCESS_KEY",
            },
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
            command_line_args=[
                {
                    "name": "region",
                    "prompt": "AWS region",
                    "default": "us-east-1",
                    "required": False,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-aws-s3"],
            system_requirements=["AWS account with S3 access"],
        ),
    ),
    MCPServerTemplate(
        id="azure-storage",
        name="azure-storage",
        display_name="Azure Storage",
        description="Manage Azure blob storage",
        category="Cloud",
        tags=["azure", "storage", "cloud", "blob"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-azure-storage"],
            "env": {
                "AZURE_STORAGE_CONNECTION_STRING": "$AZURE_STORAGE_CONNECTION_STRING"
            },
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["AZURE_STORAGE_CONNECTION_STRING"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-azure-storage"],
            system_requirements=["Azure storage account"],
        ),
    ),
    # ========== Security & Authentication ==========
    MCPServerTemplate(
        id="1password",
        name="1password",
        display_name="1Password Vault",
        description="Access 1Password vaults securely",
        category="Security",
        tags=["security", "password", "vault", "1password", "secrets"],
        type="stdio",
        config={"command": "op", "args": ["mcp-server"], "timeout": 30},
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["op"],
            system_requirements=["1Password CLI installed and authenticated"],
        ),
    ),
    MCPServerTemplate(
        id="vault",
        name="vault",
        display_name="HashiCorp Vault",
        description="Manage secrets in HashiCorp Vault",
        category="Security",
        tags=["security", "vault", "secrets", "hashicorp"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-vault"],
            "env": {"VAULT_TOKEN": "$VAULT_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["VAULT_TOKEN", "VAULT_ADDR"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-vault"],
            system_requirements=["HashiCorp Vault server accessible"],
        ),
    ),
    # ========== Documentation & Knowledge ==========
    MCPServerTemplate(
        id="context7",
        name="context7",
        display_name="Context7 Documentation Search",
        description="Search and retrieve documentation from multiple sources with AI-powered context understanding",
        category="Documentation",
        tags=["documentation", "search", "context", "ai", "knowledge", "docs", "cloud"],
        type="http",
        config={
            "url": "https://mcp.context7.com/mcp",
             "headers": {
                "Authorization": "Bearer $CONTEXT7_API_KEY"
             }
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["CONTEXT7_API_KEY"],
        ),
        example_usage="Cloud-based service - no local setup required",
    ),
    MCPServerTemplate(
        id="confluence",
        name="confluence",
        display_name="Confluence Wiki",
        description="Access and manage Confluence pages",
        category="Documentation",
        tags=["wiki", "confluence", "documentation", "atlassian"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-confluence"],
            "env": {"CONFLUENCE_TOKEN": "$CONFLUENCE_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["CONFLUENCE_TOKEN", "CONFLUENCE_BASE_URL"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-confluence"],
            system_requirements=["Confluence API access"],
        ),
    ),
    MCPServerTemplate(
        id="notion",
        name="notion",
        display_name="Notion Workspace",
        description="Access and manage Notion pages and databases",
        category="Documentation",
        tags=["notion", "wiki", "documentation", "database"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-notion"],
            "env": {"NOTION_TOKEN": "$NOTION_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            environment_vars=["NOTION_TOKEN"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-notion"],
            system_requirements=["Notion integration API key"],
        ),
    ),
    # ========== DevOps & Infrastructure ==========
    MCPServerTemplate(
        id="docker",
        name="docker",
        display_name="Docker Management",
        description="Manage Docker containers and images",
        category="DevOps",
        tags=["docker", "container", "devops", "infrastructure"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-docker"],
            "timeout": 30,
        },
        verified=True,
        popular=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx", "docker"],
            package_dependencies=["@modelcontextprotocol/server-docker"],
            system_requirements=["Docker daemon running"],
        ),
    ),
    MCPServerTemplate(
        id="kubernetes",
        name="kubernetes",
        display_name="Kubernetes Cluster",
        description="Manage Kubernetes resources",
        category="DevOps",
        tags=["kubernetes", "k8s", "container", "orchestration"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-kubernetes"],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx", "kubectl"],
            package_dependencies=["@modelcontextprotocol/server-kubernetes"],
            system_requirements=["Kubernetes cluster access (kubeconfig)"],
        ),
    ),
    MCPServerTemplate(
        id="terraform",
        name="terraform",
        display_name="Terraform Infrastructure",
        description="Manage infrastructure as code with Terraform",
        category="DevOps",
        tags=["terraform", "iac", "infrastructure", "devops"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-terraform"],
            "timeout": 60,
        },
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx", "terraform"],
            package_dependencies=["@modelcontextprotocol/server-terraform"],
            system_requirements=["Terraform configuration files"],
        ),
    ),
    # ========== Monitoring & Observability ==========
    MCPServerTemplate(
        id="prometheus",
        name="prometheus",
        display_name="Prometheus Metrics",
        description="Query Prometheus metrics",
        category="Monitoring",
        tags=["monitoring", "metrics", "prometheus", "observability"],
        type="stdio",
        config={
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-prometheus",
                "${prometheus_url}",
            ],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            command_line_args=[
                {
                    "name": "prometheus_url",
                    "prompt": "Prometheus server URL",
                    "default": "http://localhost:9090",
                    "required": True,
                }
            ],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-prometheus"],
            system_requirements=["Prometheus server accessible"],
        ),
    ),
    MCPServerTemplate(
        id="grafana",
        name="grafana",
        display_name="Grafana Dashboards",
        description="Access Grafana dashboards and alerts",
        category="Monitoring",
        tags=["monitoring", "dashboard", "grafana", "visualization"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-grafana"],
            "env": {"GRAFANA_TOKEN": "$GRAFANA_TOKEN"},
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            environment_vars=["GRAFANA_TOKEN", "GRAFANA_URL"],
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-grafana"],
            system_requirements=["Grafana server with API access"],
        ),
    ),
    # ========== Package Management ==========
    MCPServerTemplate(
        id="npm",
        name="npm",
        display_name="NPM Package Manager",
        description="Search and manage NPM packages",
        category="Package Management",
        tags=["npm", "node", "package", "javascript"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-npm"],
            "timeout": 30,
        },
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["node", "npm", "npx"],
            package_dependencies=["@modelcontextprotocol/server-npm"],
        ),
    ),
    MCPServerTemplate(
        id="pypi",
        name="pypi",
        display_name="PyPI Package Manager",
        description="Search and manage Python packages",
        category="Package Management",
        tags=["python", "pip", "pypi", "package"],
        type="stdio",
        config={"command": "python", "args": ["-m", "mcp_server_pypi"], "timeout": 30},
        verified=True,
        requires=MCPServerRequirements(
            required_tools=["python", "pip"], package_dependencies=["mcp-server-pypi"]
        ),
    ),
]


class MCPServerCatalog:
    """Catalog for searching and managing pre-configured MCP servers."""

    def __init__(self):
        self.servers = MCP_SERVER_REGISTRY
        self._build_index()

    def _build_index(self):
        """Build search index for fast lookups."""
        self.by_id = {s.id: s for s in self.servers}
        self.by_category = {}
        for server in self.servers:
            if server.category not in self.by_category:
                self.by_category[server.category] = []
            self.by_category[server.category].append(server)

    def search(self, query: str) -> List[MCPServerTemplate]:
        """
        Search for servers by name, description, or tags.

        Args:
            query: Search query string

        Returns:
            List of matching server templates
        """
        query_lower = query.lower()
        results = []

        for server in self.servers:
            # Check name
            if query_lower in server.name.lower():
                results.append(server)
                continue

            # Check display name
            if query_lower in server.display_name.lower():
                results.append(server)
                continue

            # Check description
            if query_lower in server.description.lower():
                results.append(server)
                continue

            # Check tags
            for tag in server.tags:
                if query_lower in tag.lower():
                    results.append(server)
                    break

            # Check category
            if query_lower in server.category.lower() and server not in results:
                results.append(server)

        # Sort by relevance (name matches first, then popular)
        results.sort(
            key=lambda s: (
                not s.name.lower().startswith(query_lower),
                not s.popular,
                s.name,
            )
        )

        return results

    def get_by_id(self, server_id: str) -> Optional[MCPServerTemplate]:
        """Get server template by ID."""
        return self.by_id.get(server_id)

    def get_by_category(self, category: str) -> List[MCPServerTemplate]:
        """Get all servers in a category."""
        return self.by_category.get(category, [])

    def list_categories(self) -> List[str]:
        """List all available categories."""
        return sorted(self.by_category.keys())

    def get_popular(self, limit: int = 10) -> List[MCPServerTemplate]:
        """Get popular servers."""
        popular = [s for s in self.servers if s.popular]
        return popular[:limit]

    def get_verified(self) -> List[MCPServerTemplate]:
        """Get all verified servers."""
        return [s for s in self.servers if s.verified]


# Global catalog instance
catalog = MCPServerCatalog()
