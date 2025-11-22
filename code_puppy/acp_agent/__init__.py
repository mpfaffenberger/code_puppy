"""Agent Client Protocol (ACP) agent."""

import asyncio
import logging
import uuid

from acp import (
    Agent,
    AgentSideConnection,
    PromptRequest,
    PromptResponse,
    stdio_streams,
    helpers,
)
from acp.schema import (
    Implementation,
    InitializeRequest,
    InitializeResponse,
    NewSessionRequest,
    NewSessionResponse,
)

from code_puppy import __version__
from code_puppy.agents.agent_manager import get_current_agent


logger = logging.getLogger(__name__)

agent = get_current_agent()


class CodePuppyAgent(Agent):
    def __init__(self, conn):
        self._conn = conn

    async def initialize(self, params: InitializeRequest) -> InitializeResponse:
        """
        Handles the initialization request from the client.
        """
        return InitializeResponse(
            protocolVersion=params.protocolVersion,
            agentInfo=Implementation(
                name="Code Puppy",
                version=__version__,
            ),
        )

    async def prompt(self, params: PromptRequest) -> PromptResponse:
        """
        Handles a new prompt from the client.
        """
        try:
            logger.info(f"Received prompt request for session: {params.sessionId}")
            # Extract prompt text from the request
            prompt_text = "".join(
                block.text
                for block in params.prompt
                if block.type == "text" and hasattr(block, "text") and block.text
            )

            if not prompt_text:
                logger.warning("Prompt text is empty. Ending turn.")
                return PromptResponse(stopReason="end_turn")

            logger.info(f"Extracted prompt text: {prompt_text}")

            # Run the agent with the prompt
            logger.info("Running agent with prompt...")
            response = await agent.run_with_mcp(prompt_text)
            logger.info(
                f"Agent response received: {response.output if response else 'None'}"
            )

            # Send the response back to the client as a text block update
            if response and response.output:
                logger.info("Sending response to client.")
                await self._conn.sessionUpdate(
                    helpers.session_notification(
                        params.sessionId,
                        helpers.update_agent_message(
                            helpers.text_block(response.output)
                        ),
                    )
                )

            logger.info("Ending turn.")
            return PromptResponse(stopReason="end_turn")
        except Exception as e:
            logger.error(f"An error occurred in the prompt method: {e}", exc_info=True)
            return PromptResponse(stopReason="refusal")

    async def newSession(self, params: NewSessionRequest) -> NewSessionResponse:
        """
        Handles a new session request from the client.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"Created new session with ID: {session_id}")
        return NewSessionResponse(sessionId=session_id)


async def acp_main():
    """
    Main entry point for the ACP server.
    """
    logger.info("Starting ACP server.")
    reader, writer = await stdio_streams()
    AgentSideConnection(lambda conn: CodePuppyAgent(conn), writer, reader)
    await asyncio.Event().wait()
