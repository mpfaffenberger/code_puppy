"""
Comprehensive tests for server_registry_catalog.py.

Tests server registry catalog functionality including:
- Server template creation and validation
- Requirements handling (environment vars, args, dependencies)
- Template conversion to server configs with placeholder substitution
- Registry search, filtering, and CRUD operations
- Popular/verified server handling
- Backward compatibility with old requirements format
"""

from code_puppy.mcp_.server_registry_catalog import (
    MCP_SERVER_REGISTRY,
    MCPServerRequirements,
    MCPServerTemplate,
)


class TestMCPServerRequirements:
    """Test the MCPServerRequirements dataclass."""

    def test_requirements_creation_defaults(self):
        """Test MCPServerRequirements creation with default values."""
        req = MCPServerRequirements()

        assert req.environment_vars == []
        assert req.command_line_args == []
        assert req.required_tools == []
        assert req.package_dependencies == []
        assert req.system_requirements == []

    def test_requirements_creation_with_values(self):
        """Test MCPServerRequirements creation with values."""
        env_vars = ["GITHUB_TOKEN", "API_KEY"]
        cmd_args = [
            {
                "name": "port",
                "prompt": "Port number",
                "default": "3000",
                "required": False,
            }
        ]
        tools = ["node", "python", "npm"]
        packages = ["@modelcontextprotocol/server-filesystem"]
        system = ["Docker installed", "Git configured"]

        req = MCPServerRequirements(
            environment_vars=env_vars,
            command_line_args=cmd_args,
            required_tools=tools,
            package_dependencies=packages,
            system_requirements=system,
        )

        assert req.environment_vars == env_vars
        assert req.command_line_args == cmd_args
        assert req.required_tools == tools
        assert req.package_dependencies == packages
        assert req.system_requirements == system


