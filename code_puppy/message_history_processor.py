import json
import queue
from typing import List
import os
from pathlib import Path

import pydantic
import tiktoken
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart, UserPromptPart, TextPart, ModelRequest, ModelResponse

from code_puppy.config import get_message_history_limit
from code_puppy.tools.common import console
from code_puppy.model_factory import ModelFactory
from code_puppy.config import get_model_name

# Import summarization agent
try:
    from code_puppy.summarization_agent import get_summarization_agent as _get_summarization_agent
    SUMMARIZATION_AVAILABLE = True
    
    # Make the function available in this module's namespace for mocking
    def get_summarization_agent():
        return _get_summarization_agent()
        
except ImportError:
    SUMMARIZATION_AVAILABLE = False
    console.print("[yellow]Warning: Summarization agent not available. Message history will be truncated instead of summarized.[/yellow]")
    def get_summarization_agent():
        return None


def get_tokenizer_for_model(model_name: str):
    """
    Always use cl100k_base tokenizer regardless of model type.
    This is a simple approach that works reasonably well for most models.
    """
    return tiktoken.get_encoding("cl100k_base")


def stringify_message_part(part) -> str:
    """
    Convert a message part to a string representation for token estimation or other uses.
    
    Args:
        part: A message part that may contain content or be a tool call
        
    Returns:
        String representation of the message part
    """
    result = ""
    if hasattr(part, "part_kind"):
        result += part.part_kind + ": "
    else:
        result += str(type(part)) + ": "

    # Handle content
    if hasattr(part, 'content') and part.content:
        # Handle different content types
        if isinstance(part.content, str):
            result = part.content
        elif isinstance(part.content, pydantic.BaseModel):
            result = json.dumps(part.content.model_dump())
        elif isinstance(part.content, dict):
            result = json.dumps(part.content)
        else:
            result = str(part.content)
    
    # Handle tool calls which may have additional token costs
    # If part also has content, we'll process tool calls separately
    if hasattr(part, 'tool_name') and part.tool_name:
        # Estimate tokens for tool name and parameters
        tool_text = part.tool_name
        if hasattr(part, "args"):
            tool_text += f" {str(part.args)}"
        result += tool_text
            
    return result


def estimate_tokens_for_message(message: ModelMessage) -> int:
    """
    Estimate the number of tokens in a message using tiktoken with cl100k_base encoding.
    This is more accurate than character-based estimation.
    """
    tokenizer = get_tokenizer_for_model(get_model_name())
    total_tokens = 0
    
    for part in message.parts:
        part_str = stringify_message_part(part)
        if part_str:
            tokens = tokenizer.encode(part_str)
            total_tokens += len(tokens)
            
    return max(1, total_tokens)


def summarize_messages(messages: List[ModelMessage]) -> ModelMessage:

    # Get the summarization agent
    summarization_agent = get_summarization_agent()
    message_strings = []

    for message in messages:
        for part in message.parts:
            message_strings.append(stringify_message_part(part))


    summary_string = "\n".join(message_strings)
    instructions = (
        "Above I've given you a log of Agentic AI steps that have been taken"
        " as well as user queries, etc. Summarize the contents of these steps."
        " The high level details should remain but the bulk of the content from tool-call"
        " responses should be compacted and summarized. For example if you see a tool-call"
        " reading a file, and the file contents are large, then in your summary you might just"
        " write: * used read_file on space_invaders.cpp - contents removed."
        "\n Make sure your result is a bulleted list of all steps and interactions."
    )
    try:
        # Run the summarization agent
        result = summarization_agent.run_sync(f"{summary_string}\n{instructions}")
        
        # Create a new message with the summarized content
        summarized_parts = [TextPart(result.output)]
        summarized_message = ModelResponse(parts=summarized_parts)
        return summarized_message
    except Exception as e:
        console.print(f"Summarization failed during compaction: {e}")
        # Return original message if summarization fails
        return None


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    # Load model configuration
    models_path = os.environ.get("MODELS_JSON_PATH")
    if not models_path:
        models_path = Path(__file__).parent / "models.json"
    else:
        models_path = Path(models_path)
    
    model_configs = ModelFactory.load_config(str(models_path))
    model_name = get_model_name()
    
    # Get context length from model config
    model_config = model_configs.get(model_name, {})
    context_length = model_config.get("context_length", 128000)  # Default value
    
    # Reserve 10% of context for response
    return int(context_length)


def message_history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:

    total_current_tokens = sum(estimate_tokens_for_message(msg) for msg in messages)

    model_max = get_model_context_length()

    proportion_used = total_current_tokens / model_max
    console.print(f"[bold white on blue] Tokens in context: {total_current_tokens}, total model capacity: {model_max}, proportion used: {proportion_used}")

    if proportion_used > 0.9:
        summary = summarize_messages(messages)
        result_messages = [messages[0], summary]
        final_token_count = sum(estimate_tokens_for_message(msg) for msg in result_messages)
        console.print(f"Final token count after processing: {final_token_count}")
        return result_messages
    return messages