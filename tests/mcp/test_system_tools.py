"""
Tests for system_tools.py - System tool detection and validation.

This module tests the SystemToolDetector class which provides:
- Tool availability detection via PATH lookup
- Version extraction via subprocess calls
- Package dependency checking (npm/python)
- Installation suggestions for missing tools
"""

import subprocess
from unittest.mock import MagicMock, Mock, patch

from code_puppy.mcp_.system_tools import (
    SystemToolDetector,
    ToolInfo,
    detector,
)


class TestToolInfo:
    """Test cases for ToolInfo dataclass."""

    def test_toolinfo_basic_creation(self):
        """Test basic ToolInfo creation with required fields."""
        tool = ToolInfo(name="node", available=True)
        assert tool.name == "node"
        assert tool.available is True
        assert tool.version is None
        assert tool.path is None
        assert tool.error is None

    def test_toolinfo_full_creation(self):
        """Test ToolInfo creation with all fields."""
        tool = ToolInfo(
            name="python",
            available=True,
            version="3.11.5",
            path="/usr/bin/python",
            error=None,
        )
        assert tool.name == "python"
        assert tool.available is True
        assert tool.version == "3.11.5"
        assert tool.path == "/usr/bin/python"
        assert tool.error is None

    def test_toolinfo_unavailable_with_error(self):
        """Test ToolInfo for unavailable tool with error message."""
        tool = ToolInfo(
            name="nonexistent",
            available=False,
            error="nonexistent not found in PATH",
        )
        assert tool.name == "nonexistent"
        assert tool.available is False
        assert tool.error == "nonexistent not found in PATH"

    def test_toolinfo_available_with_version_error(self):
        """Test ToolInfo when tool is available but version check failed."""
        tool = ToolInfo(
            name="git",
            available=True,
            path="/usr/bin/git",
            error="Version check failed: some error",
        )
        assert tool.available is True
        assert tool.path == "/usr/bin/git"
        assert tool.error == "Version check failed: some error"