class TestMCPServerTemplate:
    """Test the MCPServerTemplate class."""

    def test_template_creation_minimal(self):
        """Test MCPServerTemplate creation with minimal required fields."""
        template = MCPServerTemplate(
            id="test-server",
            name="test-server",
            display_name="Test Server",
            description="A test server",
            category="Test",
            tags=["test", "mock"],
            type="stdio",
            config={"command": "python", "args": ["server.py"]},
        )

        assert template.id == "test-server"
        assert template.name == "test-server"
        assert template.display_name == "Test Server"
        assert template.description == "A test server"
        assert template.category == "Test"
        assert template.tags == ["test", "mock"]
        assert template.type == "stdio"
        assert template.config == {"command": "python", "args": ["server.py"]}
        assert template.author == "Community"
        assert template.verified is False
        assert template.popular is False
        assert template.example_usage == ""

    def test_template_creation_full(self):
        """Test MCPServerTemplate creation with all fields."""
        requirements = MCPServerRequirements(
            environment_vars=["API_KEY"],
            required_tools=["node"],
        )

        template = MCPServerTemplate(
            id="full-server",
            name="full-server",
            display_name="Full Server",
            description="A complete server template",
            category="Development",
            tags=["development", "mcp"],
            type="http",
            config={"url": "http://localhost:3000"},
            author="Test Author",
            verified=True,
            popular=True,
            requires=requirements,
            example_usage="Example usage text",
        )

        assert template.id == "full-server"
        assert template.author == "Test Author"
        assert template.verified is True
        assert template.popular is True
        assert template.requires == requirements
        assert template.example_usage == "Example usage text"

    def test_get_requirements_with_object(self):
        """Test get_requirements when requires is MCPServerRequirements object."""
        requirements = MCPServerRequirements(
            environment_vars=["TOKEN"],
            required_tools=["python"],
        )

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        result = template.get_requirements()
        assert result == requirements
        assert result.environment_vars == ["TOKEN"]
        assert result.required_tools == ["python"]

    def test_get_requirements_with_list_backward_compatibility(self):
        """Test get_requirements with backward compatibility list."""
        old_format = ["node", "npm", "python"]

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=old_format,
        )

        result = template.get_requirements()
        assert isinstance(result, MCPServerRequirements)
        assert result.required_tools == old_format
        assert result.environment_vars == []
        assert result.command_line_args == []
        assert result.package_dependencies == []
        assert result.system_requirements == []

    def test_get_environment_vars_from_requirements(self):
        """Test getting environment variables from requirements."""
        requirements = MCPServerRequirements(
            environment_vars=["GITHUB_TOKEN", "API_KEY", "DB_PASSWORD"],
        )

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        env_vars = template.get_environment_vars()
        assert env_vars == ["GITHUB_TOKEN", "API_KEY", "DB_PASSWORD"]

    def test_get_environment_vars_from_config(self):
        """Test getting environment variables from config env placeholders."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={
                "env": {
                    "API_KEY": "$MY_API_KEY",
                    "DATABASE_URL": "$DB_URL",
                    "DEBUG": "true",  # Not a placeholder
                }
            },
        )

        env_vars = template.get_environment_vars()
        assert "MY_API_KEY" in env_vars
        assert "DB_URL" in env_vars
        assert "DEBUG" not in env_vars

    def test_get_environment_vars_mixed_sources(self):
        """Test getting environment variables from both requirements and config."""
        requirements = MCPServerRequirements(
            environment_vars=["GITHUB_TOKEN"],
        )

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={
                "env": {
                    "API_KEY": "$MY_API_KEY",
                    "TOKEN": "$MY_API_KEY",  # Duplicate, should not be added twice
                }
            },
            requires=requirements,
        )

        env_vars = template.get_environment_vars()
        assert "GITHUB_TOKEN" in env_vars
        assert "MY_API_KEY" in env_vars
        assert len(env_vars) == 2  # No duplicates

    def test_get_command_line_args(self):
        """Test getting command line arguments from requirements."""
        args = [
            {
                "name": "port",
                "prompt": "Port number",
                "default": "3000",
                "required": False,
            },
            {"name": "host", "prompt": "Host address", "required": True},
        ]

        requirements = MCPServerRequirements(command_line_args=args)

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        cmd_args = template.get_command_line_args()
        assert cmd_args == args

    def test_get_required_tools(self):
        """Test getting required tools from requirements."""
        tools = ["node", "npm", "git"]
        requirements = MCPServerRequirements(required_tools=tools)

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        result = template.get_required_tools()
        assert result == tools

    def test_get_package_dependencies(self):
        """Test getting package dependencies from requirements."""
        packages = ["@modelcontextprotocol/server-filesystem", "jupyter"]
        requirements = MCPServerRequirements(package_dependencies=packages)

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        result = template.get_package_dependencies()
        assert result == packages

    def test_get_system_requirements(self):
        """Test getting system requirements from requirements."""
        system = ["Docker installed", "Git configured", "Python 3.8+"]
        requirements = MCPServerRequirements(system_requirements=system)

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={},
            requires=requirements,
        )

        result = template.get_system_requirements()
        assert result == system

    def test_to_server_config_basic(self):
        """Test converting template to server config without substitutions."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={
                "command": "python",
                "args": ["server.py", "--port", "3000"],
                "env": {"DEBUG": "true"},
            },
        )

        config = template.to_server_config()

        assert config["name"] == "test"
        assert config["type"] == "stdio"
        assert config["command"] == "python"
        assert config["args"] == ["server.py", "--port", "3000"]
        assert config["env"] == {"DEBUG": "true"}

    def test_to_server_config_custom_name(self):
        """Test converting template with custom name."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={"command": "python"},
        )

        config = template.to_server_config(custom_name="my-custom-server")

        assert config["name"] == "my-custom-server"
        assert config["type"] == "stdio"
        assert config["command"] == "python"

    def test_to_server_config_arg_substitution(self):
        """Test converting template with argument substitution."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={
                "command": "python",
                "args": [
                    "server.py",
                    "--port",
                    "${port}",
                    "--host",
                    "${host}",
                    "--debug",
                    "true",  # No placeholder
                    "--path",
                    "/data/${db_path}",  # Multiple placeholders in one arg
                ],
            },
        )

        config = template.to_server_config(port=8080, host="localhost", db_path="mydb")

        expected_args = [
            "server.py",
            "--port",
            "8080",
            "--host",
            "localhost",
            "--debug",
            "true",
            "--path",
            "/data/mydb",
        ]
        assert config["args"] == expected_args

    def test_to_server_config_env_substitution(self):
        """Test converting template with environment variable substitution."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={
                "command": "python",
                "env": {
                    "API_KEY": "${api_key}",
                    "DATABASE_URL": "postgresql://user:pass@${host}:${port}/db",
                    "DEBUG": "true",  # No placeholder
                },
            },
        )

        config = template.to_server_config(
            api_key="secret123", host="localhost", port=5432
        )

        assert config["env"]["API_KEY"] == "secret123"
        assert (
            config["env"]["DATABASE_URL"] == "postgresql://user:pass@localhost:5432/db"
        )
        assert config["env"]["DEBUG"] == "true"

    def test_to_server_config_deep_copy(self):
        """Test that to_server_config creates a deep copy, not reference."""
        original_config = {"nested": {"value": "original"}}

        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config=original_config,
        )

        config = template.to_server_config()

        # Modify the original config
        original_config["nested"]["value"] = "modified"

        # Config should not be affected
        assert config["nested"]["value"] == "original"

    def test_to_server_config_no_args_substitution(self):
        """Test template conversion when no args field exists."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="http",
            config={"url": "http://localhost:3000"},
        )

        config = template.to_server_config(port=8080)

        assert config["url"] == "http://localhost:3000"  # No substitution occurred

    def test_to_server_config_no_env_substitution(self):
        """Test template conversion when no env field exists."""
        template = MCPServerTemplate(
            id="test",
            name="test",
            display_name="Test",
            description="Test",
            category="Test",
            tags=["test"],
            type="stdio",
            config={"command": "python"},
        )

        config = template.to_server_config(api_key="test")

        assert "env" not in config  # No env field created


