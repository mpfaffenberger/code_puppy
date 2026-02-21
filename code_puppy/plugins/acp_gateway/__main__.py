"""Allow running the ACP agent as: python -m code_puppy.plugins.acp_gateway

All transport concerns (stdio JSON-RPC) are handled by the ACP SDK.
We just start the CodePuppyAgent and let ``run_agent()`` do the rest.
"""

import asyncio
import logging
import sys

from code_puppy.plugins.acp_gateway.agent import run_code_puppy_agent

# Redirect logging to stderr so stdout stays clean for JSON-RPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

if __name__ == "__main__":
    asyncio.run(run_code_puppy_agent())