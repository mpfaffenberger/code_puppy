#!/usr/bin/env python3
"""
Example usage of RetryManager with MCP server operations.

This demonstrates how the RetryManager can be integrated with MCP server calls
to handle transient failures gracefully with intelligent backoff strategies.
"""

import asyncio
import logging
import random
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from code_puppy.mcp.retry_manager import get_retry_manager, retry_mcp_call  # noqa: E402

logger = logging.getLogger(__name__)


class MockMCPServer:
    """Mock MCP server for demonstration purposes."""

    def __init__(self, failure_rate: float = 0.3):
        """
        Initialize the mock server.

        Args:
            failure_rate: Probability of failure (0.0 to 1.0)
        """
        self.failure_rate = failure_rate
        self.call_count = 0

    async def list_tools(self) -> list:
        """Simulate listing available tools."""
        self.call_count += 1

        # Simulate random failures
        if random.random() < self.failure_rate:
            raise ConnectionError(
                f"Simulated connection failure (call #{self.call_count})"
            )

        return [
            {"name": "read_file", "description": "Read a file"},
            {"name": "write_file", "description": "Write a file"},
            {"name": "list_directory", "description": "List directory contents"},
        ]

    async def call_tool(self, name: str, args: dict) -> Any:
        """Simulate calling a tool."""
        self.call_count += 1

        # Simulate random failures
        if random.random() < self.failure_rate:
            if random.random() < 0.5:
                raise ConnectionError(f"Connection failed for {name}")
            else:
                # Simulate a 500 error
                from unittest.mock import Mock

                import httpx

                response = Mock()
                response.status_code = 500
                raise httpx.HTTPStatusError(
                    "Server Error", request=Mock(), response=response
                )

        return f"Tool '{name}' executed with args: {args}"


async def demonstrate_basic_retry():
    """Demonstrate basic retry functionality."""
    print("=== Basic Retry Demonstration ===")

    retry_manager = get_retry_manager()
    server = MockMCPServer(failure_rate=0.5)  # 50% failure rate

    async def list_tools_call():
        return await server.list_tools()

    try:
        result = await retry_manager.retry_with_backoff(
            func=list_tools_call,
            max_attempts=3,
            strategy="exponential",
            server_id="demo-server",
        )
        print(f"✅ Success: Retrieved {len(result)} tools")
        print(f"Server call count: {server.call_count}")
    except Exception as e:
        print(f"❌ Failed after retries: {e}")

    # Check retry stats
    stats = await retry_manager.get_retry_stats("demo-server")
    print(
        f"Retry stats: total={stats.total_retries}, successful={stats.successful_retries}"
    )
    print()


async def demonstrate_different_strategies():
    """Demonstrate different backoff strategies."""
    print("=== Backoff Strategies Demonstration ===")

    strategies = ["fixed", "linear", "exponential", "exponential_jitter"]

    for strategy in strategies:
        print(f"\n{strategy.upper()} strategy:")
        server = MockMCPServer(failure_rate=0.7)  # High failure rate

        try:
            start_time = asyncio.get_event_loop().time()

            result = await retry_mcp_call(
                func=lambda: server.call_tool("read_file", {"path": "/example.txt"}),
                server_id=f"server-{strategy}",
                max_attempts=3,
                strategy=strategy,
            )

            end_time = asyncio.get_event_loop().time()
            print(f"  ✅ Success: {result}")
            print(f"  Time taken: {end_time - start_time:.2f}s")
            print(f"  Call count: {server.call_count}")
        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            print(f"  ❌ Failed: {e}")
            print(f"  Time taken: {end_time - start_time:.2f}s")
            print(f"  Call count: {server.call_count}")


async def demonstrate_concurrent_retries():
    """Demonstrate concurrent retry operations."""
    print("\n=== Concurrent Retries Demonstration ===")

    retry_manager = get_retry_manager()

    # Create multiple servers with different failure rates
    servers = [
        ("reliable-server", MockMCPServer(failure_rate=0.1)),
        ("unreliable-server", MockMCPServer(failure_rate=0.8)),
        ("moderate-server", MockMCPServer(failure_rate=0.4)),
    ]

    async def make_call(server_name: str, server: MockMCPServer):
        """Make a call with retry handling."""
        try:
            await retry_manager.retry_with_backoff(
                func=lambda: server.list_tools(),
                max_attempts=3,
                strategy="exponential_jitter",
                server_id=server_name,
            )
            return f"{server_name}: Success (calls: {server.call_count})"
        except Exception as e:
            return f"{server_name}: Failed - {e} (calls: {server.call_count})"

    # Run concurrent calls
    tasks = [make_call(name, server) for name, server in servers]
    results = await asyncio.gather(*tasks)

    print("Concurrent results:")
    for result in results:
        print(f"  {result}")

    # Show overall stats
    print("\nOverall retry statistics:")
    all_stats = await retry_manager.get_all_stats()
    for server_id, stats in all_stats.items():
        success_rate = (stats.successful_retries / max(stats.total_retries, 1)) * 100
        print(
            f"  {server_id}: {stats.total_retries} retries, {success_rate:.1f}% success rate"
        )


async def demonstrate_error_classification():
    """Demonstrate error classification for retry decisions."""
    print("\n=== Error Classification Demonstration ===")

    retry_manager = get_retry_manager()

    # Test different error types
    test_errors = [
        ConnectionError("Network connection failed"),
        asyncio.TimeoutError("Request timeout"),
        ValueError("JSON decode error: invalid format"),
        ValueError("Schema validation failed"),
        Exception("Authentication failed"),
        Exception("Permission denied"),
    ]

    print("Error retry decisions:")
    for error in test_errors:
        should_retry = retry_manager.should_retry(error)
        status = "✅ RETRY" if should_retry else "❌ NO RETRY"
        print(f"  {type(error).__name__}: {error} → {status}")


async def main():
    """Run all demonstrations."""
    print("RetryManager Example Demonstrations")
    print("=" * 50)

    await demonstrate_basic_retry()
    await demonstrate_different_strategies()
    await demonstrate_concurrent_retries()
    await demonstrate_error_classification()

    print("\n🎉 All demonstrations completed!")


if __name__ == "__main__":
    # Set a seed for reproducible results in the demo
    random.seed(42)
    asyncio.run(main())
