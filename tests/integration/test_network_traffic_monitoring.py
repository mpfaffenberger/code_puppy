"""Integration test to capture and report all network traffic during message processing.

This test uses a custom HTTP/HTTPS proxy to monitor all requests made by code-puppy
when processing a simple message. The goal is to identify all external domains contacted
so we can build proper assertions and understand the dependency chain.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

IS_WINDOWS = os.name == "nt" or sys.platform.startswith("win")

pytestmark = pytest.mark.skipif(
    IS_WINDOWS,
    reason="Interactive CLI pexpect tests have platform-specific issues on Windows",
)


@dataclass
class NetworkCall:
    """Represents a single network request."""

    method: str
    url: str
    host: str
    path: str
    timestamp: float


@dataclass
class TrafficReport:
    """Aggregated report of all network traffic."""

    calls: list[NetworkCall] = field(default_factory=list)
    domains_contacted: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_requests: int = 0

    def add_call(self, call: NetworkCall) -> None:
        """Add a network call to the report."""
        self.calls.append(call)
        self.domains_contacted[call.host] += 1
        self.total_requests += 1

    def generate_markdown_report(self) -> str:
        """Generate a human-readable markdown report."""
        lines = [
            "# Network Traffic Report",
            "",
            f"**Total Requests:** {self.total_requests}",
            f"**Unique Domains:** {len(self.domains_contacted)}",
            "",
            "## Domains Contacted",
            "",
        ]

        # Sort domains by request count (descending)
        sorted_domains = sorted(
            self.domains_contacted.items(), key=lambda x: x[1], reverse=True
        )

        for domain, count in sorted_domains:
            lines.append(f"- **{domain}** ({count} request{'s' if count > 1 else ''})")

        lines.extend(["", "## Request Details", ""])

        # Group requests by domain
        requests_by_domain = defaultdict(list)
        for call in self.calls:
            requests_by_domain[call.host].append(call)

        for domain in [d for d, _ in sorted_domains]:
            lines.append(f"### {domain}")
            lines.append("")
            for call in requests_by_domain[domain]:
                lines.append(f"- `{call.method} {call.path}`")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export report as JSON."""
        return json.dumps(
            {
                "total_requests": self.total_requests,
                "unique_domains": len(self.domains_contacted),
                "domains": dict(self.domains_contacted),
                "calls": [
                    {
                        "method": call.method,
                        "url": call.url,
                        "host": call.host,
                        "path": call.path,
                        "timestamp": call.timestamp,
                    }
                    for call in self.calls
                ],
            },
            indent=2,
        )


