"""
Minimal tests for server_registry_catalog.py MCPServerTemplate (template
creation, requirements handling, and config placeholder substitution).
"""

from code_puppy.mcp_.server_registry_catalog import (
    MCPServerRequirements,
    MCPServerTemplate,
)


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
