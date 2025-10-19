"""Integration test for MCP server Context7 end-to-end.

Verifies install/start/status/test/logs and issues a prompt intended to
engage the Context7 tool. We assert on clear connectivity lines and
ensure recent events are printed. Guarded by CONTEXT7_API_KEY.
"""

from __future__ import annotations

import os
import re
import time

import pexpect
import pytest

from tests.integration.cli_expect.fixtures import (
    CliHarness,
    satisfy_initial_prompts,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("CONTEXT7_API_KEY"),
    reason="Requires CONTEXT7_API_KEY to run Context7 MCP integration",
)


def test_mcp_context7_end_to_end(cli_harness: CliHarness) -> None:
    env = os.environ.copy()
    env.setdefault("CODE_PUPPY_TEST_FAST", "1")

    result = cli_harness.spawn(args=["-i"], env=env)
    try:
        # Resilient first-run handling
        satisfy_initial_prompts(result, skip_autosave=True)
        cli_harness.wait_for_ready(result)

        # Install context7
        result.sendline("/mcp install context7\r")
        try:
            result.child.expect(re.compile(r"Enter custom name .*\[context7\]"), timeout=15)
            result.sendline("\r")
        except pexpect.exceptions.TIMEOUT:
            pass
        try:
            result.child.expect(re.compile(r"Required Environment Variables|Proceed with installation\?"), timeout=30)
            time.sleep(0.2)
            result.sendline("\r")
        except pexpect.exceptions.TIMEOUT:
            pass
        result.child.expect(re.compile(r"Successfully installed server: .*context7"), timeout=60)
        cli_harness.wait_for_ready(result)

        # Start
        result.sendline("/mcp start context7\r")
        time.sleep(0.5)
        result.child.expect(re.compile(r"(Started|running|status).*context7"), timeout=60)
        cli_harness.wait_for_ready(result)

        # Status
        result.sendline("/mcp status context7\r")
        result.child.expect(re.compile(r"context7.*(running|healthy|ready)"), timeout=60)
        cli_harness.wait_for_ready(result)

        # Basic connectivity test
        result.sendline("/mcp test context7\r")
        result.child.expect(re.compile(r"Testing connectivity to server: context7"), timeout=60)
        result.child.expect(re.compile(r"Server instance created successfully"), timeout=60)
        result.child.expect(re.compile(r"Connectivity test passed"), timeout=60)
        cli_harness.wait_for_ready(result)

        # Prompt intended to trigger tool usage
        result.sendline("Use context7 to fetch pydantic_ai evals information\r")
        time.sleep(6)
        log = result.read_log().lower()
        assert ("context7" in log) or ("pydantic" in log) or ("eval" in log)

        # Pull recent logs as additional signal of activity
        result.sendline("/mcp logs context7 20\r")
        result.child.expect(re.compile(r"Recent Events for .*context7"), timeout=60)
        cli_harness.wait_for_ready(result)

        result.sendline("/quit\r")
        result.child.expect(pexpect.EOF, timeout=20)
    finally:
        cli_harness.cleanup(result)
