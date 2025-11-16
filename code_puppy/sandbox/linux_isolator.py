"""
Linux filesystem isolation using bubblewrap (bwrap).
"""

import os
import shlex
import shutil

from .base import FilesystemIsolator, SandboxOptions


class BubblewrapIsolator(FilesystemIsolator):
    """Filesystem isolation using bubblewrap on Linux."""

    def is_available(self) -> bool:
        """Check if bwrap is available on the system."""
        return shutil.which("bwrap") is not None

    def get_platform(self) -> str:
        """Get the platform this isolator supports."""
        return "linux"

    def wrap_command(
        self,
        command: str,
        options: SandboxOptions,
    ) -> tuple[str, dict[str, str]]:
        """
        Wrap a command with bubblewrap isolation.

        Args:
            command: The shell command to wrap
            options: Sandbox configuration options

        Returns:
            Tuple of (wrapped_command, environment_dict)
        """
        bwrap_args = ["bwrap"]

        # Core isolation settings
        bwrap_args.extend([
            "--unshare-all",  # Unshare all namespaces
            "--share-net",  # But keep network (for proxy)
            "--die-with-parent",  # Kill sandbox when parent dies
            "--new-session",  # New session to avoid signal leakage
        ])

        # Get the working directory (resolve to absolute path)
        cwd = os.path.abspath(options.cwd)

        # Mount filesystem based on read_scope
        if options.read_scope == "broad":
            # Broad scope: Mount entire filesystem as read-only, then overlay write access
            bwrap_args.extend([
                "--ro-bind", "/", "/",  # Mount entire filesystem read-only
            ])

            # Deny specific sensitive paths by unmounting/hiding them
            for denied_path in options.denied_read_paths:
                expanded_path = os.path.expanduser(denied_path)
                if os.path.exists(expanded_path):
                    # Bind an empty tmpfs over denied paths
                    bwrap_args.extend(["--tmpfs", expanded_path])

            # Allow write access to working directory (unbind and rebind as writable)
            bwrap_args.extend(["--bind", cwd, cwd])

            # Allow write access to /tmp
            bwrap_args.extend(["--bind", "/tmp", "/tmp"])

            # Add additional allowed write paths
            for write_path in options.allowed_write_paths:
                abs_path = os.path.abspath(write_path)
                if os.path.exists(abs_path):
                    bwrap_args.extend(["--bind", abs_path, abs_path])

        else:
            # Restricted scope: Only mount specific paths
            essential_paths = [
                "/usr",
                "/lib",
                "/lib64",
                "/bin",
                "/sbin",
            ]

            for path in essential_paths:
                if os.path.exists(path):
                    bwrap_args.extend(["--ro-bind", path, path])

            # Mount /proc and /dev (required for most programs)
            bwrap_args.extend([
                "--proc", "/proc",
                "--dev", "/dev",
            ])

            # Create tmpfs for /tmp
            bwrap_args.extend(["--tmpfs", "/tmp"])

            # Allow read-write access to working directory
            bwrap_args.extend(["--bind", cwd, cwd])

            # Add additional allowed read paths
            for read_path in options.allowed_read_paths:
                abs_path = os.path.abspath(read_path)
                if os.path.exists(abs_path):
                    bwrap_args.extend(["--ro-bind", abs_path, abs_path])

            # Add additional allowed write paths
            for write_path in options.allowed_write_paths:
                abs_path = os.path.abspath(write_path)
                if os.path.exists(abs_path):
                    bwrap_args.extend(["--bind", abs_path, abs_path])

        # Set working directory
        bwrap_args.extend(["--chdir", cwd])

        # Pass through specific environment variables
        env_vars = options.env or {}
        safe_env_vars = [
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "LC_ALL",
            "TERM",
            "SHELL",
        ]

        for var in safe_env_vars:
            value = env_vars.get(var) or os.environ.get(var)
            if value:
                bwrap_args.extend(["--setenv", var, value])

        # Add proxy environment variables if network isolation is enabled
        if options.network_isolation and options.proxy_socket_path:
            proxy_url = "socks5://localhost:9050"  # Will be configured later
            bwrap_args.extend([
                "--setenv", "HTTP_PROXY", proxy_url,
                "--setenv", "HTTPS_PROXY", proxy_url,
                "--setenv", "http_proxy", proxy_url,
                "--setenv", "https_proxy", proxy_url,
            ])

        # Build the actual command with resource limits if specified
        if options.max_memory_mb or options.max_cpu_percent:
            # Use systemd-run for resource limits if available
            if shutil.which("systemd-run"):
                command = self._wrap_with_systemd_run(
                    command,
                    max_memory_mb=options.max_memory_mb,
                    max_cpu_percent=options.max_cpu_percent,
                )

        # Run the command via shell
        bwrap_args.extend([
            "--",
            "/bin/sh",
            "-c",
            command,
        ])

        wrapped_command = " ".join(shlex.quote(arg) for arg in bwrap_args)

        return wrapped_command, env_vars

    def _wrap_with_systemd_run(
        self,
        command: str,
        max_memory_mb: int = None,
        max_cpu_percent: int = None,
    ) -> str:
        """
        Wrap a command with systemd-run for resource limits.

        Args:
            command: The command to wrap
            max_memory_mb: Maximum memory in MB
            max_cpu_percent: Maximum CPU percentage

        Returns:
            Command wrapped with systemd-run
        """
        systemd_args = [
            "systemd-run",
            "--user",  # Run as user, not system service
            "--scope",  # Create a transient scope unit
            "--quiet",  # Suppress output
        ]

        if max_memory_mb:
            # Set memory limit
            systemd_args.extend([f"--property=MemoryMax={max_memory_mb}M"])

        if max_cpu_percent:
            # Set CPU quota (percentage of one CPU core)
            # CPUQuota is in percentage points (100% = 1 core)
            systemd_args.extend([f"--property=CPUQuota={max_cpu_percent}%"])

        # Add the command
        systemd_args.extend(["--", "/bin/sh", "-c", command])

        return " ".join(shlex.quote(arg) for arg in systemd_args)