class TrafficLoggingProxy:
    """Simple HTTP/HTTPS proxy that logs all traffic without decrypting HTTPS.

    For HTTPS, this proxy uses CONNECT tunneling and logs the domain from the
    CONNECT request. The actual encrypted traffic is tunneled through without
    decryption.
    """

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.report = TrafficReport()
        self.server = None
        self.thread = None
        self.actual_port = None

    def start(self):
        """Start the proxy server in a background thread."""
        report = self.report

        class ProxyHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                """Suppress default logging."""
                pass

            def do_CONNECT(self):
                """Handle HTTPS CONNECT requests by tunneling."""
                # Extract host and port from CONNECT request
                try:
                    if ":" in self.path:
                        host, port_str = self.path.split(":", 1)
                        port = int(port_str)
                    else:
                        host = self.path
                        port = 443
                except ValueError:
                    self.send_error(400, "Bad Request: Invalid CONNECT target")
                    return

                # Log the CONNECT attempt
                call = NetworkCall(
                    method="CONNECT",
                    url=f"https://{self.path}",
                    host=host,
                    path="/",
                    timestamp=time.time(),
                )
                report.add_call(call)

                # Establish connection to the destination
                dest_sock = None
                try:
                    dest_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    dest_sock.settimeout(30)
                    dest_sock.connect((host, port))

                    # Send success response to client
                    self.send_response(200, "Connection established")
                    self.end_headers()

                    # Now relay data bidirectionally
                    self._tunnel_traffic(self.connection, dest_sock)

                except Exception as e:
                    # If connection fails, send error response
                    try:
                        self.send_error(502, f"Proxy Error: {e}")
                    except Exception:
                        pass
                finally:
                    if dest_sock:
                        try:
                            dest_sock.close()
                        except Exception:
                            pass

            def _tunnel_traffic(self, client_sock, dest_sock):
                """Relay traffic between client and destination."""
                import select

                client_sock.setblocking(False)
                dest_sock.setblocking(False)

                sockets = [client_sock, dest_sock]
                timeout = 60  # 60 second idle timeout

                try:
                    while True:
                        readable, _, exceptional = select.select(
                            sockets, [], sockets, timeout
                        )

                        if exceptional:
                            break

                        if not readable:
                            # Timeout - no data for 60 seconds
                            break

                        for sock in readable:
                            try:
                                data = sock.recv(8192)
                                if not data:
                                    return  # Connection closed

                                # Send to the other socket
                                other = (
                                    dest_sock if sock is client_sock else client_sock
                                )
                                other.sendall(data)
                            except (ConnectionResetError, BrokenPipeError, OSError):
                                return
                except Exception:
                    # Unexpected error during tunneling - close gracefully
                    return

            def do_GET(self):
                self._handle_request("GET")

            def do_POST(self):
                self._handle_request("POST")

            def do_PUT(self):
                self._handle_request("PUT")

            def do_DELETE(self):
                self._handle_request("DELETE")

            def do_PATCH(self):
                self._handle_request("PATCH")

            def _handle_request(self, method):
                """Handle HTTP requests (not HTTPS)."""
                parsed = urlparse(self.path)
                host = self.headers.get("Host", parsed.netloc or "unknown")

                call = NetworkCall(
                    method=method,
                    url=self.path,
                    host=host,
                    path=parsed.path or "/",
                    timestamp=time.time(),
                )
                report.add_call(call)

                # Send minimal response - we're just logging
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"Traffic monitoring proxy - request logged")

        # Create server with automatic port assignment
        self.server = HTTPServer((self.host, self.port), ProxyHandler)
        self.actual_port = self.server.server_address[1]

        # Start server in background thread
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Give server a moment to start
        time.sleep(0.1)

    def stop(self):
        """Stop the proxy server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1)

    def get_proxy_url(self):
        """Get the proxy URL for environment variables."""
        return f"http://{self.host}:{self.actual_port}"


def test_network_traffic_on_simple_message(
    cli_harness,
    integration_env,
    tmp_path: Path,
):
    """Monitor all network traffic when processing a simple 'hi' message.

    This test:
    1. Starts a logging proxy server
    2. Configures httpx to use the proxy
    3. Spawns code-puppy in interactive mode
    4. Sends a simple "hi" message
    5. Captures all network calls
    6. Generates a detailed report

    The report is written to both markdown and JSON formats for analysis.

    Note: For HTTPS traffic, we log the domain from CONNECT requests but don't
    decrypt the actual traffic (no SSL MITM needed).
    """
    from tests.integration.cli_expect.fixtures import satisfy_initial_prompts

    # Start proxy server
    proxy = TrafficLoggingProxy()
    proxy.start()

    try:
        proxy_url = proxy.get_proxy_url()
        print(f"\n🐶 Proxy started at {proxy_url}")

        # Add proxy settings to environment
        test_env = integration_env.copy()
        test_env["HTTP_PROXY"] = proxy_url
        test_env["HTTPS_PROXY"] = proxy_url
        test_env["http_proxy"] = proxy_url  # lowercase variants
        test_env["https_proxy"] = proxy_url
        # Disable retry transport for proxy testing (disables SSL verification)
        test_env["CODE_PUPPY_DISABLE_RETRY_TRANSPORT"] = "true"

        # Spawn CLI with proxy configured
        result = cli_harness.spawn(args=["-i"], env=test_env)
        satisfy_initial_prompts(result)
        cli_harness.wait_for_ready(result)

        # Send a simple message
        print("\n🐶 Sending 'hi' message...")
        result.sendline("hi\r")

        # Wait for response (with generous timeout for LLM response)
        try:
            result.child.expect(r"Auto-saved session", timeout=120)
        except Exception as e:
            print(f"\n⚠️  Didn't see auto-save (may have failed): {e}")
            # If auto-save doesn't happen, that's okay - we still got traffic
            pass

        # Give it a moment to finish any pending requests
        time.sleep(2)

        # Cleanup
        try:
            result.sendline("/quit\r")
        except Exception:
            pass
        finally:
            cli_harness.cleanup(result)

    finally:
        # Stop proxy
        proxy.stop()

    # Generate reports
    markdown_report = proxy.report.generate_markdown_report()
    json_report = proxy.report.to_json()

    # Write reports to tmp_path
    report_md_path = tmp_path / "network_traffic_report.md"
    report_json_path = tmp_path / "network_traffic_report.json"

    report_md_path.write_text(markdown_report, encoding="utf-8")
    report_json_path.write_text(json_report, encoding="utf-8")

    # Print report to console so Mike can see it!
    print("\n" + "=" * 80)
    print("NETWORK TRAFFIC REPORT")
    print("=" * 80)
    print(markdown_report)
    print("=" * 80)
    print("\nFull reports saved to:")
    print(f"  - {report_md_path}")
    print(f"  - {report_json_path}")
    print("=" * 80 + "\n")

    # STRICT WHITELIST - Only these two domains are allowed!
    ALLOWED_DOMAINS = {
        "cloud.dbos.dev",
        "api.cerebras.ai",
        "pypi.org",
    }

    # Let's see what domains we're talking to!
    print("\n🐶 Woof! I sniffed out these domains:")
    for domain, count in sorted(
        proxy.report.domains_contacted.items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  - {domain}: {count} request(s)")

    # Check that we contacted at least one domain (sanity check)
    assert proxy.report.total_requests > 0, "Expected at least one network request"
    assert len(proxy.report.domains_contacted) > 0, (
        "Expected at least one domain to be contacted"
    )

    # NOW THE REAL DEAL - Blow up if ANY domain outside the whitelist was contacted!
    contacted_domains = set(proxy.report.domains_contacted.keys())
    unauthorized_domains = contacted_domains - ALLOWED_DOMAINS

    if unauthorized_domains:
        error_msg = (
            f"\n🚨 UNAUTHORIZED NETWORK TRAFFIC DETECTED! 🚨\n"
            f"\nOnly {ALLOWED_DOMAINS} are allowed, but we detected:\n"
        )
        for domain in sorted(unauthorized_domains):
            count = proxy.report.domains_contacted[domain]
            error_msg += f"  ❌ {domain} ({count} request(s))\n"
        error_msg += "\nThis is a security violation! No unauthorized domains allowed!"
        raise AssertionError(error_msg)

    print(
        f"\n✅ All traffic verified! Only contacted allowed domains: {contacted_domains}"
    )