class TestMCP_SERVER_REGISTRY:
    """Test the MCP_SERVER_REGISTRY constant."""

    def test_registry_is_list(self):
        """Test that registry is a list."""
        assert isinstance(MCP_SERVER_REGISTRY, list)
        assert len(MCP_SERVER_REGISTRY) > 0

    def test_registry_contains_templates(self):
        """Test that registry contains MCPServerTemplate objects."""
        for item in MCP_SERVER_REGISTRY:
            assert isinstance(item, MCPServerTemplate)

    def test_registry_contains_serena_template(self):
        """Test that registry contains the Serena server template."""
        serena_templates = [t for t in MCP_SERVER_REGISTRY if t.id == "serena"]
        assert len(serena_templates) == 1

        serena = serena_templates[0]
        assert serena.name == "serena"
        assert serena.display_name == "Serena"
        assert "Code Generation" in serena.description
        assert serena.verified is True
        assert serena.popular is True
        assert serena.type == "stdio"
        assert "uvx" in serena.get_required_tools()

    def test_registry_contains_filesystem_template(self):
        """Test that registry contains filesystem server template."""
        fs_templates = [t for t in MCP_SERVER_REGISTRY if t.id == "filesystem"]
        assert len(fs_templates) == 1

        fs = fs_templates[0]
        assert fs.name == "filesystem"
        assert fs.display_name == "Filesystem Access"
        assert "files in specified directories" in fs.description
        assert fs.verified is True
        assert fs.popular is True
        assert fs.type == "stdio"
        assert "node" in fs.get_required_tools()
        assert "npm" in fs.get_required_tools()

    def test_registry_contains_filesystem_home_template(self):
        """Test that registry contains filesystem-home server template."""
        fs_home_templates = [
            t for t in MCP_SERVER_REGISTRY if t.id == "filesystem-home"
        ]
        assert len(fs_home_templates) == 1

        fs_home = fs_home_templates[0]
        assert fs_home.name == "filesystem-home"
        assert fs_home.display_name == "Home Directory Access"
        assert "user's home directory" in fs_home.description
        assert fs_home.verified is True
        assert fs_home.popular is False  # Not marked as popular
        assert fs_home.type == "stdio"
        assert "node" in fs_home.get_required_tools()
        assert "npm" in fs_home.get_required_tools()

    def test_registry_categories(self):
        """Test that registry has multiple categories."""
        categories = {template.category for template in MCP_SERVER_REGISTRY}
        assert "Storage" in categories
        assert "Code" in categories
        assert len(categories) > 0

    def test_registry_types(self):
        """Test that registry has multiple server types."""
        types = {template.type for template in MCP_SERVER_REGISTRY}
        assert "stdio" in types
        assert "http" in types
        assert "sse" in types

    def test_registry_tags(self):
        """Test that registry templates have tags."""
        for template in MCP_SERVER_REGISTRY:
            assert isinstance(template.tags, list)
            assert len(template.tags) > 0
            # All tags should be strings
            for tag in template.tags:
                assert isinstance(tag, str)

    def test_registry_config_structure(self):
        """Test that all registry configs have proper structure."""
        for template in MCP_SERVER_REGISTRY:
            assert isinstance(template.config, dict)
            assert len(template.config) > 0

            # stdio servers should have command
            if template.type == "stdio":
                assert "command" in template.config
                assert isinstance(template.config["command"], str)

                # Most stdio servers should have args
                if "args" in template.config:
                    assert isinstance(template.config["args"], list)

            # http/sse servers should have url
            elif template.type in ["http", "sse"]:
                assert "url" in template.config
                assert isinstance(template.config["url"], str)

    def test_registry_template_ids_unique(self):
        """Test that all template IDs are unique."""
        ids = [template.id for template in MCP_SERVER_REGISTRY]
        assert len(ids) == len(set(ids))  # No duplicates

    def test_registry_template_names_unique(self):
        """Test that all template names are unique."""
        names = [template.name for template in MCP_SERVER_REGISTRY]
        assert len(names) == len(set(names))  # No duplicates

    def test_popular_servers_marked_correctly(self):
        """Test that some servers are marked as popular."""
        popular_templates = [t for t in MCP_SERVER_REGISTRY if t.popular]
        assert len(popular_templates) > 0

        # Check that known popular servers are marked
        popular_ids = {t.id for t in popular_templates}
        assert "serena" in popular_ids
        assert "filesystem" in popular_ids

    def test_verified_servers_marked_correctly(self):
        """Test that some servers are marked as verified."""
        verified_templates = [t for t in MCP_SERVER_REGISTRY if t.verified]
        assert len(verified_templates) > 0

        # Check that known verified servers are marked
        verified_ids = {t.id for t in verified_templates}
        assert "serena" in verified_ids
        assert "filesystem" in verified_ids
        assert "filesystem-home" in verified_ids

    def test_all_required_fields_present(self):
        """Test that all templates have required fields."""
        required_fields = [
            "id",
            "name",
            "display_name",
            "description",
            "category",
            "tags",
            "type",
            "config",
        ]

        for template in MCP_SERVER_REGISTRY:
            for field in required_fields:
                assert hasattr(template, field)
                assert getattr(template, field) is not None
                if field in ["tags"]:
                    assert isinstance(getattr(template, field), list)
                    assert len(getattr(template, field)) > 0
                elif field in ["config"]:
                    assert isinstance(getattr(template, field), dict)
                    assert len(getattr(template, field)) > 0
                elif field in ["type"]:
                    assert getattr(template, field) in ["stdio", "http", "sse"]


