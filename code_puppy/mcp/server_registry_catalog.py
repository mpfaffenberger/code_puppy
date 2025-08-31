"""
MCP Server Registry Catalog - Pre-configured MCP servers.
A curated collection of MCP servers that can be easily searched and installed.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field

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
    requires: List[str] = field(default_factory=list)  # Required tools/dependencies
    example_usage: str = ""
    
    def to_server_config(self, custom_name: Optional[str] = None) -> Dict:
        """Convert template to server configuration."""
        config = {
            "name": custom_name or self.name,
            "type": self.type,
            **self.config
        }
        return config


# Pre-configured MCP Server Registry
MCP_SERVER_REGISTRY: List[MCPServerTemplate] = [
    
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm"],
        example_usage="Access and modify files in /tmp directory"
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm"]
    ),
    
    MCPServerTemplate(
        id="gdrive",
        name="gdrive",
        display_name="Google Drive",
        description="Access and manage Google Drive files",
        category="Storage",
        tags=["google", "drive", "cloud", "storage", "sync"],
        type="stdio",
        config={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gdrive"],
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "google-auth"]
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
            "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "postgresql"],
        example_usage="postgresql://user:password@localhost:5432/dbname"
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
            "args": ["-y", "@modelcontextprotocol/server-sqlite", "path/to/database.db"],
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm"]
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
            "args": ["-y", "@modelcontextprotocol/server-mysql", "mysql://localhost/mydb"],
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "mysql"]
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
            "args": ["-y", "@modelcontextprotocol/server-mongodb", "mongodb://localhost:27017/mydb"],
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "mongodb"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "git"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "github-token"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "gitlab-token"]
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
            "timeout": 60
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "chrome"]
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
            "timeout": 60
        },
        verified=True,
        requires=["node", "npm"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "slack-token"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "discord-token"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm"]
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
            "timeout": 60
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "openai-api-key"]
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
            "timeout": 60
        },
        verified=True,
        requires=["node", "npm", "anthropic-api-key"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["python", "pandas", "mcp-server-pandas"]
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
            "timeout": 60
        },
        verified=True,
        requires=["python", "jupyter", "mcp-server-jupyter"]
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
                "AWS_SECRET_ACCESS_KEY": "$AWS_SECRET_ACCESS_KEY"
            },
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "aws-credentials"]
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
            "env": {"AZURE_STORAGE_CONNECTION_STRING": "$AZURE_STORAGE_CONNECTION_STRING"},
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "azure-credentials"]
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
        config={
            "command": "op",
            "args": ["mcp-server"],
            "timeout": 30
        },
        verified=True,
        requires=["1password-cli"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "vault-token"]
    ),
    
    # ========== Documentation & Knowledge ==========
    MCPServerTemplate(
        id="context7",
        name="context7",
        display_name="Context7 Documentation Search",
        description="Search and retrieve documentation from multiple sources with AI-powered context understanding",
        category="Documentation",
        tags=["documentation", "search", "context", "ai", "knowledge", "docs", "cloud"],
        type="stdio",
        config={
            "timeout": 30,
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp","--api-key", "ctx7sk-c884daad-4169-47ca-b44a-bd30ba77c4db"]
        },
        verified=True,
        popular=True,
        requires=[],
        example_usage="Cloud-based service - no local setup required"
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "confluence-token"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "notion-token"]
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
            "timeout": 30
        },
        verified=True,
        popular=True,
        requires=["node", "npm", "docker"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "kubectl"]
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
            "timeout": 60
        },
        verified=True,
        requires=["node", "npm", "terraform"]
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
            "args": ["-y", "@modelcontextprotocol/server-prometheus", "http://localhost:9090"],
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm", "grafana-token"]
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
            "timeout": 30
        },
        verified=True,
        requires=["node", "npm"]
    ),
    
    MCPServerTemplate(
        id="pypi",
        name="pypi",
        display_name="PyPI Package Manager",
        description="Search and manage Python packages",
        category="Package Management",
        tags=["python", "pip", "pypi", "package"],
        type="stdio",
        config={
            "command": "python",
            "args": ["-m", "mcp_server_pypi"],
            "timeout": 30
        },
        verified=True,
        requires=["python", "mcp-server-pypi"]
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
        results.sort(key=lambda s: (
            not s.name.lower().startswith(query_lower),
            not s.popular,
            s.name
        ))
        
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