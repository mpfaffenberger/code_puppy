"""
Usage examples for ReopenableAsyncClient.

This file demonstrates various ways to use the ReopenableAsyncClient
for different scenarios where you need to reopen HTTP connections.
"""

import asyncio

from reopenable_async_client import ReopenableAsyncClient


async def example_basic_usage():
    """Basic usage example - close and reopen manually."""
    print("🔄 Basic Usage Example")
    print("=" * 50)

    # Create client with custom configuration
    client = ReopenableAsyncClient(
        timeout=30.0, headers={"User-Agent": "MyApp/1.0", "Accept": "application/json"}
    )

    print(f"Initial state: {client.is_closed}")

    # The client will auto-open on first request
    # (This would normally make a real request)
    print("Would make request here - client auto-opens")
    await client.reopen()  # Manual open for demo
    print(f"After opening: {client.is_closed}")

    # Close the client
    await client.aclose()
    print(f"After closing: {client.is_closed}")

    # Reopen and use again
    await client.reopen()
    print(f"After reopening: {client.is_closed}")

    # Final cleanup
    await client.aclose()
    print("✅ Basic usage complete!\n")


async def example_context_manager():
    """Context manager usage - automatic cleanup."""
    print("🔒 Context Manager Example")
    print("=" * 50)

    async with ReopenableAsyncClient(timeout=10.0) as client:
        print(f"Inside context: {client.is_closed}")
        # Make requests here
        # Client automatically closes when exiting context

    print("✅ Context manager complete!\n")


async def example_long_running_service():
    """Example for a long-running service that needs reconnection."""
    print("🔄 Long-Running Service Example")
    print("=" * 50)

    client = ReopenableAsyncClient(
        timeout=60.0, headers={"Authorization": "Bearer fake-token"}
    )

    # Simulate a service that runs periodic tasks
    for i in range(3):
        print(f"Task {i + 1}:")

        try:
            # Simulate work
            if i == 1:
                # Simulate connection being closed externally
                print("  Simulating connection loss...")
                await client.aclose()

            # Try to make a request (will auto-reopen if needed)
            if client.is_closed:
                print("  Client was closed, will auto-reopen on next request")
            else:
                print("  Client is open, ready to work")

            # Simulate opening for next request
            await client.reopen()
            print(f"  Task completed, client state: {client.is_closed}")

        except Exception as e:
            print(f"  Error in task {i + 1}: {e}")

        # Small delay between tasks
        await asyncio.sleep(0.1)

    await client.aclose()
    print("✅ Long-running service example complete!\n")


async def example_configuration_preservation():
    """Show that configuration is preserved across reopens."""
    print("⚙️  Configuration Preservation Example")
    print("=" * 50)

    original_headers = {
        "Authorization": "Bearer token-123",
        "X-Custom-Header": "custom-value",
        "User-Agent": "PersistentClient/1.0",
    }

    client = ReopenableAsyncClient(
        timeout=42.0,
        headers=original_headers,
        verify=False,  # Just for example
    )

    print(f"Original timeout: {client.timeout}")
    print(f"Original headers: {dict(client.headers)}")

    # Open, close, and reopen multiple times
    for i in range(3):
        await client.reopen()
        print(f"\nAfter reopen {i + 1}:")
        print(f"  Timeout still: {client.timeout}")
        print(f"  Headers preserved: {len(client.headers)} headers")

        await client.aclose()

    print("✅ Configuration preservation complete!\n")


async def example_error_handling():
    """Show how to handle errors gracefully."""
    print("⚠️  Error Handling Example")
    print("=" * 50)

    client = ReopenableAsyncClient(timeout=5.0)

    try:
        # Multiple closes should be safe
        await client.aclose()
        await client.aclose()  # Should not error
        print("✅ Multiple closes handled safely")

        # Multiple reopens should be safe
        await client.reopen()
        await client.reopen()  # Should not error
        print("✅ Multiple reopens handled safely")

        # Operations on closed client should auto-reopen
        await client.aclose()
        # This would normally auto-reopen:
        # response = await client.get("https://example.com")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        await client.aclose()

    print("✅ Error handling complete!\n")


async def main():
    """Run all examples."""
    print("🐶 ReopenableAsyncClient Usage Examples")
    print("🚀 Let's see this puppy in action!\n")

    await example_basic_usage()
    await example_context_manager()
    await example_long_running_service()
    await example_configuration_preservation()
    await example_error_handling()

    print("🎉 All examples completed!")
    print("Your ReopenableAsyncClient is ready to fetch like a good dog! 🐕‍🦺")


if __name__ == "__main__":
    asyncio.run(main())
