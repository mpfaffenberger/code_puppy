"""Playwright-compatible browser manager for browser automation.

Supports multiple simultaneous instances with unique profile directories.
"""

import asyncio
import atexit
import contextlib
import contextvars
import math
import os
import shlex
import shutil
import socket
from collections import deque
from pathlib import Path
from typing import Callable, Dict, Optional

from playwright.async_api import Browser, BrowserContext, Page

from code_puppy import config
from code_puppy.messaging import emit_info, emit_success, emit_warning

# Registry for custom browser types from plugins (e.g., Camoufox for stealth browsing)
_CUSTOM_BROWSER_TYPES: Dict[str, Callable] = {}
_BROWSER_TYPES_LOADED: bool = False
_BUILTIN_PLAYWRIGHT_BROWSERS = {"chromium", "firefox", "webkit"}


def _load_plugin_browser_types() -> None:
    """Load custom browser types from plugins.

    This is called lazily on first browser initialization to allow plugins
    to register custom browser providers (like Camoufox for stealth browsing).
    """
    global _CUSTOM_BROWSER_TYPES, _BROWSER_TYPES_LOADED

    if _BROWSER_TYPES_LOADED:
        return

    _BROWSER_TYPES_LOADED = True

    try:
        from code_puppy.callbacks import on_register_browser_types

        results = on_register_browser_types()
        for result in results:
            if isinstance(result, dict):
                _CUSTOM_BROWSER_TYPES.update(result)
    except Exception:
        pass  # Don't break if plugins fail to load


# Store active manager instances by session ID
_active_managers: dict[str, "BrowserManager"] = {}

# Context variable for browser session - properly inherits through async tasks
# This allows parallel agent invocations to each have their own browser instance
_browser_session_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "browser_session", default=None
)


def set_browser_session(session_id: Optional[str]) -> contextvars.Token:
    """Set the browser session ID for the current context.

    This must be called BEFORE any tool calls that use the browser.
    The context will properly propagate to all subsequent async calls.

    Args:
        session_id: The session ID to use for browser operations.

    Returns:
        A token that can be used to reset the context.
    """
    return _browser_session_var.set(session_id)


def get_browser_session() -> Optional[str]:
    """Get the browser session ID for the current context.

    Returns:
        The current session ID, or None if not set.
    """
    return _browser_session_var.get()


def get_session_browser_manager() -> "BrowserManager":
    """Get the BrowserManager for the current context's session.

    This is the preferred way to get a browser manager in tool functions,
    as it automatically uses the correct session ID for the current
    agent context.

    Returns:
        A BrowserManager instance for the current session.
    """
    session_id = get_browser_session()
    return get_browser_manager(session_id)


# Flag to track if cleanup has already run
_cleanup_done: bool = False


