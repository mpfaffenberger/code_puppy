import asyncio
from acp import Agent, AgentSideConnection, PromptRequest, PromptResponse, stdio_streams, text_block
from code_puppy.agents import get_current_agent

class CodePuppyAgent(Agent):
    def __init__(self, conn):
        self._conn = conn

    async def prompt(self, params: PromptRequest) -> PromptResponse:
        """
        Handles a new prompt from the client.
        """
        # Extract prompt text from the request
        prompt_text = "".join(
            block.text
            for block in params.prompt
            if block.type == "text" and hasattr(block, "text") and block.text
        )

        if not prompt_text:
            return PromptResponse(stopReason="end_turn")

        # Get the current Code Puppy agent
        agent = get_current_agent()

        # Run the agent with the prompt
        response = await agent.run_with_mcp(prompt_text)

        # Send the response back to the client as a text block update
        if response and response.output:
            await self._conn.sessionUpdate([text_block(response.output)])

        # Signal the end of the turn
        return PromptResponse(stopReason="end_turn")

async def acp_main():
    """
    Main entry point for the ACP server.
    """
    reader, writer = await stdio_streams()
    AgentSideConnection(lambda conn: CodePuppyAgent(conn), writer, reader)
    await asyncio.Event().wait()
