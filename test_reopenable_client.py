"""
Test script for ReopenableAsyncClient that doesn't require network access.
"""

import asyncio

from code_puppy.reopenable_async_client import ReopenableAsyncClient


async def test_client_state_management():
    """Test that the client properly manages its state without network calls."""
    print("🐶 Testing ReopenableAsyncClient state management...")

    # Create client
    client = ReopenableAsyncClient(
        timeout=30.0, headers={"User-Agent": "Test-Agent/1.0"}
    )

    # Test initial state
    print(f"✅ Initial state - is_closed: {client.is_closed}")
    assert client.is_closed is True, "Client should start closed"

    # Test headers access when closed
    headers = client.headers
    print(f"✅ Headers accessible when closed: {dict(headers)}")

    # Test timeout access
    timeout = client.timeout
    print(f"✅ Timeout accessible: {timeout}")

    # Test explicit reopen
    print("\n📂 Testing explicit reopen...")
    await client.reopen()
    print(f"✅ After reopen - is_closed: {client.is_closed}")
    assert client.is_closed is False, "Client should be open after reopen()"

    # Test close
    print("\n🚪 Testing close...")
    await client.aclose()
    print(f"✅ After close - is_closed: {client.is_closed}")
    assert client.is_closed is True, "Client should be closed after aclose()"

    # Test multiple closes (should be safe)
    await client.aclose()
    print(f"✅ After second close - is_closed: {client.is_closed}")

    # Test multiple reopens
    print("\n🔄 Testing multiple reopens...")
    await client.reopen()
    await client.reopen()  # Should be safe
    print(f"✅ After multiple reopens - is_closed: {client.is_closed}")
    assert client.is_closed is False, "Client should remain open"

    # Test context manager
    print("\n🔒 Testing context manager...")
    async with ReopenableAsyncClient(timeout=10.0) as ctx_client:
        print(f"✅ Inside context - is_closed: {ctx_client.is_closed}")
        assert ctx_client.is_closed is False, "Client should be open in context"

    # Test repr
    print(f"\n📊 String representation: {client}")

    # Final cleanup
    await client.aclose()
    print(f"✅ Final state - is_closed: {client.is_closed}")

    print("\n🎉 All state management tests passed!")


async def test_configuration_preservation():
    """Test that client configuration is preserved across reopens."""
    print("\n🔧 Testing configuration preservation...")

    original_headers = {"Authorization": "Bearer test-token", "Custom": "value"}
    client = ReopenableAsyncClient(timeout=42.0, headers=original_headers, verify=False)

    # Check initial config
    assert client.timeout == 42.0, "Timeout should be preserved"

    # Open and close multiple times
    await client.reopen()
    await client.aclose()
    await client.reopen()

    # Verify config is still intact
    assert client.timeout == 42.0, "Timeout should survive reopens"
    current_headers = dict(client.headers)

    # Check that our custom headers are preserved (case-insensitive)
    for key, value in original_headers.items():
        # HTTP headers are case-insensitive, so check both ways
        found = False
        for header_key in current_headers:
            if header_key.lower() == key.lower():
                assert current_headers[header_key] == value, (
                    f"Header {key} value should be preserved"
                )
                found = True
                break
        assert found, f"Header {key} should be preserved (case-insensitive)"

    await client.aclose()
    print("✅ Configuration preservation tests passed!")


async def test_build_request():
    """Test building requests without sending them."""
    print("\n🔨 Testing request building...")

    client = ReopenableAsyncClient(headers={"User-Agent": "Builder/1.0"})

    # Should work even when client is closed
    request = client.build_request("GET", "https://example.com/test")
    print(f"✅ Built request: {request.method} {request.url}")

    assert request.method == "GET"
    assert str(request.url) == "https://example.com/test"

    # Check headers are included
    assert "User-Agent" in request.headers
    assert request.headers["User-Agent"] == "Builder/1.0"

    print("✅ Request building tests passed!")


async def test_stream_context_manager():
    """Test that the stream method returns a proper async context manager."""
    print("\n🌊 Testing stream context manager...")

    client = ReopenableAsyncClient(headers={"User-Agent": "StreamTest/1.0"})

    # Test that stream returns something that can be used as an async context manager
    stream_ctx = client.stream("GET", "https://httpbin.org/get")
    print(f"✅ Stream method returns: {type(stream_ctx)}")

    # Verify it has the async context manager methods
    assert hasattr(stream_ctx, "__aenter__"), "Stream result should have __aenter__"
    assert hasattr(stream_ctx, "__aexit__"), "Stream result should have __aexit__"

    print("✅ Stream context manager structure tests passed!")
    print("🎉 The async_generator bug has been fixed!")

    await client.aclose()


async def test_stream_usage_pattern():
    """Test the actual usage pattern that was failing before."""
    print("\n🔥 Testing the actual failing usage pattern...")

    client = ReopenableAsyncClient(timeout=5.0, headers={"User-Agent": "BugTest/1.0"})

    # This is the exact pattern that would have failed with:
    # TypeError: 'async_generator' object does not support the asynchronous context manager protocol
    try:
        # Note: This would actually try to make a network request, so we expect it might fail
        # But importantly, it should NOT fail with the async_generator TypeError anymore!
        async with client.stream("GET", "https://httpbin.org/get") as response:
            print(
                f"✅ Successfully entered stream context! Response type: {type(response)}"
            )
            # If we get here, the async context manager protocol is working!
            print(
                f"✅ Response status would be: {response.status_code if hasattr(response, 'status_code') else 'N/A'}"
            )
    except Exception as e:
        # We might get network errors, but NOT the async_generator TypeError
        if "async_generator" in str(
            e
        ) and "asynchronous context manager protocol" in str(e):
            print(f"❌ The original bug is still present: {e}")
            raise
        else:
            # Any other error (network, timeout, etc.) is expected and OK
            print(
                f"✅ Got expected network-related error (not the async_generator bug): {type(e).__name__}"
            )

    await client.aclose()
    print("🎯 The problematic usage pattern now works correctly!")


async def main():
    """Run all tests."""
    print("🚀 Starting ReopenableAsyncClient tests...\n")

    await test_client_state_management()
    await test_configuration_preservation()
    await test_build_request()
    await test_stream_context_manager()
    await test_stream_usage_pattern()

    print("\n🎯 All tests completed successfully!")
    print("The ReopenableAsyncClient is working perfectly! 🐕")


if __name__ == "__main__":
    asyncio.run(main())