class BrowserManager:
    """Browser manager for browser automation.

    Supports multiple simultaneous instances, each with its own profile directory.
    Uses Playwright Chromium by default for maximum compatibility.
    Supports Lightpanda as an optional CDP backend.
    """

    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _playwright: Optional[object] = None
    _lightpanda_process: Optional[asyncio.subprocess.Process] = None
    _lightpanda_endpoint: Optional[str] = None
    _lightpanda_stderr_task: Optional[asyncio.Task] = None
    _initialized: bool = False

    def __init__(
        self, session_id: Optional[str] = None, browser_type: Optional[str] = None
    ):
        """Initialize manager settings.

        Args:
            session_id: Optional session ID for this instance.
                If None, uses 'default' as the session ID.
            browser_type: Optional browser type to use. If None, uses Chromium.
                Custom types can be registered via the register_browser_types hook.
        """
        self.session_id = session_id or "default"
        self.browser_type = browser_type  # None means default Chromium

        # Default to headless=True (no browser spam during tests)
        # Override with BROWSER_HEADLESS=false to see the browser
        self.headless = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
        self.homepage = "https://www.google.com"

        # Unique profile directory per session for browser state
        self.profile_dir = self._get_profile_directory()
        self._lightpanda_stderr_buffer: deque[str] = deque(maxlen=128)

    def _get_profile_directory(self) -> Path:
        """Get or create the profile directory for this session.

        Each session gets its own profile directory under:
        XDG_CACHE_HOME/code_puppy/browser_profiles/<session_id>/

        This allows multiple instances to run simultaneously.
        """
        cache_dir = Path(config.CACHE_DIR)
        profiles_base = cache_dir / "browser_profiles"
        profile_path = profiles_base / self.session_id
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return profile_path

    @staticmethod
    def _find_free_port() -> int:
        """Find an available local TCP port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _resolve_lightpanda_executable(self) -> str:
        """Resolve the Lightpanda executable path from env or PATH."""
        executable = os.getenv("LIGHTPANDA_EXECUTABLE", "lightpanda")

        path_like = os.path.sep in executable or (
            os.path.altsep is not None and os.path.altsep in executable
        )

        if path_like:
            executable_path = Path(executable).expanduser()
            if executable_path.is_file() and os.access(executable_path, os.X_OK):
                return str(executable_path)
        else:
            resolved = shutil.which(executable)
            if resolved:
                return resolved

        raise RuntimeError(
            "Lightpanda executable not found or not executable. Install Lightpanda "
            "or set LIGHTPANDA_EXECUTABLE to a valid executable path."
        )

    def _get_lightpanda_host(self) -> str:
        """Get Lightpanda host."""
        return os.getenv("LIGHTPANDA_HOST", "127.0.0.1")

    @staticmethod
    def _validate_tcp_port(port: int, source_name: str) -> int:
        """Validate a TCP port number and return it."""
        if not 1 <= port <= 65535:
            raise RuntimeError(
                f"{source_name} must be between 1 and 65535, got: {port}"
            )
        return port

    def _get_lightpanda_port(self) -> int:
        """Get Lightpanda CDP port from env or an ephemeral free port."""
        configured_port = os.getenv("LIGHTPANDA_PORT")
        if configured_port:
            try:
                parsed_port = int(configured_port)
            except ValueError as exc:
                raise RuntimeError(
                    f"Invalid LIGHTPANDA_PORT value: {configured_port}"
                ) from exc
            return self._validate_tcp_port(parsed_port, "LIGHTPANDA_PORT")

        return self._validate_tcp_port(
            self._find_free_port(), "auto-selected Lightpanda port"
        )

    @staticmethod
    def _get_lightpanda_startup_timeout() -> float:
        """Get Lightpanda startup timeout in seconds."""
        timeout_raw = os.getenv("LIGHTPANDA_STARTUP_TIMEOUT", "10")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid LIGHTPANDA_STARTUP_TIMEOUT value: {timeout_raw}"
            ) from exc

        if not math.isfinite(timeout) or timeout <= 0:
            raise RuntimeError(
                "LIGHTPANDA_STARTUP_TIMEOUT must be a finite positive number, "
                f"got: {timeout_raw}"
            )
        return max(timeout, 1.0)

    @staticmethod
    def _get_lightpanda_startup_retries() -> int:
        """Get number of startup retries for auto-selected ports."""
        retries_raw = os.getenv("LIGHTPANDA_STARTUP_RETRIES", "3")
        try:
            retries = int(retries_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid LIGHTPANDA_STARTUP_RETRIES value: {retries_raw}"
            ) from exc
        return max(retries, 1)

    async def _read_lightpanda_stderr(self) -> str:
        """Read Lightpanda stderr if available for better startup errors."""
        if not self._lightpanda_stderr_buffer:
            return ""
        stderr_text = "\n".join(self._lightpanda_stderr_buffer).strip()
        return stderr_text[-500:]

    async def _drain_lightpanda_stderr(self, stream: asyncio.StreamReader) -> None:
        """Drain stderr continuously to avoid subprocess pipe backpressure."""
        try:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    return
                decoded = chunk.decode(errors="replace")
                for line in decoded.splitlines():
                    stripped = line.strip()
                    if stripped:
                        self._lightpanda_stderr_buffer.append(stripped)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Stderr draining is best effort and should not fail startup.
            return

    def _start_lightpanda_stderr_drain(self) -> None:
        """Start background stderr drain task when stream is available."""
        if self._lightpanda_stderr_task and not self._lightpanda_stderr_task.done():
            self._lightpanda_stderr_task.cancel()

        stream = self._lightpanda_process.stderr if self._lightpanda_process else None

        if isinstance(stream, asyncio.StreamReader):
            self._lightpanda_stderr_task = asyncio.create_task(
                self._drain_lightpanda_stderr(stream)
            )
        else:
            self._lightpanda_stderr_task = None

    async def _stop_lightpanda_stderr_drain(self) -> None:
        """Stop background stderr drain task."""
        task = self._lightpanda_stderr_task
        self._lightpanda_stderr_task = None

        if not task:
            return

        if task.done():
            with contextlib.suppress(Exception):
                await task
            return

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    def _build_lightpanda_command(self, host: str, port: int) -> list[str]:
        """Build the Lightpanda startup command."""
        executable = self._resolve_lightpanda_executable()
        command = [
            executable,
            "serve",
            f"--host={host}",
            f"--port={port}",
        ]

        extra_args_raw = os.getenv("LIGHTPANDA_ARGS", "").strip()
        if extra_args_raw:
            command.extend(shlex.split(extra_args_raw, posix=os.name != "nt"))

        return command

    async def _connect_lightpanda_over_cdp(self, endpoint: str) -> Browser:
        """Connect Playwright to Lightpanda CDP with retry."""
        timeout_s = self._get_lightpanda_startup_timeout()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        last_error: Optional[Exception] = None

        while loop.time() < deadline:
            if (
                self._lightpanda_process
                and self._lightpanda_process.returncode is not None
            ):
                stderr_text = await self._read_lightpanda_stderr()
                raise RuntimeError(
                    "Lightpanda process exited before CDP connection was ready "
                    f"(code={self._lightpanda_process.returncode}). "
                    f"{stderr_text}"
                )

            try:
                if not self._playwright:
                    raise RuntimeError("Playwright is not initialized.")
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                return await asyncio.wait_for(
                    self._playwright.chromium.connect_over_cdp(endpoint),
                    timeout=remaining,
                )
            except Exception as exc:
                last_error = exc
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.2, remaining))

        raise RuntimeError(
            f"Timed out connecting to Lightpanda CDP at {endpoint}: {last_error}"
        )

    async def _initialize_lightpanda_browser(self) -> None:
        """Initialize Lightpanda and attach Playwright over CDP.

        Uses retry-on-failure for auto-selected ports to reduce startup
        flakiness caused by bind races between probing and process launch.
        """
        from playwright.async_api import async_playwright

        if not self.headless:
            emit_warning(
                "Lightpanda is headless-only; forcing headless mode for this session."
            )
            self.headless = True

        host = self._get_lightpanda_host()
        self._playwright = await async_playwright().start()
        fixed_port = bool(os.getenv("LIGHTPANDA_PORT"))
        max_attempts = 1 if fixed_port else self._get_lightpanda_startup_retries()
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            port = self._get_lightpanda_port()
            self._lightpanda_endpoint = f"http://{host}:{port}"

            command = self._build_lightpanda_command(host, port)
            emit_info(
                f"Starting Lightpanda CDP endpoint at {host}:{port} "
                f"(attempt {attempt}/{max_attempts})"
            )

            self._lightpanda_process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            self._lightpanda_stderr_buffer.clear()
            self._start_lightpanda_stderr_drain()

            try:
                browser = await self._connect_lightpanda_over_cdp(
                    self._lightpanda_endpoint
                )

                # Reuse existing context when available (CDP default context),
                # otherwise create one for consistent manager behavior.
                if browser.contexts:
                    context = browser.contexts[0]
                else:
                    context = await browser.new_context()

                self._browser = browser
                self._context = context
                return
            except Exception as exc:
                last_error = exc
                await self._stop_lightpanda_process()

                if attempt < max_attempts:
                    emit_warning(
                        "Lightpanda startup failed; retrying with a new port "
                        f"(attempt {attempt + 1}/{max_attempts})."
                    )
                    await asyncio.sleep(0.1)

        raise RuntimeError(
            f"Failed to initialize Lightpanda after {max_attempts} attempts: "
            f"{last_error}"
        ) from last_error

    async def _stop_lightpanda_process(self) -> None:
        """Stop Lightpanda process if this manager started one."""
        process = self._lightpanda_process
        self._lightpanda_process = None
        self._lightpanda_endpoint = None

        if process:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    with contextlib.suppress(Exception):
                        await process.wait()
            else:
                with contextlib.suppress(Exception):
                    await process.wait()

        await self._stop_lightpanda_stderr_drain()

    async def async_initialize(self) -> None:
        """Initialize a browser backend."""
        if self._initialized:
            return

        try:
            browser_name = self.browser_type or "chromium"
            emit_info(
                f"Initializing {browser_name} browser (session: {self.session_id})..."
            )
            await self._initialize_browser()
            self._initialized = True

        except Exception:
            await self._cleanup()
            raise

    async def _initialize_browser(self) -> None:
        """Initialize browser with persistent context.

        Checks for custom browser types registered via plugins first,
        then falls back to default Playwright Chromium.
        """
        # Load plugin browser types on first initialization
        _load_plugin_browser_types()
        requested_browser = (self.browser_type or "chromium").lower()

        # Check if a custom browser type was requested and is available
        if self.browser_type and self.browser_type in _CUSTOM_BROWSER_TYPES:
            emit_info(
                f"Using custom browser type '{self.browser_type}' "
                f"(session: {self.session_id})"
            )
            init_func = _CUSTOM_BROWSER_TYPES[self.browser_type]
            # Custom init functions should set self._context and self._browser
            await init_func(self)
            self._initialized = True
            return

        if requested_browser == "lightpanda":
            emit_info(f"Using Lightpanda browser (session: {self.session_id})")
            await self._initialize_lightpanda_browser()
            self._initialized = True
            return

        if requested_browser not in _BUILTIN_PLAYWRIGHT_BROWSERS:
            supported_browsers = sorted(
                _BUILTIN_PLAYWRIGHT_BROWSERS
                | {"lightpanda"}
                | set(_CUSTOM_BROWSER_TYPES.keys())
            )
            raise ValueError(
                f"Unsupported browser_type '{self.browser_type}'. "
                f"Supported values: {', '.join(supported_browsers)}"
            )

        # Default: use built-in Playwright browser backends
        from playwright.async_api import async_playwright

        emit_info(
            f"Using built-in Playwright browser '{requested_browser}' "
            f"with persistent profile: {self.profile_dir}"
        )

        pw = await async_playwright().start()
        self._playwright = pw
        browser_launcher = getattr(pw, requested_browser)
        context = await browser_launcher.launch_persistent_context(
            user_data_dir=str(self.profile_dir), headless=self.headless
        )
        self._context = context
        self._browser = context.browser
        self._initialized = True

    async def get_current_page(self) -> Optional[Page]:
        """Get the currently active page. Lazily creates one if none exist."""
        if not self._initialized or not self._context:
            await self.async_initialize()

        if not self._context:
            return None

        pages = self._context.pages
        if pages:
            return pages[0]

        # Lazily create a new blank page without navigation
        return await self._context.new_page()

    async def new_page(self, url: Optional[str] = None) -> Page:
        """Create a new page and optionally navigate to URL."""
        if not self._initialized:
            await self.async_initialize()

        page = await self._context.new_page()
        if url:
            await page.goto(url)
        return page

    async def close_page(self, page: Page) -> None:
        """Close a specific page."""
        await page.close()

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages."""
        if not self._context:
            return []
        return self._context.pages

    async def _cleanup(self, silent: bool = False) -> None:
        """Clean up browser resources and save persistent state.

        Args:
            silent: If True, suppress all errors (used during shutdown).
        """
        try:
            # Save browser state before closing (cookies, localStorage, etc.)
            if self._context:
                try:
                    storage_state_path = self.profile_dir / "storage_state.json"
                    await self._context.storage_state(path=str(storage_state_path))
                    if not silent:
                        emit_success(f"Browser state saved to {storage_state_path}")
                except Exception as e:
                    if not silent:
                        emit_warning(f"Could not save storage state: {e}")

                try:
                    await self._context.close()
                except Exception:
                    pass  # Ignore errors during context close
                self._context = None

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass  # Ignore errors during browser close
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass  # Ignore errors during playwright shutdown
                self._playwright = None

            if self._lightpanda_process:
                try:
                    await self._stop_lightpanda_process()
                except Exception:
                    pass  # Ignore errors during Lightpanda shutdown

            self._initialized = False

            # Remove from active managers
            if self.session_id in _active_managers:
                del _active_managers[self.session_id]

        except Exception as e:
            if not silent:
                emit_warning(f"Warning during cleanup: {e}")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        await self._cleanup()
        emit_info(f"Browser closed (session: {self.session_id})")