class TestSystemToolDetectorDetectTool:
    """Test cases for SystemToolDetector.detect_tool() method."""

    def test_detect_tool_not_in_path(self):
        """Test detection of tool not in PATH."""
        with patch("shutil.which", return_value=None):
            result = SystemToolDetector.detect_tool("nonexistent-tool")

        assert result.name == "nonexistent-tool"
        assert result.available is False
        assert result.error == "nonexistent-tool not found in PATH"
        assert result.path is None
        assert result.version is None

    def test_detect_tool_in_path_with_version_success(self):
        """Test detection of tool in PATH with successful version check."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v18.17.0"
        mock_result.stderr = ""

        with patch("shutil.which", return_value="/usr/local/bin/node"):
            with patch("subprocess.run", return_value=mock_result):
                result = SystemToolDetector.detect_tool("node")

        assert result.name == "node"
        assert result.available is True
        assert result.path == "/usr/local/bin/node"
        assert result.version == "18.17.0"
        assert result.error is None

    def test_detect_tool_in_path_no_version_command(self):
        """Test detection of tool in PATH but no version command defined."""
        with patch("shutil.which", return_value="/usr/bin/unknown-tool"):
            result = SystemToolDetector.detect_tool("unknown-tool")

        assert result.name == "unknown-tool"
        assert result.available is True
        assert result.path == "/usr/bin/unknown-tool"
        assert result.version is None
        assert result.error is None

    def test_detect_tool_version_command_fails(self):
        """Test detection when version command returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: unknown option"

        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch("subprocess.run", return_value=mock_result):
                result = SystemToolDetector.detect_tool("node")

        assert result.available is True
        assert result.path == "/usr/bin/node"
        assert result.version is None
        assert "Version check failed" in result.error
        assert "error: unknown option" in result.error

    def test_detect_tool_version_timeout(self):
        """Test detection when version command times out."""
        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired("node", 10)
            ):
                result = SystemToolDetector.detect_tool("node")

        assert result.available is True
        assert result.path == "/usr/bin/node"
        assert result.version is None
        assert result.error == "Version check timed out"

    def test_detect_tool_version_exception(self):
        """Test detection when version command raises unexpected exception."""
        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch("subprocess.run", side_effect=OSError("Something went wrong")):
                result = SystemToolDetector.detect_tool("node")

        assert result.available is True
        assert result.path == "/usr/bin/node"
        assert result.version is None
        assert "Version check error: Something went wrong" in result.error

    def test_detect_tool_version_in_stderr(self):
        """Test detection when version appears in stderr (like Java)."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = 'openjdk version "17.0.1" 2021-10-19'

        with patch("shutil.which", return_value="/usr/bin/java"):
            with patch("subprocess.run", return_value=mock_result):
                result = SystemToolDetector.detect_tool("java")

        assert result.available is True
        assert result.version == "17.0.1"


class TestSystemToolDetectorDetectTools:
    """Test cases for SystemToolDetector.detect_tools() method."""

    def test_detect_tools_multiple(self):
        """Test detection of multiple tools."""

        def mock_which(tool_name):
            paths = {
                "node": "/usr/bin/node",
                "python": "/usr/bin/python",
                "nonexistent": None,
            }
            return paths.get(tool_name)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v16.0.0"
        mock_result.stderr = ""

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", return_value=mock_result):
                results = SystemToolDetector.detect_tools(
                    ["node", "python", "nonexistent"]
                )

        assert len(results) == 3
        assert results["node"].available is True
        assert results["python"].available is True
        assert results["nonexistent"].available is False

    def test_detect_tools_empty_list(self):
        """Test detection with empty tool list."""
        results = SystemToolDetector.detect_tools([])
        assert results == {}

    def test_detect_tools_single(self):
        """Test detection of single tool via detect_tools."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "git version 2.42.0"
            mock_result.stderr = ""
            with patch("subprocess.run", return_value=mock_result):
                results = SystemToolDetector.detect_tools(["git"])

        assert len(results) == 1
        assert "git" in results
        assert results["git"].available is True


class TestSystemToolDetectorParseVersion:
    """Test cases for SystemToolDetector._parse_version() method."""

    def test_parse_version_empty_output(self):
        """Test parsing empty output."""
        result = SystemToolDetector._parse_version("node", "")
        assert result is None

    def test_parse_version_none_output(self):
        """Test parsing None output."""
        result = SystemToolDetector._parse_version("node", None)
        assert result is None

    def test_parse_version_semver_with_v(self):
        """Test parsing version with 'v' prefix (e.g., v18.17.0)."""
        result = SystemToolDetector._parse_version("node", "v18.17.0")
        assert result == "18.17.0"

    def test_parse_version_semver_without_v(self):
        """Test parsing version without 'v' prefix."""
        result = SystemToolDetector._parse_version("npm", "9.8.1")
        assert result == "9.8.1"

    def test_parse_version_with_prefix_text(self):
        """Test parsing version with text prefix like 'git version 2.42.0'."""
        result = SystemToolDetector._parse_version("git", "git version 2.42.0")
        assert result == "2.42.0"

    def test_parse_version_four_part(self):
        """Test parsing four-part version number."""
        result = SystemToolDetector._parse_version("tool", "version 1.2.3.4")
        assert result == "1.2.3.4"

    def test_parse_version_major_minor_only(self):
        """Test parsing version with only major.minor."""
        result = SystemToolDetector._parse_version("tool", "Tool 3.9")
        assert result == "3.9"

    def test_parse_version_complex_output(self):
        """Test parsing version from complex multi-line output."""
        output = """Python 3.11.5
Some additional info
More lines"""
        result = SystemToolDetector._parse_version("python", output)
        assert result == "3.11.5"

    def test_parse_version_version_keyword(self):
        """Test parsing 'version X.Y.Z' pattern."""
        result = SystemToolDetector._parse_version("tool", "Tool version 2.1.0")
        assert result == "2.1.0"

    def test_parse_version_fallback_to_first_line(self):
        """Test fallback to first line when no pattern matches."""
        result = SystemToolDetector._parse_version("tool", "Custom Build Alpha")
        assert result == "Custom Build Alpha"

    def test_parse_version_long_first_line_skipped(self):
        """Test that very long first lines are skipped."""
        long_line = "x" * 150
        result = SystemToolDetector._parse_version("tool", long_line)
        assert result is None

    def test_parse_version_java_style(self):
        """Test parsing Java-style version output."""
        output = 'openjdk version "11.0.20" 2023-07-18'
        result = SystemToolDetector._parse_version("java", output)
        assert result == "11.0.20"

    def test_parse_version_go_style(self):
        """Test parsing Go-style version output."""
        result = SystemToolDetector._parse_version(
            "go", "go version go1.21.0 darwin/arm64"
        )
        assert result == "1.21.0"


