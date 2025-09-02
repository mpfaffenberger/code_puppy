"""
System tool detection and validation for MCP server requirements.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ToolInfo:
    """Information about a detected system tool."""

    name: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None


class SystemToolDetector:
    """Detect and validate system tools required by MCP servers."""

    # Tool version commands
    VERSION_COMMANDS = {
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "npx": ["npx", "--version"],
        "python": ["python", "--version"],
        "python3": ["python3", "--version"],
        "pip": ["pip", "--version"],
        "pip3": ["pip3", "--version"],
        "git": ["git", "--version"],
        "docker": ["docker", "--version"],
        "java": ["java", "-version"],
        "go": ["go", "version"],
        "rust": ["rustc", "--version"],
        "cargo": ["cargo", "--version"],
        "julia": ["julia", "--version"],
        "R": ["R", "--version"],
        "php": ["php", "--version"],
        "ruby": ["ruby", "--version"],
        "perl": ["perl", "--version"],
        "swift": ["swift", "--version"],
        "dotnet": ["dotnet", "--version"],
        "jupyter": ["jupyter", "--version"],
        "code": ["code", "--version"],  # VS Code
        "vim": ["vim", "--version"],
        "emacs": ["emacs", "--version"],
    }

    @classmethod
    def detect_tool(cls, tool_name: str) -> ToolInfo:
        """Detect if a tool is available and get its version."""
        # First check if tool is in PATH
        tool_path = shutil.which(tool_name)

        if not tool_path:
            return ToolInfo(
                name=tool_name, available=False, error=f"{tool_name} not found in PATH"
            )

        # Try to get version
        version_cmd = cls.VERSION_COMMANDS.get(tool_name)
        version = None
        error = None

        if version_cmd:
            try:
                # Run version command
                result = subprocess.run(
                    version_cmd, capture_output=True, text=True, timeout=10
                )

                if result.returncode == 0:
                    # Parse version from output
                    output = result.stdout.strip() or result.stderr.strip()
                    version = cls._parse_version(tool_name, output)
                else:
                    error = f"Version check failed: {result.stderr.strip()}"

            except subprocess.TimeoutExpired:
                error = "Version check timed out"
            except Exception as e:
                error = f"Version check error: {str(e)}"

        return ToolInfo(
            name=tool_name, available=True, version=version, path=tool_path, error=error
        )

    @classmethod
    def detect_tools(cls, tool_names: List[str]) -> Dict[str, ToolInfo]:
        """Detect multiple tools."""
        return {name: cls.detect_tool(name) for name in tool_names}

    @classmethod
    def _parse_version(cls, tool_name: str, output: str) -> Optional[str]:
        """Parse version string from command output."""
        if not output:
            return None

        # Common version patterns
        import re

        # Try to find version pattern like "v1.2.3" or "1.2.3"
        version_patterns = [
            r"v?(\d+\.\d+\.\d+(?:\.\d+)?)",  # Standard semver
            r"(\d+\.\d+\.\d+)",  # Simple version
            r"version\s+v?(\d+\.\d+\.\d+)",  # "version 1.2.3"
            r"v?(\d+\.\d+)",  # Major.minor only
        ]

        for pattern in version_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)

        # If no pattern matches, return first line (common for many tools)
        first_line = output.split("\n")[0].strip()
        if len(first_line) < 100:  # Reasonable length for a version string
            return first_line

        return None

    @classmethod
    def check_package_dependencies(cls, packages: List[str]) -> Dict[str, bool]:
        """Check if package dependencies are available."""
        results = {}

        for package in packages:
            available = False

            # Try different package managers/methods
            if package.startswith("@") or "/" in package:
                # Likely npm package
                available = cls._check_npm_package(package)
            elif package in ["jupyter", "pandas", "numpy", "matplotlib"]:
                # Python packages
                available = cls._check_python_package(package)
            else:
                # Try both npm and python
                available = cls._check_npm_package(
                    package
                ) or cls._check_python_package(package)

            results[package] = available

        return results

    @classmethod
    def _check_npm_package(cls, package: str) -> bool:
        """Check if an npm package is available."""
        try:
            result = subprocess.run(
                ["npm", "list", "-g", package],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def _check_python_package(cls, package: str) -> bool:
        """Check if a Python package is available."""
        try:
            import importlib

            importlib.import_module(package)
            return True
        except ImportError:
            return False

    @classmethod
    def get_installation_suggestions(cls, tool_name: str) -> List[str]:
        """Get installation suggestions for a missing tool."""
        suggestions = {
            "node": [
                "Install Node.js from https://nodejs.org",
                "Or use package manager: brew install node (macOS) / sudo apt install nodejs (Ubuntu)",
            ],
            "npm": ["Usually comes with Node.js - install Node.js first"],
            "npx": ["Usually comes with npm 5.2+ - update npm: npm install -g npm"],
            "python": [
                "Install Python from https://python.org",
                "Or use package manager: brew install python (macOS) / sudo apt install python3 (Ubuntu)",
            ],
            "python3": ["Same as python - install Python 3.x"],
            "pip": ["Usually comes with Python - try: python -m ensurepip"],
            "pip3": ["Usually comes with Python 3 - try: python3 -m ensurepip"],
            "git": [
                "Install Git from https://git-scm.com",
                "Or use package manager: brew install git (macOS) / sudo apt install git (Ubuntu)",
            ],
            "docker": ["Install Docker from https://docker.com"],
            "java": [
                "Install OpenJDK from https://openjdk.java.net",
                "Or use package manager: brew install openjdk (macOS) / sudo apt install default-jdk (Ubuntu)",
            ],
            "jupyter": ["Install with pip: pip install jupyter"],
        }

        return suggestions.get(tool_name, [f"Please install {tool_name} manually"])


# Global detector instance
detector = SystemToolDetector()