def get_browser_manager(
    session_id: Optional[str] = None, browser_type: Optional[str] = None
) -> BrowserManager:
    """Get or create a BrowserManager instance.

    Args:
        session_id: Optional session ID. If provided and a manager with this
            session exists, returns that manager. Otherwise creates a new one.
            If None, uses 'default' as the session ID.
        browser_type: Optional browser type to use for new managers.
            Ignored if a manager for this session already exists.
            Custom types can be registered via the register_browser_types hook.

    Returns:
        A BrowserManager instance.

    Example:
        # Default session (for single-agent use)
        manager = get_browser_manager()

        # Named session (for multi-agent use)
        manager = get_browser_manager("qa-agent-1")

        # Custom browser type (e.g., stealth browser from plugin)
        manager = get_browser_manager("stealth-session", browser_type="camoufox")
    """
    session_id = session_id or "default"

    if session_id not in _active_managers:
        _active_managers[session_id] = BrowserManager(session_id, browser_type)

    return _active_managers[session_id]


async def cleanup_all_browsers() -> None:
    """Close all active browser manager instances.

    This should be called before application exit to ensure all browser
    connections are properly closed and no dangling futures remain.
    """
    global _cleanup_done

    if _cleanup_done:
        return

    _cleanup_done = True

    # Get a copy of the keys since we'll be modifying the dict during cleanup
    session_ids = list(_active_managers.keys())

    for session_id in session_ids:
        manager = _active_managers.get(session_id)
        if manager and manager._initialized:
            try:
                await manager._cleanup(silent=True)
            except Exception:
                pass  # Silently ignore all errors during exit cleanup


def _sync_cleanup_browsers() -> None:
    """Synchronous cleanup wrapper for use with atexit.

    Creates a new event loop to run the async cleanup since the main
    event loop may have already been closed when atexit handlers run.
    """
    global _cleanup_done

    if _cleanup_done or not _active_managers:
        return

    try:
        # Try to get the running loop first
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, schedule the cleanup
            # but this is unlikely in atexit handlers
            loop.create_task(cleanup_all_browsers())
            return
        except RuntimeError:
            pass  # No running loop, which is expected in atexit

        # Create a new event loop for cleanup
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(cleanup_all_browsers())
        finally:
            loop.close()
    except Exception:
        # Silently swallow ALL errors during exit cleanup
        # We don't want to spam the user with errors on exit
        pass


# Register the cleanup handler with atexit
# This ensures browsers are closed even if close_browser() isn't explicitly called
atexit.register(_sync_cleanup_browsers)


# Backwards compatibility aliases
CamoufoxManager = BrowserManager
get_camoufox_manager = get_browser_manager
