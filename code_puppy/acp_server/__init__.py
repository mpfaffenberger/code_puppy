import asyncio
import logging
import os
import uuid
from pathlib import Path
from acp import Agent, AgentSideConnection, PromptRequest, PromptResponse, stdio_streams, helpers
from acp.schema import Implementation, InitializeRequest, InitializeResponse, NewSessionRequest, NewSessionResponse
from code_puppy import __version__
from code_puppy.agents import get_current_agent

def setup_acp_logging():
    """Set up a file logger for the ACP server to avoid interfering with stdio."""
    log_dir = Path.home() / ".code_puppy"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "acp_server.log"

    logger = logging.getLogger("acp_server")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplication
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a file handler
    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.DEBUG)

    # Create a formatter and add it to the handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(handler)
    return logger

logger = logging.getLogger("acp_server")

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

            # Get the current Code Puppy agent
            agent = get_current_agent()
            logger.info(f"Using agent: {type(agent).__name__}")

            # Run the agent with the prompt
            logger.info("Running agent with prompt...")
            response = await agent.run_with_mcp(prompt_text)
            logger.info(f"Agent response received: {response.output if response else 'None'}")

            # Send the response back to the client as a text block update
            if response and response.output:
                logger.info("Sending response to client.")
                await self._conn.sessionUpdate(
                    helpers.session_notification(
                        params.sessionId,
                        helpers.update_agent_message([helpers.text_block(response.output)])
                    )
                )

            # Signal the end of the turn
            logger.info("Ending turn.")
            return PromptResponse(stopReason="end_turn")
        except Exception as e:
            logger.error(f"An error occurred in the prompt method: {e}", exc_info=True)
            return PromptResponse(stopReason="refusal")

    async def newSession(self, params: NewSessionRequest) -> NewSessionResponse:
        """
        Handles a new session request from the client.
        """
        return NewSessionResponse(sessionId=str(uuid.uuid4()))

async def acp_main():
    """
    Main entry point for the ACP server.
    """
    setup_acp_logging()
    logger.info("Starting ACP server.")
    reader, writer = await stdio_streams()
    AgentSideConnection(lambda conn: CodePuppyAgent(conn), writer, reader)
    await asyncio.Event().wait()
