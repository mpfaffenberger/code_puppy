"""
Network proxy server for monitoring and restricting network access.
"""

import asyncio
import logging
import urllib.parse
from typing import Callable, Optional, Set

logger = logging.getLogger(__name__)


class NetworkProxyServer:
    """
    HTTP/HTTPS proxy server for sandboxed network access.

    Routes traffic through a monitored proxy that:
    - Enforces domain allowlists
    - Prompts user for approval of new domains
    - Logs all network requests
    """

    def __init__(
        self,
        allowed_domains: Optional[Set[str]] = None,
        approval_callback: Optional[Callable[[str], bool]] = None,
        port: int = 9050,
    ):
        """
        Initialize the network proxy server.

        Args:
            allowed_domains: Set of pre-approved domains
            approval_callback: Async function to ask user for domain approval
            port: Port to listen on
        """
        self.allowed_domains = allowed_domains or set()
        self.approval_callback = approval_callback
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self._running = False

        # Default allowed domains (package registries, git hosts, etc.)
        self._add_default_domains()

    def _add_default_domains(self):
        """Add commonly-used safe domains."""
        default_domains = {
            # Package registries
            "pypi.org",
            "files.pythonhosted.org",
            "npmjs.com",
            "registry.npmjs.org",
            "rubygems.org",
            "crates.io",
            # Version control
            "github.com",
            "raw.githubusercontent.com",
            "gitlab.com",
            "bitbucket.org",
            # CDNs
            "cdn.jsdelivr.net",
            "unpkg.com",
            # Documentation
            "docs.python.org",
            "nodejs.org",
            # AI providers (for code-puppy itself)
            "api.openai.com",
            "api.anthropic.com",
            "generativelanguage.googleapis.com",
        }
        self.allowed_domains.update(default_domains)

    def add_allowed_domain(self, domain: str):
        """Add a domain to the allowlist."""
        self.allowed_domains.add(domain.lower())

    def remove_allowed_domain(self, domain: str):
        """Remove a domain from the allowlist."""
        self.allowed_domains.discard(domain.lower())

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        """Handle a client connection."""
        try:
            # Read the HTTP request
            request_line = await reader.readline()
            if not request_line:
                return

            request_line = request_line.decode("utf-8").strip()
            logger.debug(f"Proxy request: {request_line}")

            # Parse the request
            parts = request_line.split()
            if len(parts) < 2:
                await self._send_error(writer, 400, "Bad Request")
                return

            method, url = parts[0], parts[1]

            # Extract the domain from the URL
            parsed = urllib.parse.urlparse(url if url.startswith("http") else f"http://{url}")
            domain = parsed.netloc.split(":")[0]  # Remove port if present

            # Check if domain is allowed
            if not await self._is_domain_allowed(domain):
                logger.warning(f"Blocked request to unauthorized domain: {domain}")
                await self._send_error(writer, 403, f"Domain not allowed: {domain}")
                return

            # For CONNECT requests (HTTPS), establish a tunnel
            if method == "CONNECT":
                await self._handle_connect(reader, writer, domain, parsed.port or 443)
            else:
                # For regular HTTP, forward the request
                await self._forward_request(reader, writer, method, url, request_line)

        except Exception as e:
            logger.error(f"Error handling proxy client: {e}", exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _is_domain_allowed(self, domain: str) -> bool:
        """Check if a domain is allowed, prompting user if necessary."""
        domain = domain.lower()

        # Check if already allowed
        if domain in self.allowed_domains:
            return True

        # Check for wildcard matches (e.g., *.github.com)
        parts = domain.split(".")
        for i in range(len(parts)):
            wildcard = "*." + ".".join(parts[i:])
            if wildcard in self.allowed_domains:
                return True

        # Ask user for approval if callback is provided
        if self.approval_callback:
            approved = await self.approval_callback(domain)
            if approved:
                self.allowed_domains.add(domain)
                return True

        return False

    async def _send_error(self, writer: asyncio.StreamWriter, code: int, message: str):
        """Send an HTTP error response."""
        response = (
            f"HTTP/1.1 {code} {message}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{message}\r\n"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def _handle_connect(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ):
        """Handle HTTPS CONNECT tunnel."""
        try:
            # Connect to the target server
            target_reader, target_writer = await asyncio.open_connection(host, port)

            # Send success response to client
            response = "HTTP/1.1 200 Connection Established\r\n\r\n"
            client_writer.write(response.encode("utf-8"))
            await client_writer.drain()

            # Relay data bidirectionally
            await asyncio.gather(
                self._relay_data(client_reader, target_writer, f"client->{host}"),
                self._relay_data(target_reader, client_writer, f"{host}->client"),
                return_exceptions=True,
            )

        except Exception as e:
            logger.error(f"Error in CONNECT tunnel to {host}:{port}: {e}")
        finally:
            try:
                target_writer.close()
                await target_writer.wait_closed()
            except Exception:
                pass

    async def _forward_request(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        method: str,
        url: str,
        request_line: str,
    ):
        """Forward an HTTP request to the target server."""
        try:
            # Parse URL
            parsed = urllib.parse.urlparse(url)
            host = parsed.netloc.split(":")[0]
            port = int(parsed.port) if parsed.port else 80

            # Connect to target
            target_reader, target_writer = await asyncio.open_connection(host, port)

            # Forward the request
            target_writer.write(f"{request_line}\r\n".encode("utf-8"))

            # Forward headers
            while True:
                line = await client_reader.readline()
                target_writer.write(line)
                if line == b"\r\n":
                    break

            await target_writer.drain()

            # Relay the response and any request body
            await asyncio.gather(
                self._relay_data(client_reader, target_writer, f"client->{host}"),
                self._relay_data(target_reader, client_writer, f"{host}->client"),
                return_exceptions=True,
            )

        except Exception as e:
            logger.error(f"Error forwarding request to {url}: {e}")
        finally:
            try:
                target_writer.close()
                await target_writer.wait_closed()
            except Exception:
                pass

    async def _relay_data(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        label: str,
    ):
        """Relay data from reader to writer."""
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as e:
            logger.debug(f"Relay {label} ended: {e}")

    async def start(self):
        """Start the proxy server."""
        if self._running:
            return

        self.server = await asyncio.start_server(
            self._handle_client,
            "127.0.0.1",
            self.port,
        )

        self._running = True
        logger.info(f"Network proxy started on 127.0.0.1:{self.port}")

    async def stop(self):
        """Stop the proxy server."""
        if not self._running:
            return

        self._running = False

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        logger.info("Network proxy stopped")

    def is_running(self) -> bool:
        """Check if the proxy is running."""
        return self._running