class TestSystemToolDetectorCheckPackageDependencies:
    """Test cases for SystemToolDetector.check_package_dependencies() method."""

    def test_check_npm_scoped_package(self):
        """Test checking npm scoped package (starts with @)."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = SystemToolDetector.check_package_dependencies(["@types/node"])

        assert result["@types/node"] is True

    def test_check_npm_namespaced_package(self):
        """Test checking npm package with slash (namespace)."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = SystemToolDetector.check_package_dependencies(["lodash/fp"])

        assert result["lodash/fp"] is True

    def test_check_python_package_known(self):
        """Test checking known Python packages."""
        # Mocking _check_python_package directly since it uses importlib
        with patch.object(
            SystemToolDetector, "_check_python_package", return_value=True
        ):
            result = SystemToolDetector.check_package_dependencies(["numpy"])

        assert result["numpy"] is True

    def test_check_unknown_package_tries_both(self):
        """Test that unknown packages try both npm and python."""
        npm_result = Mock()
        npm_result.returncode = 1  # npm fails

        with patch("subprocess.run", return_value=npm_result):
            with patch.object(
                SystemToolDetector, "_check_python_package", return_value=True
            ):
                result = SystemToolDetector.check_package_dependencies(["some-package"])

        assert result["some-package"] is True

    def test_check_package_not_found(self):
        """Test checking package that doesn't exist anywhere."""
        npm_result = Mock()
        npm_result.returncode = 1

        with patch("subprocess.run", return_value=npm_result):
            with patch.object(
                SystemToolDetector, "_check_python_package", return_value=False
            ):
                result = SystemToolDetector.check_package_dependencies(
                    ["nonexistent-pkg-xyz"]
                )

        assert result["nonexistent-pkg-xyz"] is False

    def test_check_multiple_packages(self):
        """Test checking multiple packages."""
        npm_result = Mock()
        npm_result.returncode = 0

        with patch("subprocess.run", return_value=npm_result):
            with patch.object(
                SystemToolDetector, "_check_python_package", return_value=True
            ):
                result = SystemToolDetector.check_package_dependencies(
                    ["@types/node", "pandas", "matplotlib", "some-lib"]
                )

        assert len(result) == 4

    def test_check_empty_packages_list(self):
        """Test checking empty packages list."""
        result = SystemToolDetector.check_package_dependencies([])
        assert result == {}


