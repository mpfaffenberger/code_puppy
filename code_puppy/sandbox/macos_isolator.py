"""
macOS filesystem isolation using sandbox-exec.
"""

import os
import shlex
import shutil
import tempfile
from pathlib import Path

from .base import FilesystemIsolator, SandboxOptions


class SandboxExecIsolator(FilesystemIsolator):
    """Filesystem isolation using sandbox-exec on macOS."""

    def is_available(self) -> bool:
        """Check if sandbox-exec is available on the system."""
        return shutil.which("sandbox-exec") is not None

    def get_platform(self) -> str:
        """Get the platform this isolator supports."""
        return "macos"

    def _generate_sandbox_profile(self, options: SandboxOptions) -> str:
        """
        Generate a sandbox profile in Scheme for sandbox-exec.

        Args:
            options: Sandbox configuration options

        Returns:
            Sandbox profile as a string
        """
        cwd = os.path.abspath(options.cwd)

        # Create the sandbox profile in Scheme
        profile = """(version 1)

;; Allow basic system operations
(allow process-exec*)
(allow process-fork)
(allow signal)
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix-shm)

;; Allow network access (for proxy)
(allow network*)

"""

        # Configure read access based on read_scope
        if options.read_scope == "broad":
            # Broad scope: Allow reading everything except denied paths
            profile += """;; Broad read scope: Allow reading entire filesystem
(allow file-read*)

"""
            # Explicitly deny sensitive paths
            for denied_path in options.denied_read_paths:
                expanded_path = os.path.expanduser(denied_path)
                profile += f""";; Deny access to: {expanded_path}
(deny file-read*
    (subpath "{expanded_path}")
)

"""
            # Allow write access to specific paths
            profile += f""";; Allow read-write access to working directory
(allow file*
    (subpath "{cwd}")
)

;; Allow write access to /tmp
(allow file*
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/var/tmp")
)

"""
            # Add additional allowed write paths
            for write_path in options.allowed_write_paths:
                abs_path = os.path.abspath(write_path)
                profile += f""";; Allow write access to: {abs_path}
(allow file*
    (subpath "{abs_path}")
)

"""
        else:
            # Restricted scope: Only allow specific paths
            profile += """;; Restricted read scope: Only allow specific paths

;; Allow reading from essential system directories
(allow file-read*
    (subpath "/usr/lib")
    (subpath "/usr/bin")
    (subpath "/usr/share")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/System/Library")
    (subpath "/Library")
    (subpath "/private/var/db/timezone")
    (subpath "/dev")
)

;; Allow temporary file access
(allow file*
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/var/tmp")
)

"""
            # Build allowed read paths list
            allowed_read = [cwd] + [os.path.abspath(p) for p in options.allowed_read_paths]

            # Build allowed write paths list
            allowed_write = [cwd] + [os.path.abspath(p) for p in options.allowed_write_paths]

            # Add allowed read paths
            for path in allowed_read:
                profile += f""";; Allow read access to: {path}
(allow file-read*
    (subpath "{path}")
)

"""

            # Add allowed write paths
            for path in allowed_write:
                profile += f""";; Allow read-write access to: {path}
(allow file*
    (subpath "{path}")
)

"""

        # Explicitly block access to sensitive directories (in both modes)
        profile += """;; Explicitly deny access to sensitive directories
(deny file*
    (subpath (string-append (param "HOME") "/.ssh"))
    (subpath (string-append (param "HOME") "/.aws"))
    (subpath (string-append (param "HOME") "/.gnupg"))
)
"""

        return profile

    def wrap_command(
        self,
        command: str,
        options: SandboxOptions,
    ) -> tuple[str, dict[str, str]]:
        """
        Wrap a command with sandbox-exec isolation.

        Args:
            command: The shell command to wrap
            options: Sandbox configuration options

        Returns:
            Tuple of (wrapped_command, environment_dict)
        """
        # Generate the sandbox profile
        profile = self._generate_sandbox_profile(options)

        # Write profile to a temporary file
        # We'll use a predictable path so it can be cleaned up
        profile_dir = Path(tempfile.gettempdir()) / "code_puppy_sandbox"
        profile_dir.mkdir(exist_ok=True)

        profile_file = profile_dir / f"profile_{os.getpid()}.sb"
        profile_file.write_text(profile)

        # Build the sandbox-exec command
        sandbox_args = [
            "sandbox-exec",
            "-f", str(profile_file),
        ]

        # Set HOME parameter for the profile
        env_vars = options.env or {}
        home = env_vars.get("HOME") or os.environ.get("HOME", str(Path.home()))

        # Add parameters for the sandbox profile
        sandbox_args.extend([
            "-D", f"HOME={home}",
        ])

        # Wrap command with resource limits if specified
        if options.max_memory_mb or options.max_cpu_percent:
            command = self._wrap_with_resource_limits(
                command,
                max_memory_mb=options.max_memory_mb,
                max_cpu_percent=options.max_cpu_percent,
            )

        # Add the shell command to execute
        sandbox_args.extend([
            "/bin/sh",
            "-c",
            command,
        ])

        wrapped_command = " ".join(shlex.quote(arg) for arg in sandbox_args)

        # Add proxy environment variables if network isolation is enabled
        if options.network_isolation and options.proxy_socket_path:
            proxy_url = "socks5://localhost:9050"
            env_vars.update({
                "HTTP_PROXY": proxy_url,
                "HTTPS_PROXY": proxy_url,
                "http_proxy": proxy_url,
                "https_proxy": proxy_url,
            })

        return wrapped_command, env_vars

    def _wrap_with_resource_limits(
        self,
        command: str,
        max_memory_mb: int = None,
        max_cpu_percent: int = None,
    ) -> str:
        """
        Wrap command with resource limits using ulimit (macOS).

        Args:
            command: The command to wrap
            max_memory_mb: Maximum memory in MB
            max_cpu_percent: Maximum CPU percentage (not supported on macOS via ulimit)

        Returns:
            Command wrapped with ulimit
        """
        # Build ulimit prefix
        ulimit_prefix = []

        if max_memory_mb:
            # Set memory limit (in KB for ulimit -m and -v)
            memory_kb = max_memory_mb * 1024
            ulimit_prefix.append(f"ulimit -m {memory_kb}")  # Max resident set size
            ulimit_prefix.append(f"ulimit -v {memory_kb}")  # Virtual memory

        # Note: CPU limits are harder on macOS without launchd
        # We can set CPU time limit but not percentage
        # For now, skip CPU limiting on macOS (would need launchd or cpulimit tool)

        if ulimit_prefix:
            return " && ".join(ulimit_prefix) + f" && {command}"

        return command