class TestRegistryFunctionality:
    """Test registry search and filtering functionality."""

    def test_find_by_id(self):
        """Test finding templates by ID."""

        def find_by_id(template_id):
            return next((t for t in MCP_SERVER_REGISTRY if t.id == template_id), None)

        # Test existing template
        template = find_by_id("serena")
        assert template is not None
        assert template.id == "serena"

        # Test non-existent template
        template = find_by_id("non-existent")
        assert template is None

    def test_find_by_category(self):
        """Test finding templates by category."""
        storage_templates = [t for t in MCP_SERVER_REGISTRY if t.category == "Storage"]
        code_templates = [t for t in MCP_SERVER_REGISTRY if t.category == "Code"]

        assert len(storage_templates) > 0
        assert len(code_templates) > 0

        # Check specific expected servers
        storage_ids = {t.id for t in storage_templates}
        code_ids = {t.id for t in code_templates}

        assert "filesystem" in storage_ids
        assert "filesystem-home" in storage_ids
        assert "serena" in code_ids

    def test_find_by_tag(self):
        """Test finding templates by tag."""
        code_tag_templates = [t for t in MCP_SERVER_REGISTRY if "Code" in t.tags]
        agentic_tag_templates = [t for t in MCP_SERVER_REGISTRY if "Agentic" in t.tags]

        assert len(code_tag_templates) > 0
        assert len(agentic_tag_templates) > 0

        # Check specific expected servers
        agentic_ids = {t.id for t in agentic_tag_templates}
        assert "serena" in agentic_ids

    def test_find_by_type(self):
        """Test finding templates by server type."""
        stdio_templates = [t for t in MCP_SERVER_REGISTRY if t.type == "stdio"]
        [t for t in MCP_SERVER_REGISTRY if t.type == "http"]

        assert len(stdio_templates) > 0
        # http_templates might be empty in current registry

        # Check specific expected servers
        stdio_ids = {t.id for t in stdio_templates}
        assert "serena" in stdio_ids
        assert "filesystem" in stdio_ids
        assert "filesystem-home" in stdio_ids

    def test_search_by_description(self):
        """Test searching templates by description text."""
        file_results = [
            t for t in MCP_SERVER_REGISTRY if "file" in t.description.lower()
        ]
        code_results = [
            t for t in MCP_SERVER_REGISTRY if "code" in t.description.lower()
        ]

        assert len(file_results) > 0
        assert len(code_results) > 0

        # Should find filesystem servers when searching for "file"
        file_ids = {t.id for t in file_results}
        assert "filesystem" in file_ids
        assert "filesystem-home" in file_ids

    def test_get_popular_servers(self):
        """Test getting only popular servers."""
        popular = [t for t in MCP_SERVER_REGISTRY if t.popular]

        assert len(popular) > 0
        assert all(t.popular for t in popular)

        popular_ids = {t.id for t in popular}
        assert "serena" in popular_ids
        assert "filesystem" in popular_ids

    def test_get_verified_servers(self):
        """Test getting only verified servers."""
        verified = [t for t in MCP_SERVER_REGISTRY if t.verified]

        assert len(verified) > 0
        assert all(t.verified for t in verified)

        verified_ids = {t.id for t in verified}
        assert "serena" in verified_ids
        assert "filesystem" in verified_ids
        assert "filesystem-home" in verified_ids

    def test_filter_by_requirements(self):
        """Test filtering templates by their requirements."""
        # Find templates that require node
        node_requirement_templates = [
            t for t in MCP_SERVER_REGISTRY if "node" in t.get_required_tools()
        ]

        assert len(node_requirement_templates) > 0

        # Find templates that require python
        [t for t in MCP_SERVER_REGISTRY if "python" in t.get_required_tools()]

        # Find templates that require environment variables
        [t for t in MCP_SERVER_REGISTRY if len(t.get_environment_vars()) > 0]

        # Some templates should require node
        node_ids = {t.id for t in node_requirement_templates}
        assert "filesystem" in node_ids
        assert "filesystem-home" in node_ids

    def test_template_config_validation(self):
        """Test that template configs are valid and usable."""
        for template in MCP_SERVER_REGISTRY:
            config = template.to_server_config()

            # All configs should have name and type
            assert "name" in config
            assert "type" in config
            assert config["type"] in ["stdio", "http", "sse"]

            # stdio configs should have command
            if config["type"] == "stdio":
                assert "command" in config
                assert isinstance(config["command"], str)
                assert len(config["command"]) > 0

            # http/sse configs should have url
            elif config["type"] in ["http", "sse"]:
                assert "url" in config
                assert isinstance(config["url"], str)
                assert len(config["url"]) > 0
                assert config["url"].startswith(("http://", "https://"))

    def test_registry_completeness(self):
        """Test that registry is complete and has expected servers."""
        registry_ids = {t.id for t in MCP_SERVER_REGISTRY}

        # Check for known important servers
        expected_servers = ["serena", "filesystem", "filesystem-home"]
        for server_id in expected_servers:
            assert server_id in registry_ids

        # Should have at least some servers
        assert len(MCP_SERVER_REGISTRY) >= 3

    def test_backward_compatibility_requirements(self):
        """Test that templates maintain backward compatibility for requirements."""
        for template in MCP_SERVER_REGISTRY:
            # get_requirements should always work
            requirements = template.get_requirements()
            assert isinstance(requirements, MCPServerRequirements)

            # Individual getter methods should work
            assert isinstance(template.get_environment_vars(), list)
            assert isinstance(template.get_command_line_args(), list)
            assert isinstance(template.get_required_tools(), list)
            assert isinstance(template.get_package_dependencies(), list)
            assert isinstance(template.get_system_requirements(), list)