class TestSystemToolDetectorCheckNpmPackage:
    """Test cases for SystemToolDetector._check_npm_package() method."""

    def test_check_npm_package_available(self):
        """Test checking npm package that is available."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = SystemToolDetector._check_npm_package("typescript")

        assert result is True
        mock_run.assert_called_once_with(
            ["npm", "list", "-g", "typescript"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_check_npm_package_not_available(self):
        """Test checking npm package that is not available."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = SystemToolDetector._check_npm_package("nonexistent-pkg")

        assert result is False

    def test_check_npm_package_exception(self):
        """Test checking npm package when exception occurs."""
        with patch("subprocess.run", side_effect=OSError("npm not found")):
            result = SystemToolDetector._check_npm_package("typescript")

        assert result is False

    def test_check_npm_package_timeout(self):
        """Test checking npm package when timeout occurs."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npm", 10)):
            result = SystemToolDetector._check_npm_package("typescript")

        assert result is False


class TestSystemToolDetectorCheckPythonPackage:
    """Test cases for SystemToolDetector._check_python_package() method."""

    def test_check_python_package_available(self):
        """Test checking Python package that is available."""
        # 'json' is a standard library module, always available
        result = SystemToolDetector._check_python_package("json")
        assert result is True

    def test_check_python_package_not_available(self):
        """Test checking Python package that is not available."""
        result = SystemToolDetector._check_python_package(
            "this_package_definitely_does_not_exist_xyz123"
        )
        assert result is False

    def test_check_python_package_with_mock_import(self):
        """Test checking Python package with mocked import."""
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"fake_module": mock_module}):
            # After adding to sys.modules, import should work
            result = SystemToolDetector._check_python_package("fake_module")
        # Note: importlib.import_module checks sys.modules, so this should pass
        assert result is True

    def test_check_python_package_import_error(self):
        """Test that ImportError returns False."""
        with patch(
            "importlib.import_module", side_effect=ImportError("No module found")
        ):
            result = SystemToolDetector._check_python_package("anything")
        assert result is False


class TestSystemToolDetectorGetInstallationSuggestions:
    """Test cases for SystemToolDetector.get_installation_suggestions() method."""

    def test_suggestions_for_node(self):
        """Test installation suggestions for Node.js."""
        suggestions = SystemToolDetector.get_installation_suggestions("node")
        assert len(suggestions) >= 1
        assert any("nodejs" in s.lower() or "node.js" in s.lower() for s in suggestions)

    def test_suggestions_for_npm(self):
        """Test installation suggestions for npm."""
        suggestions = SystemToolDetector.get_installation_suggestions("npm")
        assert len(suggestions) >= 1
        assert any("node" in s.lower() for s in suggestions)

    def test_suggestions_for_npx(self):
        """Test installation suggestions for npx."""
        suggestions = SystemToolDetector.get_installation_suggestions("npx")
        assert len(suggestions) >= 1

    def test_suggestions_for_python(self):
        """Test installation suggestions for Python."""
        suggestions = SystemToolDetector.get_installation_suggestions("python")
        assert len(suggestions) >= 1
        assert any("python" in s.lower() for s in suggestions)

    def test_suggestions_for_python3(self):
        """Test installation suggestions for Python3."""
        suggestions = SystemToolDetector.get_installation_suggestions("python3")
        assert len(suggestions) >= 1

    def test_suggestions_for_pip(self):
        """Test installation suggestions for pip."""
        suggestions = SystemToolDetector.get_installation_suggestions("pip")
        assert len(suggestions) >= 1
        assert any("ensurepip" in s.lower() for s in suggestions)

    def test_suggestions_for_pip3(self):
        """Test installation suggestions for pip3."""
        suggestions = SystemToolDetector.get_installation_suggestions("pip3")
        assert len(suggestions) >= 1

    def test_suggestions_for_git(self):
        """Test installation suggestions for git."""
        suggestions = SystemToolDetector.get_installation_suggestions("git")
        assert len(suggestions) >= 1
        assert any("git" in s.lower() for s in suggestions)

    def test_suggestions_for_docker(self):
        """Test installation suggestions for Docker."""
        suggestions = SystemToolDetector.get_installation_suggestions("docker")
        assert len(suggestions) >= 1
        assert any("docker" in s.lower() for s in suggestions)

    def test_suggestions_for_java(self):
        """Test installation suggestions for Java."""
        suggestions = SystemToolDetector.get_installation_suggestions("java")
        assert len(suggestions) >= 1
        assert any("jdk" in s.lower() or "openjdk" in s.lower() for s in suggestions)

    def test_suggestions_for_jupyter(self):
        """Test installation suggestions for Jupyter."""
        suggestions = SystemToolDetector.get_installation_suggestions("jupyter")
        assert len(suggestions) >= 1
        assert any("pip" in s.lower() for s in suggestions)

    def test_suggestions_for_unknown_tool(self):
        """Test installation suggestions for unknown tool."""
        suggestions = SystemToolDetector.get_installation_suggestions(
            "unknown-tool-xyz"
        )
        assert len(suggestions) == 1
        assert "unknown-tool-xyz" in suggestions[0]
        assert "install" in suggestions[0].lower()


class TestVersionCommands:
    """Test cases for VERSION_COMMANDS constant."""

    def test_version_commands_contains_common_tools(self):
        """Test that VERSION_COMMANDS contains common tools."""
        expected_tools = [
            "node",
            "npm",
            "npx",
            "python",
            "python3",
            "pip",
            "pip3",
            "git",
            "docker",
            "java",
            "go",
            "rust",
            "cargo",
        ]
        for tool in expected_tools:
            assert tool in SystemToolDetector.VERSION_COMMANDS

    def test_version_commands_are_lists(self):
        """Test that all version commands are lists."""
        for tool, cmd in SystemToolDetector.VERSION_COMMANDS.items():
            assert isinstance(cmd, list), f"{tool} command is not a list"
            assert len(cmd) >= 2, f"{tool} command should have at least 2 elements"

    def test_version_commands_have_version_flag(self):
        """Test that version commands contain version flag."""
        for tool, cmd in SystemToolDetector.VERSION_COMMANDS.items():
            # Most tools use --version or -version
            has_version_flag = any(
                "version" in arg.lower() for arg in cmd if isinstance(arg, str)
            )
            assert has_version_flag, f"{tool} command missing version flag"


class TestGlobalDetectorInstance:
    """Test cases for the global detector instance."""

    def test_global_detector_exists(self):
        """Test that global detector instance exists."""
        assert detector is not None

    def test_global_detector_is_system_tool_detector(self):
        """Test that global detector is a SystemToolDetector instance."""
        assert isinstance(detector, SystemToolDetector)

    def test_global_detector_has_methods(self):
        """Test that global detector has expected methods."""
        assert hasattr(detector, "detect_tool")
        assert hasattr(detector, "detect_tools")
        assert hasattr(detector, "check_package_dependencies")
        assert hasattr(detector, "get_installation_suggestions")


class TestIntegrationScenarios:
    """Integration-style tests for realistic usage scenarios."""

    def test_detect_node_ecosystem(self):
        """Test detecting Node.js ecosystem tools."""

        def mock_which(tool):
            if tool in ["node", "npm", "npx"]:
                return f"/usr/local/bin/{tool}"
            return None

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v18.17.0"
        mock_result.stderr = ""

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", return_value=mock_result):
                results = SystemToolDetector.detect_tools(["node", "npm", "npx"])

        assert all(r.available for r in results.values())
        assert all(r.version is not None for r in results.values())

    def test_detect_python_ecosystem(self):
        """Test detecting Python ecosystem tools."""

        def mock_which(tool):
            if tool in ["python", "python3", "pip", "pip3"]:
                return f"/usr/bin/{tool}"
            return None

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Python 3.11.5"
        mock_result.stderr = ""

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", return_value=mock_result):
                results = SystemToolDetector.detect_tools(
                    ["python", "python3", "pip", "pip3"]
                )

        assert all(r.available for r in results.values())

    def test_mixed_availability_scenario(self):
        """Test scenario with mixed tool availability."""

        def mock_which(tool):
            available = {"git": "/usr/bin/git", "docker": None, "node": "/usr/bin/node"}
            return available.get(tool)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "version 2.0.0"
        mock_result.stderr = ""

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", return_value=mock_result):
                results = SystemToolDetector.detect_tools(["git", "docker", "node"])

        assert results["git"].available is True
        assert results["docker"].available is False
        assert results["node"].available is True
